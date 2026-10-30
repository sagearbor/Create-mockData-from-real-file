"""Offline tests for the dcri_llm wiring (keyless auth + llm_call telemetry).

A fake chat client stands in for AzureOpenAI, so no network or Azure login is
needed. ``dcri_llm.instrument`` wraps it exactly as ``make_client`` wraps the
real client.
"""

import json
from types import SimpleNamespace

import pytest

from src import dcri_llm
from src.core import llm_client
from src.core.synthetic_generator import (
    LLM_MAX_COMPLETION_TOKENS,
    SyntheticDataGenerator,
)

SECRET_COLUMN = "patient_secret_mrn_col"
SECRET_VALUE = "SECRET_VALUE_XYZ"

GOOD_CODE = (
    "import pandas as pd\n"
    "def generate_synthetic_data():\n"
    f"    return pd.DataFrame({{'{SECRET_COLUMN}': [1, 2, 3]}})\n"
    "result = generate_synthetic_data()\n"
)


class _FakeCompletions:
    def __init__(self, content, finish_reason="stop", exc=None):
        self.content, self.finish_reason, self.exc = content, finish_reason, exc
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        usage = SimpleNamespace(
            prompt_tokens=120, completion_tokens=900,
            prompt_tokens_details=SimpleNamespace(cached_tokens=0),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=700),
        )
        msg = SimpleNamespace(content=self.content, tool_calls=None, function_call=None)
        return SimpleNamespace(
            model="gpt-5-nano-2025-08-07", usage=usage,
            choices=[SimpleNamespace(finish_reason=self.finish_reason, message=msg)],
        )


def _fake_client(**kw):
    completions = _FakeCompletions(**kw)
    client = SimpleNamespace(
        base_url="https://dcri-aifoundry-poc.openai.azure.com/openai/",
        chat=SimpleNamespace(completions=completions),
    )
    return dcri_llm.instrument(client), completions


def _metadata():
    return {
        "structure": {
            "shape": {"rows": 3, "columns": 1},
            "columns": [{"name": SECRET_COLUMN, "dtype": "object"}],
        },
        "statistics": {SECRET_COLUMN: {"most_common_values": {SECRET_VALUE: 3}}},
        "patterns": {},
    }


def _events(out):
    return [json.loads(line) for line in out.splitlines()
            if line.startswith("{") and '"llm_call"' in line]


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("SOLUTION_NAME", "mock-data-generator")
    monkeypatch.delenv("TELEMETRY_BLOB_ACCOUNT_URL", raising=False)
    monkeypatch.chdir(tmp_path)  # usage logs land in tmp, not the repo
    from src.utils.config import settings
    monkeypatch.setattr(settings, "azure_openai_chat_deployment", "gpt-5-nano")


def test_one_call_emits_schema_v1_event_without_content(capsys):
    client, completions = _fake_client(content=GOOD_CODE)
    gen = SyntheticDataGenerator(openai_client=client)

    code, method, _, llm_error = gen._generate_code_with_llm(_metadata(), 3, 0.8)

    assert method == "llm" and llm_error is None
    sent = completions.calls[0]
    assert sent["max_completion_tokens"] == LLM_MAX_COMPLETION_TOKENS == 40000
    assert "max_tokens" not in sent
    assert "temperature" not in sent  # gpt-5 rejects non-default temperature

    out = capsys.readouterr().out
    events = _events(out)
    assert len(events) == 1
    ev = events[0]
    assert ev["event"] == "llm_call" and ev["schema"] == 1
    assert ev["solution"] == "mock-data-generator"
    assert ev["operation"] == "generate_code"
    assert ev["input_tokens"] == 120 and ev["output_tokens"] == 900
    assert ev["reasoning_tokens"] == 700
    assert ev["max_completion_tokens"] == 40000 and ev["budget_below_floor"] is False
    assert ev["finish_reason"] == "stop" and ev["empty_output"] is False
    line = next(l for l in out.splitlines() if '"llm_call"' in l)
    assert SECRET_COLUMN not in line and SECRET_VALUE not in line
    assert "synthetic" not in line.lower()  # no system/user prompt text


@pytest.mark.parametrize("content,finish", [("partial code", "length"), ("", "stop")])
def test_truncated_or_empty_output_falls_back_and_is_surfaced(content, finish, capsys):
    client, _ = _fake_client(content=content, finish_reason=finish)
    gen = SyntheticDataGenerator(openai_client=client)

    code, method, _, llm_error = gen._generate_code_with_llm(_metadata(), 3, 0.8)

    assert method == "fallback"
    assert llm_error and "fallback" in llm_error
    ev = _events(capsys.readouterr().out)[0]
    assert ev["finish_length"] is (finish == "length")


def test_auth_failure_falls_back_cleanly_and_generate_reports_it(capsys):
    class FakeAuthError(Exception):
        status_code = 401

    client, _ = _fake_client(content=None, exc=FakeAuthError("bad token"))
    gen = SyntheticDataGenerator(openai_client=client)

    df, info = gen.generate(_metadata(), num_rows=3, use_cached=False)

    assert len(df) == 3
    assert info["method"] == "fallback"
    assert "FakeAuthError" in info["llm_error"] and "401" in info["llm_error"]
    ev = _events(capsys.readouterr().out)[0]
    assert ev["outcome"] == "error" and ev["http_status"] == 401


def test_no_endpoint_means_no_client(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    assert llm_client.build_llm_client() is None


def test_identity_client_builds_without_a_key(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("LLM_AUTH", "identity")
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    pytest.importorskip("azure.identity")
    client = llm_client.build_llm_client()
    assert client is not None
    assert getattr(client, "__dcri_llm_instrumented__", False)


def test_usage_log_has_no_column_names(tmp_path):
    gen = SyntheticDataGenerator()
    gen._log_usage("fallback", _metadata(), 3, {"total": 0.1})

    files = list((tmp_path / "logs" / "usage").glob("*.jsonl"))
    text = files[0].read_text()
    assert SECRET_COLUMN not in text
    entry = json.loads(text.splitlines()[-1])
    assert "column_names" not in entry and entry["num_columns"] == 1
