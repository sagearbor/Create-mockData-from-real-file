"""About page: copy-and-paste blocks for using the tool from code (ADP-42).

The examples are parsed OUT OF the served page and then really used against the
app, so these tests fail when an example drifts from the API (a renamed field,
a moved route, a changed response key, a new undocumented request field).

No network, no Azure login, no real LLM: the generator is replaced by a fake.
All data here is made up (widgets), never anything resembling real records.
"""

import ast
import inspect
import json
import re
import shlex
import shutil
import subprocess
import sys
import types
import typing
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import main
from src.api import v1 as api_v1
from src.core import generation_service

REPO = Path(__file__).resolve().parent.parent
PLACEHOLDER = "https://YOUR-SITE"
KEY_VAR = "$MOCKDATA_API_KEY"
SECTION_START = '<section class="info-block" id="use-it-from-code">'
# The only other addresses the page may contain: its existing font and diagram assets.
ALLOWED_HOSTS = {"YOUR-SITE", "fonts.googleapis.com", "cdn.jsdelivr.net"}

SOURCE_CSV = "part_id,finish,length_mm\nA1,matt,10.5\nA2,gloss,11.0\nA3,matt,9.75\n"
DICTIONARY = {"columns": {
    "widget_id": {"type": "integer", "constraints": {"min_value": 1, "max_value": 99}},
    "colour": {"type": "string", "constraints": {"allowed_values": ["red", "blue"]}},
}}


class FakeGenerator:
    """Stands in for SyntheticDataGenerator: no LLM, returns exactly num_rows rows."""

    openai_client = object()

    def __init__(self):
        self.calls = []

    def generate(self, metadata, num_rows=None, match_threshold=0.8, use_cached=True):
        self.calls.append(num_rows)
        names = ([c["name"] for c in metadata.get("structure", {}).get("columns", [])]
                 or list(metadata.get("expected_columns") or []))
        n = num_rows if num_rows is not None else metadata["structure"]["shape"]["rows"]
        df = pd.DataFrame({name: [f"{name}-{i}" for i in range(n)] for name in names})
        return df, {"method": "llm", "num_rows": n, "cached": False}

    def _log_usage(self, *args, **kwargs):
        pass


