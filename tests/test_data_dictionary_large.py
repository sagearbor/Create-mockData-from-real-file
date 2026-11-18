"""Offline tests for big and oddly shaped data dictionaries.

Motivating failure: a 34 MB HL7 FHIR Bundle of StructureDefinitions was
accepted as "5 columns" (its top-level keys), the whole file went into the LLM
prompt, and the provider answered HTTP 400 (shown to the user as 502).

Covered here:
* shape recognition (existing shapes unchanged; FHIR, JSON Schema,
  Frictionless Table Schema added);
* files that are not data dictionaries are refused with a 4xx in the uniform
  error shape;
* files that define several tables need an explicit ``table`` choice;
* the dictionary text sent to the model stays under a budget, and trimming is
  reported;
* a provider "request too large" rejection becomes a clear, content-free error.

No network, no Azure login, no real LLM. Every dictionary here is invented
(gadgets, widgets, sprockets); nothing resembles real participant data.
"""

import asyncio
import copy
import json
from types import SimpleNamespace

import httpx
import pytest

import main
from src.core import data_dictionary as dd_module
from src.core.data_dictionary import (
    DataDictionary,
    DictionaryTableRequired,
    UnknownDictionaryTable,
    UnrecognizedDictionaryError,
)
from src.core.synthetic_generator import SyntheticDataGenerator

ERROR_KEYS = {"status", "error", "error_class"}

GOOD_CODE = (
    "import pandas as pd\n"
    "def generate_synthetic_data():\n"
    "    return pd.DataFrame({'serial': ['G1', 'G2', 'G3']})\n"
    "result = generate_synthetic_data()\n"
)


# --------------------------------------------------------------------------- #
# Invented fixtures
# --------------------------------------------------------------------------- #

def _el(path, types=(), mn=0, mx="1", short="", binding=None, **extra):
    el = {"id": extra.pop("id", path), "path": path, "min": mn, "max": mx, "short": short}
    if types:
        el["type"] = [{"code": t} for t in types]
    if binding:
        el["binding"] = binding
    el.update(extra)
    return el


GADGET_SD = {
    "resourceType": "StructureDefinition",
    "id": "Gadget",
    "name": "Gadget",
    "type": "Gadget",
    "kind": "resource",
    "snapshot": {"element": [
        _el("Gadget", mx="*", short="An invented gadget"),
        _el("Gadget.id", ["http://hl7.org/fhirpath/System.String"], short="Logical id"),
        _el("Gadget.meta", ["Meta"]),
        _el("Gadget.text", ["Narrative"]),
        _el("Gadget.extension", ["Extension"], mx="*"),
        _el("Gadget.serial", ["string"], mn=1, short="Serial number"),
        _el("Gadget.colour", ["code"], short="red | green | blue",
            binding={"strength": "required",
                     "valueSet": "http://example.org/ValueSet/gadget-colour|1.0"}),
        _el("Gadget.finish", ["code"], short="Surface finish",
            binding={"strength": "example", "valueSet": "http://example.org/ValueSet/finish"}),
        _el("Gadget.weight", ["decimal"], short="Weight in grams"),
        _el("Gadget.madeOn", ["date"], short="Date made"),
        _el("Gadget.retired[x]", ["boolean", "dateTime"], short="Whether retired"),
        _el("Gadget.part", ["BackboneElement"], mx="*", short="Parts"),
        _el("Gadget.part.id", ["http://hl7.org/fhirpath/System.String"]),
        _el("Gadget.part.modifierExtension", ["Extension"], mx="*"),
        _el("Gadget.part.label", ["string"], mn=1, short="Part label"),
        _el("Gadget.part.count", ["positiveInt"], short="How many"),
        _el("Gadget.part.subpart", mx="*", contentReference="#Gadget.part"),
        _el("Gadget.legacyCode", ["string"], mx="0", short="Removed"),
        _el("Gadget.serial", ["string"], id="Gadget.serial:short", sliceName="short"),
    ]},
}

GADGET_COLUMNS = ["id", "serial", "colour", "finish", "weight", "madeOn", "retired",
                  "part.label", "part.count"]

WIDGET_SD = {  # differential only
    "resourceType": "StructureDefinition",
    "id": "Widget",
    "name": "Widget",
    "type": "Widget",
    "kind": "logical",
    "differential": {"element": [
        _el("Widget", short="An invented widget"),
        _el("Widget.size", ["integer"], mn=1, short="Size"),
        _el("Widget.label", ["markdown"], short="Label"),
    ]},
}

