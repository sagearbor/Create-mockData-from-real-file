"""Offline tests for the JSON API under /api/v1 (ST-358).

ST-362  POST /api/v1/generate (JSON in, typed JSON out)
ST-363  API key, request size limit and ONE error shape, for /api/v1 only
ST-364  GET /api/v1/version and scripts/api_client_example.py
ST-365  this file

No network, no Azure login, no real LLM: the generator is replaced by a fake.
All data here is made up (widgets), never anything resembling real records.
"""

import asyncio
import base64
import importlib.util
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import httpx
import pandas as pd
import pytest

import main
from src.api import v1 as api_v1
from src.core import generation_service
from src.core.synthetic_generator import SyntheticDataGenerator
from src.utils.config import APP_VERSION

REPO = Path(__file__).resolve().parent.parent

CSV_TEXT = (
    "widget_id,colour,weight_g\n"
    "W001,red,12.5\n"
    "W002,blue,14.1\n"
    "W003,green,11.8\n"
    "W004,red,13.2\n"
    "W005,blue,12.9\n"
)
COLUMNS = ["widget_id", "colour", "weight_g"]
SOURCE_ROWS = 5

GOOD_CODE = (
    "import numpy as np\n"
    "import pandas as pd\n"
    "def generate_synthetic_data():\n"
    "    n = 8\n"
    "    return pd.DataFrame({'widget_id': [f'W{i:03d}' for i in range(n)],\n"
    "                         'colour': np.random.choice(['red', 'blue', 'green'], n),\n"
    "                         'weight_g': np.random.uniform(11, 15, n).round(1)})\n"
    "result = generate_synthetic_data()\n"
)

ERROR_KEYS = {"status", "error", "error_class"}


class FakeGenerator:
    """Stands in for SyntheticDataGenerator: no LLM, returns exactly num_rows rows."""

    def __init__(self, block=False):
        self.calls = []
        self.block = block
        self.entered, self.release, self.exited = threading.Event(), threading.Event(), threading.Event()

    def generate(self, metadata, num_rows=None, match_threshold=0.8, use_cached=True, model=None):
        self.calls.append({"num_rows": num_rows, "match_threshold": match_threshold,
                           "use_cached": use_cached})
        self.entered.set()
        try:
            if self.block:
                self.release.wait(timeout=5)
            names = [c["name"] for c in metadata["structure"]["columns"]]
            n = num_rows if num_rows is not None else metadata["structure"]["shape"]["rows"]
            df = pd.DataFrame({name: [f"{name}-{i}" for i in range(n)] for name in names})
            return df, {"method": "llm", "num_rows": n, "cached": False}
        finally:
            self.exited.set()


class _Completions:
    """Fake chat.completions for the real generator: fixed content or a fixed failure."""

    def __init__(self, content=GOOD_CODE, finish_reason="stop", exc=None):
        self.content, self.finish_reason, self.exc = content, finish_reason, exc

    def create(self, **kwargs):
        if self.exc:
            raise self.exc
        msg = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason=self.finish_reason, message=msg)])


def _real_generator(completions):
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    gen = SyntheticDataGenerator(openai_client=client)
    gen.cache_manager = SimpleNamespace(
        cache_generation=lambda *a, **k: None, find_similar_cached=lambda *a, **k: None)
    return gen