def _no_real_client():
    raise AssertionError("test tried to build a real LLM client")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # usage logs and example output land in tmp, not the repo
    for name in (api_v1.API_KEY_ENV, api_v1.MAX_BYTES_ENV, "AZURE_OPENAI_ENDPOINT",
                 "AZURE_OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(generation_service, "_get_generator", _no_real_client)


@pytest.fixture
def fake(monkeypatch):
    """Fake generator behind /api/v1, A2A (generation_service) and the form routes (main)."""
    gen = FakeGenerator()
    monkeypatch.setattr(generation_service, "_get_generator", lambda: gen)
    monkeypatch.setattr(main, "synthetic_generator", gen)
    monkeypatch.setattr(main.cache_manager, "find_similar_cached", lambda *a, **k: None)
    # /generate-with-dictionary keeps the uploaded dictionary on this object: put it back after.
    monkeypatch.setattr(main.data_dictionary, "catalog", main.data_dictionary.catalog)
    monkeypatch.setattr(main.data_dictionary, "dictionary", main.data_dictionary.dictionary)
    return gen


@pytest.fixture
def client():
    # No "with": entering the context runs the lifespan, which builds the real LLM client.
    return TestClient(main.app)


# --------------------------------------------------------------------------- #
# Reading the page
# --------------------------------------------------------------------------- #

class _Section(HTMLParser):
    """Collects the copy blocks, the field table rows, the links and the visible text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self.fields, self.hrefs, self.text = [], {}, [], []
        self.loose_pre = 0          # <pre> outside any copy block
        self.local_dev_notes = []   # text of the labelled local-development note(s)
        self._block = self._field = self._note_tag = None
        self._div_depth = 0
        self._in_code = self._in_title = self._in_button = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if "data-local-dev-note" in a:
            self._note_tag = tag
            self.local_dev_notes.append("")
        if tag == "a" and a.get("href"):
            self.hrefs.append(a["href"])
        if tag == "tr" and a.get("data-field"):
            self._field = a["data-field"]
            self.fields[self._field] = ""
        if tag == "div":
            if self._block is not None:
                self._div_depth += 1
            elif "api-block" in classes:
                self._block = {"name": a.get("data-block"), "lang": a.get("data-lang"),
                               "title": "", "buttons": [], "code": "", "code_tags": 0}
                self._div_depth = 1
        if tag == "pre" and self._block is None:
            self.loose_pre += 1
        if self._block is not None:
            if self._in_code:
                self._block["code_tags"] += 1  # markup inside the code would change the copied text
            if tag == "code":
                self._in_code = True
            if tag == "button" and "copy-btn" in classes:
                self._in_button = True
                self._block["buttons"].append("")
            if "api-block-title" in classes:
                self._in_title = True

    def handle_endtag(self, tag):
        if tag == self._note_tag:
            self._note_tag = None
        if tag == "tr":
            self._field = None
        if self._block is None:
            return
        if tag == "code":
            self._in_code = False
        elif tag == "button":
            self._in_button = False
        elif tag == "span":
            self._in_title = False
        elif tag == "div":
            self._div_depth -= 1
            if self._div_depth == 0:
                self.blocks.append(self._block)
                self._block = None

    def handle_data(self, data):
        self.text.append(data)
        if self._note_tag:
            self.local_dev_notes[-1] += data
        if self._field:
            self.fields[self._field] += data
        if self._block is not None:
            if self._in_code:
                self._block["code"] += data
            elif self._in_button:
                self._block["buttons"][-1] += data
            elif self._in_title:
                self._block["title"] += data


def _page(client) -> str:
    resp = client.get("/about")
    assert resp.status_code == 200, resp.text
    return resp.text


def _section_html(page: str) -> str:
    assert SECTION_START in page, 'the About page has no "Use it from code" section'
    rest = page.split(SECTION_START, 1)[1]
    return rest.split("</section>", 1)[0]


@pytest.fixture
def page(client):
    return _page(client)


@pytest.fixture
def section(page):
    parser = _Section()
    parser.feed(_section_html(page))
    parser.close()
    parser.all_text = " ".join(" ".join(parser.text).split())
    return parser


def _block(section, name):
    found = [b for b in section.blocks if b["name"] == name]
    assert len(found) == 1, f"expected exactly one block named {name!r}"
    return found[0]


def _parse_curl(code: str) -> dict:
    """Split a curl example the way a shell would (quotes kept, backslash-newline joined)."""
    args = shlex.split(code.replace("\\\n", " "))
    assert args[0] == "curl", code
    out = {"method": "GET", "url": None, "headers": {}, "data": None, "form": {}, "output": None}
    i = 1
    while i < len(args):
        arg = args[i]
        if arg == "-X":
            out["method"] = args[i + 1]
        elif arg == "-H":
            name, _, value = args[i + 1].partition(":")
            out["headers"][name.strip()] = value.strip()
        elif arg == "-d":
            out["data"] = args[i + 1]
        elif arg == "-F":
            name, _, value = args[i + 1].partition("=")
            out["form"][name] = value
        elif arg == "-o":
            out["output"] = args[i + 1]
        else:
            assert not arg.startswith("-"), f"curl option {arg!r} is not understood by this test"
            assert out["url"] is None, code
            out["url"] = arg
            i += 1
            continue
        i += 2
    assert out["url"] and out["url"].startswith(PLACEHOLDER + "/"), code
    out["path"] = out["url"][len(PLACEHOLDER):]
    return out


def _real_headers(headers: dict, key: str = "") -> dict:
    """What the shell would send: $MOCKDATA_API_KEY replaced by the variable's value."""
    return {name: value.replace(KEY_VAR, key) for name, value in headers.items()}


# --------------------------------------------------------------------------- #
# The section, its blocks and their copy buttons
# --------------------------------------------------------------------------- #

def test_about_has_a_visible_use_it_from_code_section(page, section):
    assert "Use it from code" in _section_html(page).split("</h2>", 1)[0]
    assert len(section.blocks) >= 7
    # Not hidden behind a click-to-expand word: no block sits inside an accordion.
    for chunk in _section_html(page).split('class="accordion-content"')[1:]:
        assert "api-block" not in chunk and "<pre" not in chunk


def test_no_paragraph_in_the_section_holds_block_content(page):
    """A browser ends a <p> at the first list, table, div or pre inside it. That once threw
    a click-to-expand list out of its hidden span, so it showed permanently."""
    for paragraph in re.findall(r"<p[\s>].*?</p>", _section_html(page), re.S):
        for tag in ("<ul", "<ol", "<div", "<pre", "<table", "<h3", "<p", "<section"):
            assert tag not in paragraph[2:], f"{tag}> inside a <p>: {paragraph[:80]!r}"


def test_section_has_curl_python_and_javascript_json_examples(section):
    for lang in ("curl", "python", "javascript"):
        hits = [b for b in section.blocks if b["lang"] == lang and "/api/v1/generate" in b["code"]]
        assert hits, f"no {lang} example for POST /api/v1/generate"
    assert "import requests" in _block(section, "python-json")["code"]
    assert "fetch(" in _block(section, "javascript-json")["code"]
    assert "pd.DataFrame(" in _block(section, "python-pandas")["code"]
    assert "csv_text" in _block(section, "python-pandas")["code"]


def test_every_block_has_one_copy_button_and_plain_text_code(section):
    assert section.loose_pre == 0, "a <pre> in the section has no copy button"
    for block in section.blocks:
        assert block["name"] and block["lang"] and block["title"].strip(), block
        assert [b.strip() for b in block["buttons"]] == ["Copy"], block["name"]
        assert block["code"].strip(), block["name"]
        assert block["code_tags"] == 0, f"{block['name']}: markup inside <code>"
        assert block["code"] == block["code"].strip(), f"{block['name']}: stray whitespace would be copied"
    names = [b["name"] for b in section.blocks]
    assert len(names) == len(set(names))


def test_copy_script_uses_clipboard_with_a_fallback_and_no_inner_html(page):
    match = re.search(r'<script id="api-blocks-script">(.*?)</script>', page, re.S)
    assert match, "the copy/origin script is missing"
    script = match.group(1)
    assert "navigator.clipboard.writeText(" in script
    assert "document.execCommand('copy')" in script      # fallback for non-secure contexts
    assert "'Copied'" in script
    assert "window.location.origin" in script and f"'{PLACEHOLDER}'" in script
    assert "innerHTML" not in script and "insertAdjacentHTML" not in script
    assert "document.write" not in script


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_inline_script_and_javascript_example_are_valid_javascript(page, section, tmp_path):
    script = re.search(r'<script id="api-blocks-script">(.*?)</script>', page, re.S).group(1)
    for name, source in (("page_script.js", script),
                         ("example.js", _block(section, "javascript-json")["code"])):
        path = tmp_path / name
        path.write_text(source, encoding="utf-8")
        done = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True, timeout=30)
        assert done.returncode == 0, done.stderr