BUNDLE = {
    "resourceType": "Bundle",
    "id": "invented-definitions",
    "meta": {"lastUpdated": "2020-01-01T00:00:00Z"},
    "type": "collection",
    "entry": [
        {"fullUrl": "http://example.org/Gadget", "resource": GADGET_SD},
        {"fullUrl": "http://example.org/Widget", "resource": WIDGET_SD},
        {"fullUrl": "http://example.org/op", "resource": {
            "resourceType": "OperationDefinition", "id": "polish", "name": "Polish"}},
    ],
}

JSON_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Sprocket",
    "type": "object",
    "required": ["sprocket_id"],
    "properties": {
        "sprocket_id": {"type": "string", "pattern": "^S[0-9]{3}$"},
        "teeth": {"type": "integer", "minimum": 6, "maximum": 60},
        "pitch_mm": {"type": "number"},
        "coated": {"type": "boolean"},
        "grade": {"type": "string", "enum": ["A", "B", "C"]},
        "made": {"type": "string", "format": "date"},
    },
}

FRICTIONLESS = {
    "fields": [
        {"name": "sprocket_id", "type": "string", "constraints": {"required": True, "unique": True}},
        {"name": "teeth", "type": "integer", "constraints": {"minimum": 6, "maximum": 60}},
        {"name": "grade", "type": "string", "constraints": {"enum": ["A", "B"]}},
    ],
    "primaryKey": "sprocket_id",
}


def _parse(obj, **kw):
    return DataDictionary().parse_dictionary(json.dumps(obj).encode(), "auto",
                                             filename="dict.json", **kw)


# --------------------------------------------------------------------------- #
# Existing shapes: unchanged
# --------------------------------------------------------------------------- #

def test_dict_existing_columns_shape_is_returned_unchanged():
    src = {"columns": {"age": {"type": "integer", "constraints": {"min_value": 0}},
                       "site": {"type": "string", "description": "Invented site"}}}
    assert _parse(src) == src
    assert DataDictionary().parse_dictionary(copy.deepcopy(src)) == src  # dict input, no filename


def test_dict_existing_list_of_named_items_unchanged():
    src = [{"name": "age", "type": "integer"}, {"name": "colour", "type": "string"}]
    assert _parse(src) == {"columns": {"age": {"type": "integer"}, "colour": {"type": "string"}}}


def test_dict_existing_flat_mapping_unchanged():
    src = {"age": "integer", "colour": {"type": "string", "description": "Gadget colour"},
           "notes": "free text"}
    assert _parse(src) == {"columns": {
        "age": {"type": "integer"},
        "colour": {"type": "string", "description": "Gadget colour"},
        "notes": {"type": "free text"}}}


def test_dict_existing_yaml_columns_shape_unchanged():
    text = "columns:\n  age:\n    type: integer\n  colour:\n    type: string\n"
    out = DataDictionary().parse_dictionary(text.encode(), "auto", filename="d.yaml")
    assert out == {"columns": {"age": {"type": "integer"}, "colour": {"type": "string"}}}


def test_dict_existing_csv_dictionary_unchanged():
    text = "column,data_type,description\nage,integer,Age in years\ncolour,string,Colour\n"
    out = DataDictionary().parse_dictionary(text.encode(), "auto", filename="d.csv")
    assert out == {"columns": {"age": {"type": "integer", "description": "Age in years"},
                               "colour": {"type": "string", "description": "Colour"}}}


# --------------------------------------------------------------------------- #
# New shapes
# --------------------------------------------------------------------------- #

def test_dict_fhir_structure_definition_becomes_columns():
    out = _parse(GADGET_SD)
    cols = out["columns"]
    assert list(cols) == GADGET_COLUMNS
    # required (min >= 1) and allowed values from a required code binding
    assert cols["serial"]["constraints"]["required"] is True
    assert cols["colour"]["type"] == "categorical"
    assert cols["colour"]["constraints"]["allowed_values"] == ["red", "green", "blue"]
    # non-required binding: no allowed values, value set named in the description
    assert "allowed_values" not in cols["finish"].get("constraints", {})
    assert "finish" in cols["finish"]["description"]
    # type mapping
    assert cols["weight"]["type"] == "float"
    assert cols["madeOn"]["type"] == "datetime"
    assert cols["part.count"]["type"] == "integer"
    # choice type: one column, first type, all types in the description
    assert cols["retired"]["type"] == "boolean"
    assert "boolean | dateTime" in cols["retired"]["description"]
    # nested backbone child keeps its parent in the name; cardinality noted
    assert cols["part.label"]["constraints"]["required"] is True
    assert "0..*" not in cols["part.label"]["description"]
    assert "1..1" in cols["part.label"]["description"]