def _no_real_client():
    raise AssertionError("test tried to build a real LLM client")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # usage logs land in tmp, not the repo
    for name in (api_v1.API_KEY_ENV, api_v1.MAX_BYTES_ENV, "AZURE_OPENAI_ENDPOINT",
                 "AZURE_OPENAI_API_KEY", "LLM_REASONING_EFFORT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(SyntheticDataGenerator, "_reasoning_effort_rejected", False)
    monkeypatch.setattr(generation_service, "_get_generator", _no_real_client)


@pytest.fixture
def fake(monkeypatch):
    gen = FakeGenerator()
    monkeypatch.setattr(generation_service, "_get_generator", lambda: gen)
    return gen


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test")


def _request(method, path, **kwargs):
    async def go():
        async with _client() as c:
            return await c.request(method, path, **kwargs)
    return asyncio.run(go())


def _generate(body, **kwargs):
    return _request("POST", "/api/v1/generate", json=body, **kwargs)


def _assert_uniform_error(resp, status_code, error_class=None):
    assert resp.status_code == status_code, resp.text
    body = resp.json()
    assert set(body) == ERROR_KEYS, body
    assert body["status"] == "error" and body["error"] and isinstance(body["error"], str)
    api_v1.ErrorResponse.model_validate(body)
    if error_class:
        assert body["error_class"] == error_class
    return body


# --------------------------------------------------------------------------- #
# ST-362: POST /api/v1/generate
# --------------------------------------------------------------------------- #

def test_ST_362_generate_json_csv_text_happy_path(fake):
    resp = _generate({"csv_text": CSV_TEXT})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "success"
    assert body["shape"] == [SOURCE_ROWS, len(COLUMNS)]  # num_rows omitted: match the source
    assert len(body["data"]) == SOURCE_ROWS and all(isinstance(r, dict) for r in body["data"])
    assert body["generation_info"]["method"] == "llm"
    assert len(fake.calls) == 1


def test_ST_362_generate_json_base64_data_content(fake):
    encoded = base64.b64encode(CSV_TEXT.encode()).decode()
    resp = _generate({"data_content": encoded, "format": "csv", "num_rows": 3})

    assert resp.status_code == 200, resp.text
    assert resp.json()["columns"] == COLUMNS and resp.json()["shape"] == [3, 3]


def test_ST_362_generate_json_base64_tsv_uses_format(fake):
    tsv = CSV_TEXT.replace(",", "\t")
    resp = _generate({"data_content": base64.b64encode(tsv.encode()).decode(), "format": "tsv"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["columns"] == COLUMNS  # parsed as tab-separated, not as one wide column


@pytest.mark.parametrize("num_rows", [1, 7, 40])
def test_ST_362_generate_json_num_rows_respected(fake, num_rows):
    resp = _generate({"csv_text": CSV_TEXT, "num_rows": num_rows})

    assert resp.status_code == 200, resp.text
    assert resp.json()["shape"] == [num_rows, len(COLUMNS)]
    assert len(resp.json()["data"]) == num_rows
    assert fake.calls[0]["num_rows"] == num_rows


def test_ST_362_generate_json_response_matches_model_and_input_columns(fake):
    body = _generate({"csv_text": CSV_TEXT, "num_rows": 4}).json()

    parsed = api_v1.GenerateResponse.model_validate(body)
    assert set(body) == set(api_v1.GenerateResponse.model_fields)
    assert parsed.columns == COLUMNS  # same columns, same order, as the input
    assert all(list(row) == COLUMNS for row in parsed.data)


def test_ST_362_generate_json_options_reach_the_generator(fake):
    resp = _generate({"csv_text": CSV_TEXT, "match_threshold": 0.55, "use_cache": False})

    assert resp.status_code == 200, resp.text
    assert fake.calls[0] == {"num_rows": None, "match_threshold": 0.55, "use_cached": False}


def test_ST_362_generate_json_real_pipeline_with_fake_llm(monkeypatch):
    """The real generator (fake LLM behind it): its generation_info must serialise."""
    monkeypatch.setattr(generation_service, "_get_generator",
                        lambda: _real_generator(_Completions()))

    resp = _generate({"csv_text": CSV_TEXT, "num_rows": 8, "use_cache": False})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["shape"] == [8, 3] and body["columns"] == COLUMNS
    assert body["generation_info"]["method"] == "llm"


def test_ST_362_generate_json_in_openapi_with_request_model():
    spec = _request("GET", "/openapi.json").json()

    post = spec["paths"]["/api/v1/generate"]["post"]
    assert post["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("/GenerateRequest")
    assert post["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/GenerateResponse")
    for code in ("401", "413", "422", "502"):
        assert post["responses"][code]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")
    props = spec["components"]["schemas"]["GenerateRequest"]["properties"]
    assert {"csv_text", "data_content", "format", "num_rows", "match_threshold", "use_cache"} <= set(props)


def test_ST_362_generate_json_does_not_block_event_loop(monkeypatch):
    """/health must answer while a slow generation is in flight (ACA liveness probe)."""
    gen = FakeGenerator(block=True)
    monkeypatch.setattr(generation_service, "_get_generator", lambda: gen)

    async def go():
        async with _client() as c:
            task = asyncio.create_task(
                c.post("/api/v1/generate", json={"csv_text": CSV_TEXT, "num_rows": 2}, timeout=30))
            for _ in range(200):  # wait (without blocking the loop) until generation starts
                if gen.entered.is_set() or task.done():
                    break
                await asyncio.sleep(0.02)
            assert gen.entered.is_set(), "generation never started"

            health = await asyncio.wait_for(c.get("/health"), timeout=2)
            in_flight = not gen.exited.is_set() and not task.done()
            gen.release.set()
            return health, in_flight, await asyncio.wait_for(task, timeout=30)

    health, in_flight, resp = asyncio.run(go())
    assert health.status_code == 200
    assert in_flight, "/health only answered after generation finished: event loop was blocked"
    assert resp.status_code == 200 and resp.json()["shape"] == [2, 3]


# --------------------------------------------------------------------------- #
# ST-363: one error shape, API key, size limit (for /api/v1 only)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("body", [
    {},                                                           # neither input
    {"num_rows": 5},                                              # still neither
    {"csv_text": CSV_TEXT, "data_content": "YQ=="},               # both
    {"data_content": "not base64 !!"},                            # bad base64
    {"csv_text": CSV_TEXT, "num_rows": 0},                        # out of range
    {"csv_text": CSV_TEXT, "match_threshold": 1.5},               # out of range
    {"csv_text": CSV_TEXT, "nmu_rows": 5},                        # typo in an option name
])
def test_ST_363_validation_error_is_422_in_uniform_shape(fake, body):
    resp = _generate(body)

    _assert_uniform_error(resp, 422, "RequestValidationError")
    assert "detail" not in resp.json()
    assert fake.calls == []  # nothing was generated


def test_ST_363_missing_both_inputs_says_what_to_send(fake):
    body = _assert_uniform_error(_generate({}), 422)
    assert "csv_text" in body["error"] and "data_content" in body["error"]


def test_ST_363_body_that_is_not_json_is_422_in_uniform_shape(fake):
    resp = _request("POST", "/api/v1/generate", content=b"{not json",
                    headers={"Content-Type": "application/json"})
    _assert_uniform_error(resp, 422, "RequestValidationError")


class _Boom(Exception):
    status_code = 500


@pytest.mark.parametrize("kw,expect", [
    ({"exc": _Boom("provider said: secret prompt text")}, "HTTP 500"),
    ({"content": "partial", "finish_reason": "length"}, "finish_reason=length"),
    ({"content": "", "finish_reason": "stop"}, "empty response"),
])
def test_ST_363_ai_failure_is_502_in_uniform_shape(monkeypatch, kw, expect):
    monkeypatch.setattr(generation_service, "_get_generator",
                        lambda: _real_generator(_Completions(**kw)))

    resp = _generate({"csv_text": CSV_TEXT, "num_rows": 8, "use_cache": False})

    body = _assert_uniform_error(resp, 502)
    assert body["error"].startswith("AI generation failed:") and expect in body["error"]
    assert body["error"].endswith("No data was generated.")
    assert "secret prompt text" not in resp.text


def test_ST_363_ai_not_configured_is_503_in_uniform_shape(monkeypatch):
    monkeypatch.setattr(generation_service, "_get_generator",
                        lambda: SyntheticDataGenerator(openai_client=None))

    resp = _generate({"csv_text": CSV_TEXT, "use_cache": False})

    body = _assert_uniform_error(resp, 503, "AINotConfiguredError")
    assert "No data was generated" in body["error"]


def test_ST_363_unreadable_source_data_is_400_in_uniform_shape(fake):
    not_json = base64.b64encode(b"this is not json").decode()
    resp = _generate({"data_content": not_json, "format": "json"})

    _assert_uniform_error(resp, 400, "GenerationError")
    assert fake.calls == []


def test_ST_363_unknown_v1_path_is_404_in_uniform_shape():
    _assert_uniform_error(_request("GET", "/api/v1/nope"), 404)
    _assert_uniform_error(_request("GET", "/api/v1/generate"), 405)


def test_ST_363_api_key_check_is_off_when_env_unset(fake):
    assert _generate({"csv_text": CSV_TEXT}).status_code == 200
    assert _generate({"csv_text": CSV_TEXT}, headers={"X-API-Key": "anything"}).status_code == 200
    assert _request("GET", "/api/v1/version").status_code == 200


def test_ST_363_api_key_check_is_off_when_env_empty(monkeypatch, fake):
    monkeypatch.setenv(api_v1.API_KEY_ENV, "")
    assert _generate({"csv_text": CSV_TEXT}).status_code == 200


@pytest.mark.parametrize("headers", [
    {},                                       # missing
    {"X-API-Key": "wrong-key"},               # wrong
    {"X-API-Key": "test-key-not-a-secret-x"},  # right prefix, extra character
    {"X-API-Key": ""},                        # empty
    {"Authorization": "Bearer test-key-not-a-secret"},  # right value, wrong header
])
def test_ST_363_wrong_or_missing_api_key_is_401(monkeypatch, fake, headers):
    monkeypatch.setenv(api_v1.API_KEY_ENV, "test-key-not-a-secret")

    resp = _generate({"csv_text": CSV_TEXT}, headers=headers)
    body = _assert_uniform_error(resp, 401, "InvalidApiKey")
    assert "test-key-not-a-secret" not in body["error"]  # never echo the expected key
    assert fake.calls == []
    _assert_uniform_error(_request("GET", "/api/v1/version", headers=headers), 401, "InvalidApiKey")


def test_ST_363_right_api_key_is_200(monkeypatch, fake):
    monkeypatch.setenv(api_v1.API_KEY_ENV, "test-key-not-a-secret")
    headers = {"x-api-key": "test-key-not-a-secret"}  # header names are case-insensitive

    assert _generate({"csv_text": CSV_TEXT}, headers=headers).status_code == 200
    assert _request("GET", "/api/v1/version", headers=headers).status_code == 200


def test_ST_363_api_key_does_not_apply_to_older_routes(monkeypatch):
    monkeypatch.setenv(api_v1.API_KEY_ENV, "test-key-not-a-secret")

    assert _request("GET", "/health").status_code == 200
    assert _request("GET", "/api").status_code == 200
    assert _request("GET", "/api/cache-info").status_code != 401  # /api/..., but not /api/v1


def test_ST_363_oversize_request_is_413_in_uniform_shape(monkeypatch, fake):
    monkeypatch.setenv(api_v1.MAX_BYTES_ENV, "2000")
    big = "widget_id,colour\n" + "W001,red\n" * 500  # ~4.5 kB

    body = _assert_uniform_error(_generate({"csv_text": big}), 413, "RequestTooLarge")
    assert "2000" in body["error"]
    assert fake.calls == []
    assert _generate({"csv_text": CSV_TEXT}).status_code == 200  # a small request still works


def test_ST_363_oversize_request_without_content_length_is_413(monkeypatch, fake):
    """A streamed (chunked) body has no Content-Length; the bytes are counted instead."""
    monkeypatch.setenv(api_v1.MAX_BYTES_ENV, "2000")
    payload = json.dumps({"csv_text": "widget_id,colour\n" + "W001,red\n" * 500}).encode()

    async def chunks():
        for i in range(0, len(payload), 512):
            yield payload[i:i + 512]

    resp = _request("POST", "/api/v1/generate", content=chunks(),
                    headers={"Content-Type": "application/json"})
    assert "content-length" not in resp.request.headers
    _assert_uniform_error(resp, 413, "RequestTooLarge")
    assert fake.calls == []


def test_ST_363_size_limit_default_and_bad_values(monkeypatch):
    assert api_v1.max_request_bytes() == api_v1.DEFAULT_MAX_BYTES == 10 * 1024 * 1024
    for bad in ("", "abc", "0", "-5"):
        monkeypatch.setenv(api_v1.MAX_BYTES_ENV, bad)
        assert api_v1.max_request_bytes() == api_v1.DEFAULT_MAX_BYTES
    monkeypatch.setenv(api_v1.MAX_BYTES_ENV, "123")
    assert api_v1.max_request_bytes() == 123


def test_ST_363_older_routes_keep_their_own_error_shapes(monkeypatch):
    monkeypatch.setenv(api_v1.MAX_BYTES_ENV, "10")  # the limit is for /api/v1 only

    not_found = _request("GET", "/batch/does-not-exist-anywhere")
    unknown = _request("GET", "/no-such-route")
    invalid = _request("POST", "/metadata")  # required upload missing

    assert unknown.status_code == 404 and unknown.json() == {"detail": "Not Found"}
    assert invalid.status_code == 422 and isinstance(invalid.json()["detail"], list)
    assert "error_class" not in not_found.text


# --------------------------------------------------------------------------- #
# ST-364: version endpoint and the example client
# --------------------------------------------------------------------------- #

def test_ST_364_version_endpoint_uses_the_one_constant():
    resp = _request("GET", "/api/v1/version")

    assert resp.status_code == 200
    assert resp.json() == {"service": "BYOD Synthetic Data Generator",
                           "version": APP_VERSION, "api_version": "v1"}
    assert main.app.version == APP_VERSION
    assert _request("GET", "/api").json()["version"] == APP_VERSION
    assert _request("GET", "/openapi.json").json()["info"]["version"] == APP_VERSION


def test_ST_364_version_is_not_repeated_as_a_literal():
    for rel in ("main.py", "src/api/v1.py"):
        assert f'"{APP_VERSION}"' not in (REPO / rel).read_text(), f"version literal repeated in {rel}"


def _load_example_client():
    path = REPO / "scripts" / "api_client_example.py"
    spec = importlib.util.spec_from_file_location("api_client_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ST_364_example_client_builds_correct_requests(monkeypatch):
    example = _load_example_client()
    client = example.MockDataClient("http://mock.test:9000/", api_key="test-key-not-a-secret")

    health = client.build_request("GET", "/health")
    assert health.full_url == "http://mock.test:9000/health" and health.get_method() == "GET"
    assert client.build_request("GET", "/api/v1/version").get_header("X-api-key") == "test-key-not-a-secret"

    req = client.build_generate_request(csv_text=example.DEMO_CSV, num_rows=5)
    assert req.full_url == "http://mock.test:9000/api/v1/generate" and req.get_method() == "POST"
    assert req.get_header("Content-type") == "application/json"
    assert req.get_header("X-api-key") == "test-key-not-a-secret"
    sent = json.loads(req.data)
    assert sent["csv_text"] == example.DEMO_CSV and sent["num_rows"] == 5
    api_v1.GenerateRequest.model_validate(sent)  # the server would accept it

    req = client.build_generate_request(file_bytes=b"a,b\n1,2\n", format="csv")
    sent = json.loads(req.data)
    assert base64.b64decode(sent["data_content"]) == b"a,b\n1,2\n" and "csv_text" not in sent
    api_v1.GenerateRequest.model_validate(sent)

    with pytest.raises(ValueError):
        client.build_generate_request()

    # base URL and key fall back to the environment; no key means no header
    monkeypatch.setenv("MOCKDATA_API_URL", "http://from-env.test:1234")
    monkeypatch.delenv("MOCKDATA_API_KEY", raising=False)
    from_env = example.MockDataClient()
    assert from_env.build_request("GET", "/health").full_url == "http://from-env.test:1234/health"
    assert from_env.build_request("GET", "/health").get_header("X-api-key") is None


def test_ST_364_example_client_request_is_accepted_by_the_server(fake):
    """Send exactly what the example client would send, through the real app."""
    example = _load_example_client()
    req = example.MockDataClient("http://test").build_generate_request(
        csv_text=example.DEMO_CSV, num_rows=5)

    resp = _request(req.get_method(), "/api/v1/generate", content=req.data,
                    headers=dict(req.header_items()))

    assert resp.status_code == 200, resp.text
    assert resp.json()["shape"] == [5, 3]
    assert resp.json()["columns"] == ["widget_id", "colour", "weight_g"]