# --------------------------------------------------------------------------- #
# Addresses and keys
# --------------------------------------------------------------------------- #

def test_no_hard_coded_hostname_and_localhost_only_in_the_local_dev_note(page, section):
    assert "azurecontainerapps" not in page.lower()
    hosts = set(re.findall(r"https?://([A-Za-z0-9.\-]+)", page))
    assert hosts - ALLOWED_HOSTS == {"localhost"}, hosts

    assert len(section.local_dev_notes) == 1
    note = section.local_dev_notes[0]
    assert "local development" in note.lower() and "localhost" in note
    # Take the labelled note out: nothing else on the page may mention a local address.
    without_note = re.sub(r"<p[^>]*\bdata-local-dev-note\b.*?</p>", "", page, flags=re.S)
    assert without_note != page
    for word in ("localhost", "127.0.0.1", "0.0.0.0", ":8201"):
        assert word not in without_note, word

    for block in section.blocks:
        for url in re.findall(r"https?://[^\s\"']+", block["code"]):
            assert url.startswith(PLACEHOLDER), f"{block['name']}: {url}"


def test_api_key_is_shown_as_an_environment_placeholder_only_for_api_v1(section):
    for block in section.blocks:
        if "/api/v1/" in block["code"] and block["lang"] != "json":
            assert "X-API-Key" in block["code"], block["name"]
            assert "MOCKDATA_API_KEY" in block["code"], block["name"]
        elif block["lang"] == "curl":
            assert "X-API-Key" not in block["code"], f"{block['name']}: the key is for /api/v1 only"
    for name in ("curl-json", "curl-version"):
        assert _parse_curl(_block(section, name)["code"])["headers"]["X-API-Key"] == KEY_VAR
    # Nothing that looks like a real key: the header's value is always the environment
    # variable (shell or Python) or the constant that was read from it (JavaScript).
    allowed = (KEY_VAR + '"', 'os.environ.get("MOCKDATA_API_KEY", "")', "API_KEY }")
    for block in section.blocks:
        for line in block["code"].splitlines():
            if "X-API-Key" in line:
                value = re.split(r'X-API-Key"?:\s*', line, maxsplit=1)[1]
                assert value.startswith(allowed), line
    js = _block(section, "javascript-json")["code"]
    assert "const API_KEY = " in js and "process.env.MOCKDATA_API_KEY" in js
    assert api_v1.API_KEY_HEADER == "X-API-Key" and api_v1.API_KEY_ENV == "MOCKDATA_API_KEY"
    assert "only needed if this server was configured with a key" in section.all_text