def test_dict_fhir_nested_language_and_text_are_data_not_infrastructure():
    sd = copy.deepcopy(GADGET_SD)
    sd["snapshot"]["element"] += [
        _el("Gadget.note", ["BackboneElement"], mx="*"),
        _el("Gadget.note.language", ["code"], mn=1, short="Note language"),
        _el("Gadget.note.text", ["string"], short="Note text"),
        _el("Gadget.note.extension", ["Extension"], mx="*"),
    ]
    cols = _parse(sd)["columns"]
    assert "note.language" in cols and "note.text" in cols
    assert "note.extension" not in cols and "text" not in cols and "language" not in cols


def test_dict_fhir_differential_only_definition_is_used():
    cols = _parse(WIDGET_SD)["columns"]
    assert list(cols) == ["size", "label"]
    assert cols["size"]["type"] == "integer"


def test_dict_fhir_bundle_without_table_lists_the_choices():
    with pytest.raises(DictionaryTableRequired) as exc:
        _parse(BUNDLE)
    assert exc.value.tables == ["Gadget", "Widget"]  # OperationDefinition is not a table
    assert "Gadget" in str(exc.value) and "table" in str(exc.value)
    assert exc.value.http_status == 400


@pytest.mark.parametrize("name", ["Gadget", "gadget", "GADGET"])
def test_dict_fhir_bundle_table_selector(name):
    assert list(_parse(BUNDLE, table=name)["columns"]) == GADGET_COLUMNS


def test_dict_unknown_table_says_what_exists():
    with pytest.raises(UnknownDictionaryTable) as exc:
        _parse(BUNDLE, table="Gadjet")
    assert "Gadget" in str(exc.value)


def test_dict_single_table_ignores_matching_selector_and_rejects_other():
    assert list(_parse(GADGET_SD, table="Gadget")["columns"]) == GADGET_COLUMNS
    with pytest.raises(UnknownDictionaryTable):
        _parse(GADGET_SD, table="Widget")


def test_dict_json_schema_properties():
    cols = _parse(JSON_SCHEMA)["columns"]
    assert list(cols) == ["sprocket_id", "teeth", "pitch_mm", "coated", "grade", "made"]
    assert cols["sprocket_id"]["constraints"] == {"required": True, "pattern": "^S[0-9]{3}$"}
    assert cols["teeth"] == {"type": "integer", "constraints": {"min_value": 6, "max_value": 60}}
    assert cols["pitch_mm"]["type"] == "float"
    assert cols["coated"]["type"] == "boolean"
    assert cols["grade"]["type"] == "categorical"
    assert cols["grade"]["constraints"]["allowed_values"] == ["A", "B", "C"]
    assert cols["made"]["type"] == "datetime"


def test_dict_json_schema_defs_are_tables():
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema",
              "$defs": {"Sprocket": JSON_SCHEMA, "Cog": {"type": "object", "properties": {
                  "cog_id": {"type": "string"}}}}}
    with pytest.raises(DictionaryTableRequired) as exc:
        _parse(schema)
    assert exc.value.tables == ["Sprocket", "Cog"]
    assert list(_parse(schema, table="cog")["columns"]) == ["cog_id"]


def test_dict_frictionless_table_schema():
    cols = _parse(FRICTIONLESS)["columns"]
    assert cols["sprocket_id"]["constraints"] == {"required": True, "unique": True}
    assert cols["teeth"]["constraints"] == {"min_value": 6, "max_value": 60}
    assert cols["grade"]["constraints"]["allowed_values"] == ["A", "B"]


# --------------------------------------------------------------------------- #
# Not a data dictionary: refused
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("obj", [
    {"resourceType": "Bundle", "type": "searchset", "entry": [
        {"resource": {"resourceType": "Gadget", "id": "g1", "serial": "G-1"}}]},
    {"resourceType": "Gadget", "id": "g1", "serial": "G-1"},
    [{"widget_id": "W1", "colour": "red"}, {"widget_id": "W2", "colour": "blue"}],
    {"name": "my-widget-app", "version": "1.0.0", "dependencies": {"leftpad": "^1.0.0"},
     "scripts": {"test": "jest"}},
    {"data": [{"a": 1}, {"a": 2}], "count": 2},
    {},
    [],
    {"columns": {}},
])
def test_dict_unrecognised_json_is_refused(obj):
    with pytest.raises(UnrecognizedDictionaryError) as exc:
        _parse(obj)
    message = str(exc.value)
    assert "does not look like a data dictionary" in message
    assert "FHIR" in message and "JSON Schema" in message  # says what IS accepted
    assert exc.value.http_status == 400


