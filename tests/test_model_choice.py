"""Choosing the AI model per request (ADP-43) and the cache rules that go with it (ADP-61).

* ``GET /api/models`` lists the server default and the allow-list (``LLM_ALLOWED_MODELS``).
* Every generation route passes the chosen model to the generator and refuses any other
  name with 400 before the generator is called.
* The model is an argument all the way down to the completions call (never a shared setting).
* A cached script is reused only for the same model, privacy mode and row count, and only
  if its file still has the text that was cached.

No server, no network, no real model: the app is driven in-process with fake completions.
"""

import asyncio
import base64
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import httpx
import pandas as pd
import pytest

import main
from src.api import v1 as api_v1
from src.core import generation_service, models
from src.core import synthetic_generator as sg
from src.core.cache_manager import CacheManager, cache_variant
from src.core.metadata_extractor import MetadataExtractor
from src.core.synthetic_generator import SyntheticDataGenerator
from src.utils.config import settings

DEFAULT = "gpt-5-nano"
OTHER = "gpt-5.5"
NOT_ALLOWED = "Mistral-Large-3"
CSV = b"a,b\n1,x\n2,y\n3,z\n"
DICTIONARY = {"columns": {"a": {"type": "integer"}, "b": {"type": "string"}}}
ERROR_KEYS = {"status", "error", "error_class"}
WEB = Path(__file__).resolve().parents[1] / "src" / "web"


def _df_code(columns=("a", "b"), rows=3, marker=""):
    cols = ", ".join(f"'{c}': [1] * {rows}" for c in columns)
    return f"import pandas as pd\n# {marker}\nresult = pd.DataFrame({{{cols}}})\n"


class _Sequence:
    """Fake chat.completions: records every request, answers with each code in turn."""

    def __init__(self, *contents):
        self.contents, self.calls = list(contents), []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.contents[min(len(self.calls), len(self.contents)) - 1]
        msg = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=msg)])


def _generator(completions, cache=None):
    gen = SyntheticDataGenerator(openai_client=SimpleNamespace(
        chat=SimpleNamespace(completions=completions)))
    gen.cache_manager = cache or SimpleNamespace(
        cache_generation=lambda *a, **k: None, find_similar_cached=lambda *a, **k: None)
    return gen


class _Recorder:
    """Stub generator: records every generate() call, returns a tiny frame."""

    openai_client = object()

    def __init__(self):
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return pd.DataFrame({"a": [1, 2]}), {"method": "llm", "model": kwargs.get("model")}

    def _log_usage(self, *args, **kwargs):
        pass


def _metadata(names=("a", "b"), rows=3):
    return {"structure": {"columns": [], "shape": {"rows": rows, "columns": len(names)}},
            "statistics": {}, "expected_columns": list(names)}


def _file_metadata(mode):
    return MetadataExtractor(safety_mode=mode).extract(pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]}))