# --------------------------------------------------------------------------- #
# The examples really work against the app
# --------------------------------------------------------------------------- #

def test_curl_json_example_posted_as_shown_returns_the_documented_response(client, section, fake):
    curl = _parse_curl(_block(section, "curl-json")["code"])
    assert (curl["method"], curl["path"]) == ("POST", "/api/v1/generate")
    assert curl["headers"]["Content-Type"] == "application/json"
    sent = json.loads(curl["data"])  # the example body must be valid JSON as typed

    resp = client.post(curl["path"], content=curl["data"], headers=_real_headers(curl["headers"]))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == set(api_v1.GenerateResponse.model_fields)
    assert body["status"] == "success"
    assert body["shape"] == [sent["num_rows"], 3] and len(body["data"]) == sent["num_rows"]
    assert body["columns"] == sent["csv_text"].splitlines()[0].split(",")
    assert fake.calls == [sent["num_rows"]]
    # Every response key is named on the page.
    for key in api_v1.GenerateResponse.model_fields:
        assert key in section.all_text.split("Response (200):", 1)[1].split("Limits and errors")[0], key


def test_curl_json_example_works_when_the_server_requires_a_key(client, section, fake, monkeypatch):
    monkeypatch.setenv(api_v1.API_KEY_ENV, "placeholder-for-this-test")
    curl = _parse_curl(_block(section, "curl-json")["code"])

    with_key = client.post(curl["path"], content=curl["data"],
                           headers=_real_headers(curl["headers"], "placeholder-for-this-test"))
    without_key = client.post(curl["path"], content=curl["data"],
                              headers=_real_headers(curl["headers"]))

    assert with_key.status_code == 200, with_key.text
    assert without_key.status_code == 401
    assert without_key.json()["error_class"] == "InvalidApiKey"


def test_curl_version_example(client, section):
    curl = _parse_curl(_block(section, "curl-version")["code"])
    assert (curl["method"], curl["path"]) == ("GET", "/api/v1/version")
    resp = client.get(curl["path"], headers=_real_headers(curl["headers"]))
    assert resp.status_code == 200, resp.text
    assert set(resp.json()) == set(api_v1.VersionResponse.model_fields)


def _fake_requests(client):
    """A stand-in `requests` module that sends the example's call to the app under test."""
    seen = []

    def post(url, headers=None, json=None, timeout=None):
        assert url.startswith(PLACEHOLDER + "/"), url
        assert timeout, "the example should set a timeout: generation is slow"
        resp = client.post(url[len(PLACEHOLDER):], headers=headers, json=json)
        seen.append((url[len(PLACEHOLDER):], json, resp.status_code))
        return types.SimpleNamespace(ok=resp.is_success, status_code=resp.status_code, json=resp.json)

    module = types.ModuleType("requests")
    module.post = post
    return module, seen