def test_dict_invalid_json_is_refused():
    with pytest.raises(UnrecognizedDictionaryError):
        DataDictionary().parse_dictionary(b"{not json", "auto", filename="d.json")


def test_dict_data_csv_without_definitions_is_refused():
    with pytest.raises(UnrecognizedDictionaryError):
        DataDictionary().parse_dictionary(b"widget_id,colour\nW1,red\nW2,blue\n", "csv",
                                          filename="widgets.csv")


# --------------------------------------------------------------------------- #
# Prompt budget
# --------------------------------------------------------------------------- #

def _huge_dictionary(n=3000):
    cols = {}
    for i in range(n):
        cols[f"gadget_field_{i:05d}"] = {
            "type": "categorical",
            "description": "An invented gadget attribute. " * 20,
            "constraints": {"allowed_values": [f"value_{j}" for j in range(80)],
                            **({"required": True} if i % 10 == 0 else {})},
        }
    return {"columns": cols}


def test_dict_budget_small_dictionary_is_untouched():
    dd = DataDictionary()
    src = {"columns": {"age": {"type": "integer"}}}
    fitted, info = dd.fit_to_prompt_budget(src, max_chars=10_000)
    assert fitted == src and info["trimmed"] is False
    assert info["columns_kept"] == 1 and info["columns_dropped"] == 0


def test_dict_budget_huge_dictionary_is_trimmed_and_reported():
    dd = DataDictionary()
    src = _huge_dictionary()
    before = copy.deepcopy(src)
    fitted, info = dd.fit_to_prompt_budget(src, max_chars=20_000)

    assert src == before  # the caller's dictionary is not modified
    assert dd.dictionary_prompt_chars(fitted) <= 20_000
    assert info["trimmed"] is True
    assert info["columns_total"] == 3000
    assert info["columns_kept"] + info["columns_dropped"] == 3000
    assert info["columns_kept"] == len(fitted["columns"]) > 0
    assert info["prompt_chars_after"] <= info["budget_chars"] == 20_000
    assert "Kept" in info["message"] and "3000" in info["message"]
    # required columns are kept ahead of optional ones
    kept = fitted["columns"]
    assert all(c.get("constraints", {}).get("required") for c in kept.values()) or \
        all(name in kept for name, c in src["columns"].items()
            if c["constraints"].get("required"))


def test_dict_budget_trims_text_before_dropping_columns():
    dd = DataDictionary()
    src = _huge_dictionary(40)
    fitted, info = dd.fit_to_prompt_budget(src, max_chars=16_000)
    assert info["trimmed"] is True and info["columns_dropped"] == 0
    assert len(fitted["columns"]) == 40
    assert "descriptions removed" in info["steps"]
    assert not any("dropped" in step for step in info["steps"])
    assert dd.dictionary_prompt_chars(fitted) <= 16_000


def test_dict_budget_env_var(monkeypatch):
    monkeypatch.delenv(dd_module.PROMPT_BUDGET_ENV, raising=False)
    assert dd_module.prompt_budget_chars() == dd_module.DEFAULT_PROMPT_BUDGET_CHARS
    for bad in ("", "abc", "0", "-3"):
        monkeypatch.setenv(dd_module.PROMPT_BUDGET_ENV, bad)
        assert dd_module.prompt_budget_chars() == dd_module.DEFAULT_PROMPT_BUDGET_CHARS
    monkeypatch.setenv(dd_module.PROMPT_BUDGET_ENV, "5000")
    assert dd_module.prompt_budget_chars() == 5000


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #

class _Capture:
    """Fake chat.completions: records every request, answers with fixed content or error."""

    def __init__(self, content=GOOD_CODE, exc=None):
        self.content, self.exc, self.calls = content, exc, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        msg = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=msg)])


def _generator(completions):
    gen = SyntheticDataGenerator(openai_client=SimpleNamespace(
        chat=SimpleNamespace(completions=completions)))
    gen.cache_manager = SimpleNamespace(
        cache_generation=lambda *a, **k: None, find_similar_cached=lambda *a, **k: None)
    return gen


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # usage logs land in tmp, not the repo
    for name in (dd_module.PROMPT_BUDGET_ENV, dd_module.MAX_BYTES_ENV,
                 "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "LLM_REASONING_EFFORT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(SyntheticDataGenerator, "_reasoning_effort_rejected", False)
    monkeypatch.setattr(main, "data_dictionary", DataDictionary())


@pytest.fixture
def llm(monkeypatch):
    completions = _Capture()
    monkeypatch.setattr(main, "synthetic_generator", _generator(completions))
    return completions


def _post(path, data=None, files=None):
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                     base_url="http://test") as c:
            return await c.post(path, data=data or {}, files=files)
    return asyncio.run(go())