def _cached_codes(cache):
    return [open(e["cache_file"]).read() for entries in cache.cache_index.values() for e in entries]


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # usage logs land in tmp, not the repo
    for name in (models.ALLOWED_MODELS_ENV, "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY",
                 "LLM_REASONING_EFFORT", api_v1.API_KEY_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(settings, "azure_openai_chat_deployment", DEFAULT)
    monkeypatch.setattr(SyntheticDataGenerator, "_reasoning_effort_rejected", False)
    monkeypatch.setattr(main, "_dictionary_uploads", {})
    monkeypatch.setattr(main, "_dictionary_previews", {})
    monkeypatch.setattr(main.cache_manager, "find_similar_cached", lambda *a, **k: None)


@pytest.fixture
def recorder(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(main, "synthetic_generator", rec)
    return rec


def _request(method, path, **kwargs):
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                     base_url="http://test") as c:
            return await c.request(method, path, **kwargs)
    return asyncio.run(go())


def _post(path, data=None, files=None):
    return _request("POST", path, data=data or {}, files=files)


def _sse_result(resp):
    events = [json.loads(line[len("data: "):]) for line in resp.text.splitlines()
              if line.startswith("data: ")]
    return events[-1]


# --------------------------------------------------------------------------- #
# The allow-list: one place, read from settings and env on every call
# --------------------------------------------------------------------------- #

def test_models_endpoint_lists_the_default_list_with_the_default_first():
    resp = _request("GET", "/api/models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["default"] == DEFAULT
    assert [m["name"] for m in body["models"]] == list(models.DEFAULT_ALLOWED_MODELS)
    assert all(set(m) == {"name", "label", "note"} for m in body["models"])
    # labels are the names; the only note is "default"
    assert all(m["label"] == m["name"] for m in body["models"])
    assert [m["note"] for m in body["models"]] == ["default"] + [""] * 6


def test_default_list_is_the_seven_probed_models_and_not_the_one_that_failed():
    assert models.DEFAULT_ALLOWED_MODELS == (
        "gpt-5-nano", "gpt-5.4-nano", "gpt-5.4-mini", "gpt-5.5",
        "gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol")
    assert NOT_ALLOWED not in models.allowed_models()


def test_models_endpoint_uses_the_env_list(monkeypatch):
    monkeypatch.setenv(models.ALLOWED_MODELS_ENV, " alpha , beta,, alpha ")
    body = _request("GET", "/api/models").json()
    # the configured default is always allowed, and listed first
    assert [m["name"] for m in body["models"]] == [DEFAULT, "alpha", "beta"]
    assert body["default"] == DEFAULT
    assert "gpt-5.5" not in models.allowed_models()


def test_default_deployment_is_always_allowed_even_if_not_listed(monkeypatch):
    monkeypatch.setattr(settings, "azure_openai_chat_deployment", "house-model")
    monkeypatch.setenv(models.ALLOWED_MODELS_ENV, "alpha")
    assert models.allowed_models() == ["house-model", "alpha"]
    assert models.resolve_model("house-model") == "house-model"
    assert models.resolve_model(None) == "house-model"
    monkeypatch.delenv(models.ALLOWED_MODELS_ENV)
    assert models.allowed_models() == ["house-model", *models.DEFAULT_ALLOWED_MODELS]


@pytest.mark.parametrize("empty", [None, "", "   "])
def test_empty_or_absent_model_means_the_server_default(empty):
    assert models.resolve_model(empty) == DEFAULT


def test_resolve_model_refuses_other_names_and_says_which_are_allowed():
    assert models.resolve_model(f" {OTHER} ") == OTHER
    with pytest.raises(models.ModelNotAllowed) as refused:
        models.resolve_model(NOT_ALLOWED)
    assert isinstance(refused.value, ValueError)
    for name in models.DEFAULT_ALLOWED_MODELS:
        assert name in str(refused.value)


# --------------------------------------------------------------------------- #
# Form routes: the chosen model reaches the generator; other names are 400 first
# --------------------------------------------------------------------------- #

def _route_request(path, **form):
    if path == "/generate-with-dictionary":
        files = {"dictionary_file": ("d.json", json.dumps(DICTIONARY).encode(), "application/json")}
    else:
        files = {"file": ("d.csv", CSV, "text/csv")}
    return _post(path, data={"output_format": "json", **form}, files=files)


ROUTES = ["/generate", "/generate-sse", "/generate-with-dictionary"]


@pytest.mark.parametrize("path", ROUTES)
@pytest.mark.parametrize("preview", ["true", "false"])
def test_route_passes_the_chosen_model_to_the_generator(recorder, path, preview):
    resp = _route_request(path, model=OTHER, preview_only=preview, use_cache="false")
    assert resp.status_code == 200, resp.text
    assert recorder.calls and all(call["model"] == OTHER for call in recorder.calls)
    body = _sse_result(resp) if path == "/generate-sse" else resp.json()
    assert body["generation_info"]["model"] == OTHER


@pytest.mark.parametrize("path", ROUTES)
@pytest.mark.parametrize("form", [{}, {"model": ""}])
def test_route_without_a_model_uses_the_server_default(recorder, path, form):
    resp = _route_request(path, **form)
    assert resp.status_code == 200, resp.text
    assert recorder.calls and all(call["model"] == DEFAULT for call in recorder.calls)


@pytest.mark.parametrize("path", ROUTES)
def test_route_refuses_a_model_not_on_the_list_before_generating(recorder, path):
    resp = _route_request(path, model=NOT_ALLOWED)
    assert resp.status_code == 400, resp.text  # a real 400, also for the SSE route
    detail = resp.json()["detail"]
    assert NOT_ALLOWED in detail and DEFAULT in detail and OTHER in detail
    assert recorder.calls == []


def test_every_file_of_a_multi_file_request_uses_the_chosen_model(recorder):
    resp = _route_request("/generate", model=OTHER, file_count="3", output_format="csv", use_cache="false")
    assert resp.status_code == 200
    assert [call["model"] for call in recorder.calls] == [OTHER] * 3
    assert resp.headers["x-generation-model"] == OTHER


def test_dictionary_download_reuses_the_preview_only_for_the_same_model(recorder):
    preview = _route_request("/generate-with-dictionary", model=OTHER, preview_only="true").json()
    ids = {"dictionary_id": preview["dictionary_id"], "preview_id": preview["preview_id"],
           "preview_only": "false", "output_format": "csv"}
    same = _post("/generate-with-dictionary", data={**ids, "model": OTHER})
    assert same.status_code == 200 and len(recorder.calls) == 1  # the preview's rows
    assert same.headers["x-generation-model"] == OTHER
    other = _post("/generate-with-dictionary", data={**ids, "model": "gpt-5.4-mini"})
    assert other.status_code == 200 and len(recorder.calls) == 2
    assert recorder.calls[-1]["model"] == "gpt-5.4-mini"


# --------------------------------------------------------------------------- #
# /api/v1, and the service layer that MCP and A2A call
# --------------------------------------------------------------------------- #

def _v1(body):
    return _request("POST", "/api/v1/generate", json=body)


def test_api_v1_passes_the_chosen_model_and_reports_it(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(generation_service, "_get_generator", lambda: rec)
    resp = _v1({"csv_text": CSV.decode(), "model": OTHER})
    assert resp.status_code == 200, resp.text
    assert rec.calls[0]["model"] == OTHER
    assert resp.json()["generation_info"]["model"] == OTHER
    assert _v1({"csv_text": CSV.decode()}).status_code == 200
    assert rec.calls[1]["model"] == DEFAULT


def test_api_v1_refuses_a_bad_model_in_the_uniform_error_shape(monkeypatch):
    def must_not_build():
        raise AssertionError("the generator must not be built for a refused model")

    monkeypatch.setattr(generation_service, "_get_generator", must_not_build)
    resp = _v1({"csv_text": CSV.decode(), "model": NOT_ALLOWED})
    assert resp.status_code == 400
    body = resp.json()
    assert set(body) == ERROR_KEYS
    assert body["status"] == "error" and body["error_class"] == "ModelNotAllowed"
    assert NOT_ALLOWED in body["error"] and DEFAULT in body["error"]


def test_api_v1_model_field_is_optional_and_described():
    field = api_v1.GenerateRequest.model_fields["model"]
    assert field.default is None and not field.is_required() and field.description


def test_service_layer_refuses_a_bad_model_before_reading_the_file(monkeypatch):
    """generation_service.generate is what the MCP tool and the A2A agent call."""
    monkeypatch.setattr(generation_service, "_get_generator",
                        lambda: (_ for _ in ()).throw(AssertionError("must not be built")))
    result = generation_service.generate({"data_content": "not base64 at all", "model": NOT_ALLOWED})
    assert result["status"] == "error" and result["error_class"] == "ModelNotAllowed"
    assert NOT_ALLOWED in result["error"]


def test_service_layer_passes_the_model_through(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(generation_service, "_get_generator", lambda: rec)
    payload = {"data_content": base64.b64encode(CSV).decode(), "file_name": "d.csv", "model": OTHER}
    result = generation_service.generate(payload)
    assert result["status"] == "success" and rec.calls[0]["model"] == OTHER
    assert result["generation_info"]["model"] == OTHER


# --------------------------------------------------------------------------- #
# The generator: the model is an argument down to the completions call
# --------------------------------------------------------------------------- #

def test_completions_receive_the_chosen_model_also_on_the_correction_retry():
    seq = _Sequence("raise SystemExit(1)\n", _df_code())
    df, info = _generator(seq).generate(metadata=_metadata(), num_rows=3, model=OTHER)
    assert len(seq.calls) == 2 and [c["model"] for c in seq.calls] == [OTHER, OTHER]
    assert info["model"] == OTHER and info["retried_after_failure"] is True


def test_completions_receive_the_chosen_model_on_the_wrong_columns_regeneration():
    seq = _Sequence(_df_code(["a", "extra"]), _df_code())
    df, info = _generator(seq).generate(metadata=_metadata(), num_rows=3, model=OTHER)
    assert [c["model"] for c in seq.calls] == [OTHER, OTHER]
    assert info["regenerated"] is True and info["model"] == OTHER


def test_generator_without_a_model_uses_the_setting_at_call_time(monkeypatch):
    seq = _Sequence(_df_code())
    gen = _generator(seq)
    _, info = gen.generate(metadata=_metadata(), num_rows=3)
    monkeypatch.setattr(settings, "azure_openai_chat_deployment", "gpt-5.4-nano")
    _, info2 = gen.generate(metadata=_metadata(), num_rows=3)
    assert [c["model"] for c in seq.calls] == [DEFAULT, "gpt-5.4-nano"]
    assert (info["model"], info2["model"]) == (DEFAULT, "gpt-5.4-nano")


def test_route_response_reports_the_model_through_the_real_generator(monkeypatch):
    seq = _Sequence(_df_code())
    monkeypatch.setattr(main, "synthetic_generator", _generator(seq))
    resp = _route_request("/generate", model=OTHER, preview_only="true")
    assert resp.status_code == 200, resp.text
    assert resp.json()["generation_info"]["model"] == OTHER
    assert seq.calls[0]["model"] == OTHER


def test_two_requests_at_once_each_keep_their_own_model():
    """No shared mutable setting: both calls are inside the model call at the same time."""
    both_inside = threading.Barrier(2, timeout=20)

    class _Together:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            both_inside.wait()
            self.calls.append(kwargs["model"])
            # each model writes code that names itself, so a mix-up would show in the rows
            code = f"import pandas as pd\nresult = pd.DataFrame({{'a': ['{kwargs['model']}'] * 3, 'b': [1] * 3}})\n"
            return SimpleNamespace(choices=[SimpleNamespace(
                finish_reason="stop", message=SimpleNamespace(content=code))])

    completions = _Together()
    gen = _generator(completions)
    results, errors = {}, []

    def run(model):
        try:
            results[model] = gen.generate(metadata=_metadata(), num_rows=3, model=model)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(m,)) for m in (OTHER, "gpt-5.6-sol")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not errors
    assert sorted(completions.calls) == sorted([OTHER, "gpt-5.6-sol"])
    for model, (df, info) in results.items():
        assert info["model"] == model and set(df["a"]) == {model}
    assert settings.azure_openai_chat_deployment == DEFAULT  # never written per request


# --------------------------------------------------------------------------- #
# Reasoning models keep their output budget
# --------------------------------------------------------------------------- #

def test_completion_budget_constant_is_40000():
    assert sg.LLM_MAX_COMPLETION_TOKENS == 40000


@pytest.mark.parametrize("name", models.DEFAULT_ALLOWED_MODELS)
def test_every_default_model_is_a_reasoning_model_with_the_full_budget(name):
    assert sg._REASONING_MODEL_RE.match(name), f"{name} must be classified as a reasoning model"
    seq = _Sequence(_df_code())
    _generator(seq).generate(metadata=_metadata(), num_rows=3, model=name)
    request = seq.calls[0]
    assert request["model"] == name
    assert request["max_completion_tokens"] >= 40000
    assert "max_tokens" not in request and "temperature" not in request
    assert request["reasoning_effort"] == "low"


# --------------------------------------------------------------------------- #
# Cache: same model, same privacy mode, unaltered script
# --------------------------------------------------------------------------- #

def test_script_cached_for_one_model_is_not_reused_for_another(tmp_path):
    seq = _Sequence(_df_code(marker="first"), _df_code(marker="second"))
    gen = _generator(seq, CacheManager(cache_dir=tmp_path / "cache"))
    meta = _metadata()
    _, first = gen.generate(metadata=meta, num_rows=3, model=DEFAULT)
    assert first["method"] == "llm" and len(seq.calls) == 1
    _, second = gen.generate(metadata=meta, num_rows=3, model=OTHER)  # asks the model again
    assert second["method"] == "llm" and second["model"] == OTHER and len(seq.calls) == 2
    assert seq.calls[1]["model"] == OTHER
    # each is then served from the cache for its own model, and says who wrote it
    _, again_default = gen.generate(metadata=meta, num_rows=3, model=DEFAULT)
    _, again_other = gen.generate(metadata=meta, num_rows=3, model=OTHER)
    assert len(seq.calls) == 2
    assert (again_default["method"], again_default["model"]) == ("cached", DEFAULT)
    assert (again_other["method"], again_other["model"]) == ("cached", OTHER)


def test_extractor_stamps_the_privacy_mode_without_changing_the_format_hash(tmp_path):
    cache = CacheManager(cache_dir=tmp_path / "cache")
    strict, balanced = _file_metadata("strict"), _file_metadata("balanced")
    assert strict["privacy_mode"] == "strict" and balanced["privacy_mode"] == "balanced"
    assert cache.generate_format_hash(strict) == cache.generate_format_hash(balanced)
    assert cache.generate_full_hash(strict) != cache.generate_full_hash(balanced)
    assert cache.generate_metadata_embedding(strict).shape == (128,)
    assert cache_variant(strict, DEFAULT) != cache_variant(balanced, DEFAULT)
    assert cache_variant(strict, DEFAULT) != cache_variant(strict, OTHER)


def test_script_cached_in_one_privacy_mode_is_not_offered_in_another(tmp_path):
    """Checked on the loose (similarity) lookup main.py uses, where the full hash is not consulted."""
    cache = CacheManager(cache_dir=tmp_path / "cache")
    permissive, strict = _file_metadata("permissive"), _file_metadata("strict")
    cache.cache_generation(permissive, _df_code(), num_rows=3,
                           variant=cache_variant(permissive, DEFAULT), model=DEFAULT)
    assert cache.find_similar_cached(strict, 0.0, num_rows=3,
                                     variant=cache_variant(strict, DEFAULT)) is None
    hit = cache.find_similar_cached(permissive, 0.0, num_rows=3,
                                    variant=cache_variant(permissive, DEFAULT))
    assert hit and hit["model"] == DEFAULT and hit["generation_code"] == _df_code()


def test_generator_asks_again_for_another_privacy_mode_and_reuses_for_the_same(tmp_path):
    seq = _Sequence(_df_code(marker="strict"), _df_code(marker="balanced"))
    gen = _generator(seq, CacheManager(cache_dir=tmp_path / "cache"))
    gen.generate(metadata=_file_metadata("strict"), num_rows=3)
    _, other_mode = gen.generate(metadata=_file_metadata("balanced"), num_rows=3)
    assert other_mode["method"] == "llm" and len(seq.calls) == 2
    _, same_mode = gen.generate(metadata=_file_metadata("strict"), num_rows=3)
    assert same_mode["method"] == "cached" and len(seq.calls) == 2


@pytest.mark.parametrize("path", ["/generate", "/generate-sse"])
@pytest.mark.parametrize("cache_mode", ["structure", "structure_stats"])
def test_route_cache_lookup_keeps_models_and_privacy_modes_apart(monkeypatch, tmp_path, path, cache_mode):
    """main.py's own lookup (then _run_cached_code) applies the model and the privacy mode."""
    cache = CacheManager(cache_dir=tmp_path / "cache")
    seq = _Sequence(*[_df_code(marker=f"call {i}") for i in range(1, 6)])
    monkeypatch.setattr(main, "cache_manager", cache)  # one index for the route and the generator
    monkeypatch.setattr(main, "synthetic_generator", _generator(seq, cache))

    def ask(**form):
        resp = _route_request(path, preview_only="true", cache_mode=cache_mode,
                              match_threshold="0.0", num_rows="3", **form)
        assert resp.status_code == 200, resp.text
        body = _sse_result(resp) if path == "/generate-sse" else resp.json()
        assert "error" not in body, body
        return body["generation_info"]

    first = ask(model=DEFAULT, safety_mode="balanced")
    assert first["method"] == "llm" and len(seq.calls) == 1
    other_model = ask(model=OTHER, safety_mode="balanced")
    assert other_model["method"] == "llm" and other_model["model"] == OTHER and len(seq.calls) == 2
    other_mode = ask(model=DEFAULT, safety_mode="strict")
    assert other_mode["method"] == "llm" and len(seq.calls) == 3
    # the same requests again: served from the cache, reporting the model that wrote the script
    same = ask(model=DEFAULT, safety_mode="balanced")
    assert same["method"] == "cached" and same["model"] == DEFAULT and len(seq.calls) == 3
    again = ask(model=OTHER, safety_mode="balanced")
    assert again["method"] == "cached" and again["model"] == OTHER and len(seq.calls) == 3
    assert [c["model"] for c in seq.calls] == [DEFAULT, OTHER, DEFAULT]


def test_altered_script_file_is_dropped_and_replaced(tmp_path):
    seq = _Sequence(_df_code(marker="original"), _df_code(marker="replacement"))
    cache = CacheManager(cache_dir=tmp_path / "cache")
    gen = _generator(seq, cache)
    meta = _metadata()
    gen.generate(metadata=meta, num_rows=3)
    entry = next(e for entries in cache.cache_index.values() for e in entries)
    assert len(entry["code_sha256"]) == 64
    altered = _df_code(marker="original").replace("[1]", "[666]")
    Path(entry["cache_file"]).write_text(altered)  # changed on disk after it was cached

    df, info = gen.generate(metadata=meta, num_rows=3)
    assert info["method"] == "llm" and len(seq.calls) == 2  # a miss: the model is asked again
    assert 666 not in set(df["a"])                          # the altered script never ran
    codes = _cached_codes(cache)
    assert len(codes) == 1 and "replacement" in codes[0] and "666" not in codes[0]
    assert gen.generate(metadata=meta, num_rows=3)[1]["method"] == "cached"


def test_missing_script_file_or_missing_hash_is_a_miss_not_an_error(tmp_path):
    cache = CacheManager(cache_dir=tmp_path / "cache")
    meta, variant = _metadata(), cache_variant(_metadata(), DEFAULT)
    cache.cache_generation(meta, _df_code(), num_rows=3, variant=variant, model=DEFAULT)
    entry = next(e for entries in cache.cache_index.values() for e in entries)
    Path(entry["cache_file"]).unlink()
    assert cache.find_similar_cached(meta, 0.95, num_rows=3, variant=variant) is None
    assert cache.cache_index == {}

    cache.cache_generation(meta, _df_code(), num_rows=3, variant=variant, model=DEFAULT)
    entry = next(e for entries in cache.cache_index.values() for e in entries)
    del entry["code_sha256"]  # as an entry from an older index file would be
    assert cache.find_similar_cached(meta, 0.95, num_rows=3, variant=variant) is None
    assert cache.cache_index == {}


def test_second_cache_object_does_not_write_its_index_copy_back(tmp_path):
    """main.py's CacheManager shares the generator's folder; a drop there stays in memory."""
    folder = tmp_path / "cache"
    owner = CacheManager(cache_dir=folder)
    meta, variant = _metadata(), cache_variant(_metadata(), DEFAULT)
    owner.cache_generation(meta, _df_code(), num_rows=3, variant=variant, model=DEFAULT)
    second = CacheManager(cache_dir=folder, persist_removals=False)
    entry = next(e for entries in second.cache_index.values() for e in entries)
    Path(entry["cache_file"]).write_text("raise SystemExit(1)\n")
    assert second.find_similar_cached(meta, 0.95, num_rows=3, variant=variant) is None
    assert second.cache_index == {}
    assert json.loads((folder / "cache_index.json").read_text()) != {}  # index file untouched
    # the owner checks for itself and drops it for good
    assert owner.find_similar_cached(meta, 0.95, num_rows=3, variant=variant) is None
    assert json.loads((folder / "cache_index.json").read_text()) == {}
    assert not Path(entry["cache_file"]).exists()
    assert main.cache_manager.persist_removals is False


@pytest.mark.parametrize("threshold", [0.0, 0.95])
def test_entries_without_a_variant_never_match(tmp_path, threshold):
    cache = CacheManager(cache_dir=tmp_path / "cache")
    meta, variant = _metadata(), cache_variant(_metadata(), DEFAULT)
    cache.cache_generation(meta, _df_code(), num_rows=3)  # as cached before this release
    assert cache.find_similar_cached(meta, threshold, num_rows=3, variant=variant) is None
    assert cache.find_similar_cached(meta, threshold, num_rows=3) is None
    # and a lookup that names no variant is offered nothing, even when entries have one
    cache.cache_generation(meta, _df_code(), num_rows=3, variant=variant, model=DEFAULT)
    assert cache.find_similar_cached(meta, threshold, num_rows=3) is None
    assert cache.find_similar_cached(meta, threshold, num_rows=3, variant=variant) is not None


def test_generator_ignores_a_script_cached_without_a_variant(tmp_path):
    seq = _Sequence(_df_code(marker="new"))
    cache = CacheManager(cache_dir=tmp_path / "cache")
    cache.cache_generation(_metadata(), _df_code(marker="old"), num_rows=3)
    _, info = _generator(seq, cache).generate(metadata=_metadata(), num_rows=3)
    assert info["method"] == "llm" and len(seq.calls) == 1


def test_client_metadata_cannot_claim_a_privacy_mode():
    raw = json.dumps({
        "privacy_mode": "balanced",
        "structure": {"columns": [{"name": "a", "dtype": "int64"}], "shape": {"rows": 3, "columns": 1}},
        "statistics": {"a": {"type": "numeric"}},
    })
    cleaned = main._validated_client_metadata(raw)
    assert "privacy_mode" not in cleaned
    assert cache_variant(cleaned, DEFAULT) == f"{DEFAULT}|client"
    assert cache_variant(cleaned, DEFAULT) != cache_variant(_file_metadata("balanced"), DEFAULT)
    assert cache_variant(_metadata(), DEFAULT) == f"{DEFAULT}|client"  # dictionary-only: no stamp


def test_only_the_exact_mode_text_shares_a_cache_variant():
    """The extractor compares modes exactly ("Strict" is not handled as "strict"), and the
    routes accept any text, so the variant uses the stamped text as it is."""
    strict = cache_variant({"privacy_mode": "strict"}, DEFAULT)
    unstamped = cache_variant({}, DEFAULT)
    others = [cache_variant({"privacy_mode": mode}, DEFAULT)
              for mode in ("Strict", " strict", "STRICT", "client", "balanced")]
    assert len({strict, unstamped, *others}) == 7
    # The extractor itself normalises the mode, so a file read as "Strict" is a strict file.
    assert cache_variant(_file_metadata("Strict"), DEFAULT) == cache_variant(_file_metadata("strict"), DEFAULT)
    assert cache_variant({"privacy_mode": None}, DEFAULT) == unstamped


# --------------------------------------------------------------------------- #
# The page
# --------------------------------------------------------------------------- #

def test_page_has_the_model_choice_and_sends_it_with_every_generation_request():
    html = (WEB / "index.html").read_text()
    js = (WEB / "static" / "js" / "app.js").read_text()
    assert '<select id="modelSelect"' in html and "Server default" in html
    assert "The default is fastest. Choose a stronger model if the result has wrong columns or values." in html
    assert "app.js?v=2026" in html
    assert "/api/models" in js
    # two previews (remember the choice) and two downloads (send the preview's choice)
    assert js.count("appendModel(formData, true)") == 2
    assert js.count("appendModel(formData, false)") == 2
    for function in ("generateSyntheticData", "generateFromDictionary",
                     "downloadGeneratedData", "downloadDictionaryData"):
        body = js.split(f"async function {function}(")[1].split("\nasync function ")[0].split("\nfunction ")[0]
        assert "appendModel(formData" in body, function
    loader = js.split("async function loadModelChoices()")[1].split("\nfunction ")[0]
    assert "textContent" in loader and "innerHTML" not in loader


def test_page_no_longer_makes_the_four_false_privacy_statements():
    html = (WEB / "index.html").read_text()
    for false_statement in ("Safe to upload sensitive/PHI data", "Data never leaves your browser",
                            "Only metadata is sent to LLM", "Original data is never exposed"):
        assert false_statement not in html
    for true_statement in (
            "Your file is sent to this server to be analysed.",
            "Rows are not sent to the AI model. It receives column names, types and summary statistics.",
            "Labels of repeated categories (such as M / F) are sent unless you set Privacy to Strict.",
            "Do not upload real study data or patient identifiers: this release has not been approved for them."):
        assert true_statement in html