@pytest.mark.parametrize("name", ["python-json", "python-pandas"])
def test_python_examples_run_unchanged(client, section, fake, monkeypatch, tmp_path, capsys, name):
    code = _block(section, name)["code"]
    ast.parse(code)
    module, seen = _fake_requests(client)
    monkeypatch.setitem(sys.modules, "requests", module)
    (tmp_path / "your_data.csv").write_text(SOURCE_CSV, encoding="utf-8")  # the placeholder file name

    exec(compile(code, name, "exec"), {"__name__": "__main__"})  # noqa: S102 - our own page's example

    assert [(path, status) for path, _, status in seen] == [("/api/v1/generate", 200)]
    sent = seen[0][1]
    assert set(sent) <= set(api_v1.GenerateRequest.model_fields)
    out = capsys.readouterr().out
    if name == "python-pandas":
        assert sent["csv_text"] == SOURCE_CSV
        saved = pd.read_csv(tmp_path / "synthetic.csv")
        assert list(saved.columns) == ["part_id", "finish", "length_mm"]
        assert len(saved) == sent["num_rows"]
        assert "part_id" in out
    else:
        assert f"[{sent['num_rows']}, 3]" in out


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_javascript_example_sends_a_request_the_api_accepts(client, section, fake, tmp_path):
    code = _block(section, "javascript-json")["code"]
    assert not re.search(r"fetch\(\s*[`'\"]https?://", code)  # tests/test_frontend_api_base.py rule
    # Run the example unchanged, with fetch replaced by a recorder.
    recorder = (
        "globalThis.fetch = async (url, options) => {\n"
        "  process.stdout.write(JSON.stringify({ url, options }));\n"
        "  return { ok: true, json: async () => ({ data: [] }) };\n"
        "};\n"
        "console.table = () => {};\n"
    )
    script = tmp_path / "example_run.js"
    script.write_text(recorder + code, encoding="utf-8")
    done = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0 and not done.stderr, done.stderr
    call = json.loads(done.stdout)

    assert call["url"] == PLACEHOLDER + "/api/v1/generate"
    assert call["options"]["method"] == "POST"
    assert "X-API-Key" in call["options"]["headers"]
    resp = client.post("/api/v1/generate", content=call["options"]["body"],
                       headers=call["options"]["headers"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["shape"][0] == json.loads(call["options"]["body"])["num_rows"]


@pytest.mark.parametrize("name, path, route, file_field, file_name", [
    ("curl-file", "/generate", "generate_synthetic_data", "file", "your_data.csv"),
    ("curl-dictionary", "/generate-with-dictionary", "generate_with_dictionary",
     "dictionary_file", "dictionary.json"),
])
def test_form_upload_examples_match_the_routes_and_return_csv(
        client, section, fake, name, path, route, file_field, file_name):
    curl = _parse_curl(_block(section, name)["code"])
    assert (curl["method"], curl["path"]) == ("POST", path)
    assert curl["output"] == "synthetic.csv"
    assert curl["form"][file_field] == "@" + file_name
    assert curl["form"]["output_format"] == "csv"
    # Every -F name is a real parameter of the route function.
    parameters = inspect.signature(getattr(main, route)).parameters
    assert set(curl["form"]) <= set(parameters), set(curl["form"]) - set(parameters)

    content = json.dumps(DICTIONARY) if file_field == "dictionary_file" else SOURCE_CSV
    fields = {k: v for k, v in curl["form"].items() if k != file_field}
    resp = client.post(path, data=fields, files={file_field: (file_name, content.encode())})

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    lines = resp.text.strip().splitlines()
    assert len(lines) == int(curl["form"]["num_rows"]) + 1  # header + rows
    expected = list(DICTIONARY["columns"]) if file_field == "dictionary_file" else ["part_id", "finish", "length_mm"]
    assert lines[0].split(",") == expected


# --------------------------------------------------------------------------- #
# Reference: fields, limits, errors, links
# --------------------------------------------------------------------------- #

def test_field_table_names_every_generate_request_field(section):
    model = api_v1.GenerateRequest.model_fields
    assert set(section.fields) == set(model), (
        "the field table on the About page and GenerateRequest disagree: "
        f"undocumented {set(model) - set(section.fields)}, stale {set(section.fields) - set(model)}")

    for name, info in model.items():
        row = section.fields[name]
        if info.default is not None:
            shown = str(info.default).lower() if isinstance(info.default, bool) else str(info.default)
            assert shown in row, f"{name}: default {shown!r} is not in the table row"
        if typing.get_origin(info.annotation) is typing.Literal:
            for option in typing.get_args(info.annotation):
                assert option in row, f"{name}: option {option!r} is not in the table row"
        for bound in info.metadata:
            for attr in ("ge", "le"):
                value = getattr(bound, attr, None)
                if value is not None:
                    texts = {str(value), f"{value:,}"}
                    if isinstance(value, float) and value.is_integer():
                        texts.add(str(int(value)))
                    assert any(t in row for t in texts), f"{name}: bound {value} is not in the table row"

    assert api_v1.GenerateRequest.model_config.get("extra") == "forbid"
    assert "Unknown fields are rejected" in section.all_text
    assert "exactly one of csv_text or data_content" in section.all_text


def test_limits_and_the_single_error_shape_are_documented(client, section):
    megabytes = api_v1.DEFAULT_MAX_BYTES // (1024 * 1024)
    assert api_v1.DEFAULT_MAX_BYTES == megabytes * 1024 * 1024
    assert f"{megabytes} MB" in section.all_text and api_v1.MAX_BYTES_ENV in section.all_text

    shape = json.loads(_block(section, "error-shape")["code"])
    assert set(shape) == set(api_v1.ErrorResponse.model_fields) == {"status", "error", "error_class"}
    assert shape["status"] == "error"

    errors_table = section.all_text.split("HTTP status", 1)[1]
    for status in list(api_v1._ERROR_RESPONSES) + [500]:
        assert str(status) in errors_table, status

    # A real failure has exactly that shape, and its error_class is in the table.
    resp = client.post("/api/v1/generate", json={"csv_text": "a,b\n1,2\n", "not_a_field": 1})
    assert resp.status_code == 422
    assert set(resp.json()) == set(shape)
    assert resp.json()["error_class"] == shape["error_class"]
    assert resp.json()["error_class"] in errors_table

    too_many = api_v1.GenerateRequest.model_fields["num_rows"].metadata
    limit = next(m.le for m in too_many if getattr(m, "le", None) is not None)
    assert f"{limit:,}" in section.all_text.split("Limits:", 1)[1]
    assert client.post("/api/v1/generate",
                       json={"csv_text": "a,b\n1,2\n", "num_rows": limit + 1}).status_code == 422


def test_links_point_at_pages_that_exist_including_the_interactive_reference(client, section):
    assert section.hrefs, "the section has no links"
    for href in section.hrefs:
        assert href.startswith("/"), f"{href}: links must be relative to this site"
        assert client.get(href).status_code == 200, href
    assert main.app.docs_url in section.hrefs        # /docs is enabled, so it is linked
    assert main.app.openapi_url in section.hrefs
    assert "/api/v1/generate" in client.get(main.app.openapi_url).json()["paths"]


def test_a2a_and_mcp_pointers_describe_what_the_code_does(client, section, fake):
    # A2A: the agent card and the message route named on the page both answer.
    card_curl = _parse_curl(_block(section, "curl-agent-card")["code"])
    assert card_curl["path"] == "/.well-known/agent.json"
    card = client.get(card_curl["path"])
    assert card.status_code == 200, card.text
    assert card.json()["url"] in section.all_text  # /a2a/mock-data-generator

    from src.a2a_agent import register
    register()  # normally done at startup (lifespan), which these tests do not run
    import base64
    envelope = {
        "payload": {"data_content": base64.b64encode(SOURCE_CSV.encode()).decode(), "num_rows": 4},
        "metadata": {"correlation_id": "test-1", "cycle": 1, "agent_id": "mock-data-generator"},
    }
    for word in list(envelope) + list(envelope["metadata"]) + ["data_content"]:
        assert word in section.all_text, word
    answer = client.post(card.json()["url"], json=envelope)
    assert answer.status_code == 200, answer.text
    assert answer.json()["payload"]["status"] == "success"
    assert answer.json()["payload"]["shape"] == [4, 3]

    # MCP: a local stdio program, started exactly as the page says, with the two named tools.
    start = _block(section, "mcp-start")["code"]
    assert start == "python -m src.mcp_server"
    source = (REPO / "src" / "mcp_server.py").read_text(encoding="utf-8")
    assert "stdio_server()" in source and '__name__ == "__main__"' in source
    for tool in re.findall(r'Tool\(\s*name="([^"]+)"', source):
        assert tool in section.all_text, tool
    assert "not reachable at this site's address" in section.all_text