def _json_file(obj, name="dict.json"):
    return {"file": (name, json.dumps(obj).encode(), "application/json")}


def _dict_file(obj, name="dict.json"):
    return {"dictionary_file": (name, json.dumps(obj).encode(), "application/json")}


def _assert_uniform_error(resp, status_code, error_class):
    assert resp.status_code == status_code, resp.text
    body = resp.json()
    assert set(body) == ERROR_KEYS, body
    assert body["status"] == "error" and body["error_class"] == error_class
    return body


def _user_prompts(completions):
    return [next(m["content"] for m in call["messages"] if m["role"] == "user")
            for call in completions.calls]


def test_dict_route_upload_unrecognised_is_400_uniform_shape():
    resp = _post("/dictionary/upload", files=_json_file(
        {"resourceType": "Bundle", "type": "searchset", "entry": []}))
    body = _assert_uniform_error(resp, 400, "UnrecognizedDictionary")
    assert "does not look like a data dictionary" in body["error"]
    assert "columns_defined" not in resp.text
    assert main.data_dictionary.dictionary == {}


def test_dict_route_upload_bundle_asks_for_table_then_select():
    resp = _post("/dictionary/upload", files=_json_file(BUNDLE))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "choose_table"
    assert body["tables"] == ["Gadget", "Widget"]
    assert body["dictionary_format"] == "fhir_bundle"
    assert "columns_defined" not in body
    assert main.data_dictionary.dictionary == {}  # nothing chosen yet, nothing stored

    chosen = _post("/dictionary/table", data={"table": "gadget"})
    assert chosen.status_code == 200, chosen.text
    out = chosen.json()
    assert out["status"] == "success" and out["table"] == "Gadget"
    assert out["columns_defined"] == len(GADGET_COLUMNS)
    assert list(out["dictionary"]["columns"]) == GADGET_COLUMNS
    assert out["prompt_budget"]["trimmed"] is False
    assert list(main.data_dictionary.dictionary["columns"]) == GADGET_COLUMNS


def test_dict_route_select_unknown_table_is_400_uniform_shape():
    _post("/dictionary/upload", files=_json_file(BUNDLE))
    body = _assert_uniform_error(_post("/dictionary/table", data={"table": "Nope"}),
                                 400, "UnknownDictionaryTable")
    assert "Gadget" in body["error"]


def test_dict_route_select_without_upload_is_400():
    _assert_uniform_error(_post("/dictionary/table", data={"table": "Gadget"}),
                          400, "NoDictionary")


def test_dict_route_upload_with_table_field():
    resp = _post("/dictionary/upload", data={"table": "Widget"}, files=_json_file(BUNDLE))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "success" and body["table"] == "Widget"
    assert body["columns_defined"] == 2


def test_dict_route_upload_existing_shape_response_unchanged():
    src = {"columns": {"age": {"type": "integer"}}}
    body = _post("/dictionary/upload", files=_json_file(src)).json()
    assert body["status"] == "success"
    assert body["filename"] == "dict.json"
    assert body["columns_defined"] == 1 and body["dictionary"] == src


def test_dict_route_upload_too_large_is_413(monkeypatch):
    monkeypatch.setenv(dd_module.MAX_BYTES_ENV, "100")
    resp = _post("/dictionary/upload", files=_json_file(_huge_dictionary(5)))
    _assert_uniform_error(resp, 413, "DictionaryTooLarge")


def test_dict_route_generate_bundle_without_table_lists_names(llm):
    resp = _post("/generate-with-dictionary", data={"preview_only": "true", "num_rows": "3"},
                 files=_dict_file(BUNDLE))
    body = _assert_uniform_error(resp, 400, "DictionaryTableRequired")
    assert "Gadget" in body["error"] and "Widget" in body["error"]
    assert llm.calls == []  # no AI call was made


def test_dict_route_generate_bundle_with_table(llm):
    resp = _post("/generate-with-dictionary",
                 data={"preview_only": "true", "num_rows": "3", "table": "Gadget"},
                 files=_dict_file(BUNDLE))
    assert resp.status_code == 200, resp.text
    assert resp.json()["dictionary_trimming"]["trimmed"] is False
    prompt = _user_prompts(llm)[0]
    assert "part.label" in prompt and "serial" in prompt
    assert "Widget" not in prompt and "entry" not in prompt


def test_dict_route_generate_unrecognised_is_400_not_502(llm):
    resp = _post("/generate-with-dictionary", data={"preview_only": "true"},
                 files=_dict_file({"resourceType": "Gadget", "id": "g1"}))
    _assert_uniform_error(resp, 400, "UnrecognizedDictionary")
    assert llm.calls == []


def test_dict_route_generate_stays_under_budget_and_reports_trim(monkeypatch, llm):
    monkeypatch.setenv(dd_module.PROMPT_BUDGET_ENV, "20000")
    big = _huge_dictionary()
    full_chars = DataDictionary().dictionary_prompt_chars(big)
    assert full_chars > 1_000_000  # the untrimmed dictionary would be enormous

    resp = _post("/generate-with-dictionary",
                 data={"preview_only": "true", "num_rows": "3", "use_stored_dictionary": "false"},
                 files=_dict_file(big))
    assert resp.status_code == 200, resp.text
    trim = resp.json()["dictionary_trimming"]
    assert trim["trimmed"] is True and trim["columns_dropped"] > 0
    assert trim["columns_kept"] + trim["columns_dropped"] == 3000
    assert resp.json()["generation_info"]["dictionary_trimming"] == trim
    template_chars = 4000  # fixed prompt wording around the dictionary
    for prompt in _user_prompts(llm):
        assert len(prompt) <= 20000 + template_chars
    # the stored dictionary is the full one; only the copy sent to the model is trimmed
    assert len(main.data_dictionary.dictionary["columns"]) == 3000


def test_dict_route_generate_existing_shape_still_works(llm):
    src = {"columns": {"serial": {"type": "string", "description": "Gadget serial"}}}
    resp = _post("/generate-with-dictionary", data={"preview_only": "true", "num_rows": "3"},
                 files=_dict_file(src))
    assert resp.status_code == 200, resp.text
    assert resp.json()["dictionary_applied"] is True
    assert "Gadget serial" in _user_prompts(llm)[0]


class _TooBig(Exception):
    status_code = 400
    code = "context_length_exceeded"


@pytest.mark.parametrize("exc", [
    _TooBig("This model's maximum context length is 1 tokens. secret prompt text"),
    type("_Http413", (Exception,), {"status_code": 413})("secret prompt text"),
])
def test_dict_route_model_says_too_large_is_clear_413(monkeypatch, exc):
    completions = _Capture(exc=exc)
    monkeypatch.setattr(main, "synthetic_generator", _generator(completions))
    resp = _post("/generate-with-dictionary", data={"preview_only": "true", "num_rows": "3"},
                 files=_dict_file({"columns": {"serial": {"type": "string"}}}))
    body = _assert_uniform_error(resp, 413, "AIRequestTooLargeError")
    assert "too large" in body["error"]
    assert dd_module.PROMPT_BUDGET_ENV in body["error"]
    assert "secret prompt text" not in resp.text and "maximum context" not in resp.text


# --------------------------------------------------------------------------- #
# More no-regression: Excel, text, and shapes whose prompt rendering is fragile
# --------------------------------------------------------------------------- #

def test_dict_existing_excel_dictionary_unchanged():
    import io
    import pandas as pd
    pytest.importorskip("openpyxl")
    buf = io.BytesIO()
    pd.DataFrame({"Variable": ["age", "colour"], "Type": ["integer", "text"],
                  "Description": ["Gadget age", "Gadget colour"]}).to_excel(buf, index=False)
    out = DataDictionary().parse_dictionary(buf.getvalue(), "auto", filename="d.xlsx")
    assert out == {"columns": {"age": {"type": "integer", "description": "Gadget age"},
                               "colour": {"type": "string", "description": "Gadget colour"}}}


def test_dict_existing_text_dictionary_unchanged():
    text = "age: integer age of the gadget\nmade_on: date the gadget was made\n"
    out = DataDictionary().parse_dictionary(text.encode(), "text", filename="d.txt")
    assert out == {"columns": {
        "age": {"description": "integer age of the gadget", "type": "integer"},
        "made_on": {"description": "date the gadget was made", "type": "datetime"}}}


@pytest.mark.parametrize("name,body,columns", [
    ("a.json", b'{"columns": {"age": "integer"}}', 1),
    ("b.csv", b"column,data_type,constraint\nage,integer,min 0\ncolour,string,\n", 2),
])
def test_dict_route_upload_of_unusual_existing_shapes_still_loads(name, body, columns):
    resp = _post("/dictionary/upload", files={"file": (name, body, "application/octet-stream")})
    assert resp.status_code == 200, resp.text
    assert resp.json()["columns_defined"] == columns


def test_dict_route_preview_with_date_column_is_json(monkeypatch):
    """A generated date column (pandas Timestamp) must not break the preview response."""
    import pandas as pd

    df = pd.DataFrame({"id": [1, 2], "birthDate": pd.to_datetime(["1980-01-02", None])})
    stub = SimpleNamespace(generate=lambda **k: (df, {}))
    monkeypatch.setattr(main, "synthetic_generator", stub)
    resp = _post("/generate-with-dictionary",
                 data={"preview_only": "true", "num_rows": "2", "table": "Widget"},
                 files=_dict_file(BUNDLE))
    assert resp.status_code == 200, resp.text
    rows = resp.json()["preview"]
    assert rows[0]["birthDate"].startswith("1980-01-02") and rows[1]["birthDate"] is None


@pytest.mark.parametrize("fmt", ["csv", "json", "excel"])
def test_dict_route_download_after_preview_sends_the_previewed_rows(monkeypatch, fmt):
    """Download with the preview id returns the preview's rows without a second generation."""
    import pandas as pd

    total = main.PREVIEW_ROWS + 1  # one more than the preview shows
    calls = []

    def generate(**k):
        calls.append(k)
        n = len(calls)
        return pd.DataFrame({"id": [n] * total, "birthDate": pd.to_datetime(["1980-01-02"] * total)}), {}

    monkeypatch.setattr(main, "synthetic_generator", SimpleNamespace(generate=generate))
    monkeypatch.setattr(main, "_dictionary_previews", {})
    common = {"num_rows": str(total), "table": "Widget", "output_format": fmt}
    prev = _post("/generate-with-dictionary", data={**common, "preview_only": "true"}, files=_dict_file(BUNDLE))
    assert prev.status_code == 200, prev.text
    assert prev.json()["total_rows"] == total and len(prev.json()["preview"]) == main.PREVIEW_ROWS
    down = _post("/generate-with-dictionary",
                 data={**common, "preview_only": "false", "preview_id": prev.json()["preview_id"]})
    assert down.status_code == 200, down.text
    assert len(calls) == 1  # the download did not generate again
    # someone without the id gets a newly generated set, never the previewed rows
    other = _post("/generate-with-dictionary", data={**common, "preview_only": "false", "preview_id": "guess"})
    assert other.status_code == 200 and len(calls) == 2
    if fmt == "csv":
        assert other.text.strip().splitlines()[1].startswith("2,")
    if fmt == "csv":
        assert len(down.text.strip().splitlines()) == total + 1 and "1980-01-02" in down.text
    elif fmt == "json":
        rows = down.json()
        assert isinstance(rows, list) and len(rows) == total and rows[0]["birthDate"].startswith("1980-01-02")
    else:
        assert down.content[:2] == b"PK"


def test_dict_route_download_without_preview_still_generates(monkeypatch):
    import pandas as pd

    calls = []

    def generate(**k):
        calls.append(k)
        return pd.DataFrame({"id": [1, 2]}), {}

    monkeypatch.setattr(main, "synthetic_generator", SimpleNamespace(generate=generate))
    monkeypatch.setattr(main, "_dictionary_previews", {})
    down = _post("/generate-with-dictionary",
                 data={"num_rows": "2", "table": "Widget", "preview_only": "false", "preview_id": "unknown"},
                 files=_dict_file(BUNDLE))
    assert down.status_code == 200 and len(calls) == 1


def _df_code(columns):
    cols = ", ".join(f"'{c}': [1] * 3" for c in columns)
    return f"import pandas as pd\nresult = pd.DataFrame({{{cols}}})\n"


class _Sequence:
    """Fake chat.completions answering with each given code in turn."""

    def __init__(self, *contents):
        self.contents, self.calls = list(contents), []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.contents[min(len(self.calls), len(self.contents)) - 1]
        msg = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=msg)])


def _dict_only_metadata(names):
    return {"structure": {"columns": [], "shape": {"rows": 3, "columns": len(names)}},
            "statistics": {}, "expected_columns": list(names)}


def test_generator_dictionary_only_matching_columns_is_one_model_call():
    seq = _Sequence(_df_code(["a", "b"]))
    df, info = _generator(seq).generate(metadata=_dict_only_metadata(["a", "b"]), num_rows=3)
    assert list(df.columns) == ["a", "b"] and len(seq.calls) == 1 and "regenerated" not in info


def test_generator_code_that_fails_to_run_is_retried_once():
    seq = _Sequence("raise SystemExit(1)\n", _df_code(["a", "b"]))
    df, info = _generator(seq).generate(metadata=_dict_only_metadata(["a", "b"]), num_rows=3)
    assert list(df.columns) == ["a", "b"] and len(seq.calls) == 2 and info["retried_after_failure"]


def test_generator_keeps_first_result_when_regeneration_cannot_run():
    seq = _Sequence(_df_code(["a", "extra"]), "raise SystemExit(1)\n")
    df, info = _generator(seq).generate(metadata=_dict_only_metadata(["a", "b"]), num_rows=3)
    assert list(df.columns) == ["a", "extra"] and info["structure_mismatch"] is True


# --------------------------------------------------------------------------- #
# Code that fails to run: never cached, dropped if cached, corrected with its error
# --------------------------------------------------------------------------- #
def _real_cache_generator(completions, tmp_path):
    from src.core.cache_manager import CacheManager
    gen = SyntheticDataGenerator(openai_client=SimpleNamespace(
        chat=SimpleNamespace(completions=completions)))
    gen.cache_manager = CacheManager(cache_dir=tmp_path / "cache")
    return gen


def _cached_codes(gen):
    return [open(e["cache_file"]).read() for entries in gen.cache_manager.cache_index.values() for e in entries]


def test_code_that_fails_to_run_is_never_cached(tmp_path):
    seq = _Sequence("raise SystemExit(1)\n", _df_code(["a", "b"]))
    gen = _real_cache_generator(seq, tmp_path)
    meta = _dict_only_metadata(["a", "b"])
    gen.generate(metadata=meta, num_rows=3)
    codes = _cached_codes(gen)
    assert len(codes) == 1 and "SystemExit" not in codes[0]
    # the next request for the same shape reuses the working code: no model call
    df, info = gen.generate(metadata=meta, num_rows=3)
    assert info["method"] == "cached" and len(seq.calls) == 2 and list(df.columns) == ["a", "b"]


def test_cached_code_that_fails_is_dropped_and_replaced(tmp_path):
    seq = _Sequence(_df_code(["a", "b"]))
    gen = _real_cache_generator(seq, tmp_path)
    meta = _dict_only_metadata(["a", "b"])
    gen.cache_manager.cache_generation(meta, "raise SystemExit(1)\n")  # a poisoned entry
    df, info = gen.generate(metadata=meta, num_rows=3)
    assert list(df.columns) == ["a", "b"] and info["method"] == "llm" and len(seq.calls) == 1
    codes = _cached_codes(gen)
    assert len(codes) == 1 and "SystemExit" not in codes[0]


def test_retry_tells_the_model_what_went_wrong_and_stops_after_two_corrections():
    seq = _Sequence("raise ValueError('boom-marker')\n")
    gen = _generator(seq)
    with pytest.raises(Exception) as exc:
        gen.generate(metadata=_dict_only_metadata(["a"]), num_rows=3)
    assert len(seq.calls) == 3  # first try + two corrections
    assert "boom-marker" not in seq.calls[0]["messages"][1]["content"]
    assert "boom-marker" in seq.calls[1]["messages"][1]["content"]
    assert "boom-marker" not in str(exc.value)  # the error text never reaches the user


def test_seeding_keeps_module_level_code_runnable():
    gen = _generator(_Sequence(""))
    for code in ("fake = Faker()\nx = 1\n",
                 "from __future__ import annotations\nx = 1\n",
                 "def generate_synthetic_data(\n    n=3,\n):\n    return n\n"):
        compile(gen._inject_random_seed(code, 7), "<t>", "exec")
    seeded = gen._inject_random_seed("def f():\n    fake = Faker()\n    return fake\n", 7)
    assert "    fake.seed_instance(7)" in seeded


def test_generate_route_falls_back_when_cached_script_fails(monkeypatch):
    import pandas as pd
    from src.core.synthetic_generator import CodeExecutionError

    forgotten = []

    def boom(code):
        raise CodeExecutionError("generated code failed in the sandbox (exit 1)")

    stub = SimpleNamespace(
        _execute_generation_code=boom, forget_cached=lambda entry: forgotten.append(entry),
        generate=lambda **k: (pd.DataFrame({"a": [1, 2]}), {"method": "llm"}),
        _log_usage=lambda *a, **k: None, openai_client=object())
    monkeypatch.setattr(main, "synthetic_generator", stub)
    monkeypatch.setattr(main.cache_manager, "find_similar_cached",
                        lambda *a, **k: {"generation_code": "x", "cache_file": "nope"})
    resp = _post("/generate", data={"output_format": "csv", "preview_only": "false"},
                 files={"file": ("d.csv", b"a\n1\n2\n", "text/csv")})
    assert resp.status_code == 200, resp.text
    assert len(forgotten) == 1 and resp.text.strip().splitlines() == ["a", "1", "2"]
