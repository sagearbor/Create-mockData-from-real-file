"""Offline guards for the 2026-11-04 production failure and the no-fallback rule.

1. The LLM call is synchronous and slow (gpt-5-nano took ~59 s). When it ran
   on the event loop, /health stopped answering, the ACA liveness probe failed
   and the container was restarted mid-request (0 bytes after 240 s).
2. AI failures must never be papered over with template data: the user gets a
   clear error and no data, and /ready reports not-ready when AI is missing.
3. Reasoning models get reasoning_effort (default "low") and a 40000 budget.

A fake chat client stands in for Azure OpenAI: no network, no Azure login.
"""

import asyncio
import io
import json
import threading
from types import SimpleNamespace

import httpx
import pytest

import main
from src.core import llm_client
from src.core.synthetic_generator import (
    LLM_MAX_COMPLETION_TOKENS,
    AINotConfiguredError,
    SyntheticDataGenerator,
)

CSV = (
    "subject_id,age,sex,sbp\n"
    "S001,54,F,128\n"
    "S002,61,M,141\n"
    "S003,47,F,119\n"
    "S004,70,M,150\n"
    "S005,58,F,132\n"
).encode()

GOOD_CODE = (
    "import numpy as np\n"
    "import pandas as pd\n"
    "def generate_synthetic_data():\n"
    "    n = 8\n"
    "    return pd.DataFrame({'subject_id': [f'S{i:03d}' for i in range(n)],\n"
    "                         'age': np.random.randint(40, 75, n),\n"
    "                         'sex': np.random.choice(['F', 'M'], n),\n"
    "                         'sbp': np.random.randint(110, 160, n)})\n"
    "result = generate_synthetic_data()\n"
)

FORM = {"num_rows": "8", "use_cache": "false", "cache_mode": "off", "output_format": "csv"}


class _Completions:
    """Fake chat.completions: optional block until released, or a fixed failure."""

    def __init__(self, content=GOOD_CODE, finish_reason="stop", exc=None, block=False):
        self.content, self.finish_reason, self.exc, self.block = content, finish_reason, exc, block
        self.entered, self.release, self.exited = threading.Event(), threading.Event(), threading.Event()
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        self.entered.set()
        try:
            if self.block:
                self.release.wait(timeout=5)
            if self.exc:
                raise self.exc
            msg = SimpleNamespace(content=self.content)
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason=self.finish_reason, message=msg)])
        finally:
            self.exited.set()


def _generator(completions):
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    gen = SyntheticDataGenerator(openai_client=client)
    gen.cache_manager = SimpleNamespace(
        cache_generation=lambda *a, **k: None, find_similar_cached=lambda *a, **k: None)
    return gen


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # usage logs land in tmp, not the repo
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
    monkeypatch.setattr(SyntheticDataGenerator, "_reasoning_effort_rejected", False)
    from src.utils.config import settings
    monkeypatch.setattr(settings, "azure_openai_chat_deployment", "gpt-5-nano")


def _run(coro):
    return asyncio.run(coro)


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test")


async def _health_during(path, completions):
    """POST `path` with a slow fake LLM, probe /health while it is in flight."""
    async with _client() as c:
        gen = asyncio.create_task(
            c.post(path, data=FORM, files={"file": ("synthetic.csv", CSV, "text/csv")}, timeout=30))
        for _ in range(200):  # wait (without blocking the loop) until the LLM call starts
            if completions.entered.is_set() or gen.done():
                break
            await asyncio.sleep(0.02)
        assert completions.entered.is_set(), "generation never reached the LLM call"

        health = await asyncio.wait_for(c.get("/health"), timeout=2)
        in_flight = not completions.exited.is_set() and not gen.done()
        completions.release.set()
        resp = await asyncio.wait_for(gen, timeout=30)
        return health, in_flight, resp


# --------------------------------------------------------------------------- #
# 1. /health answers while a slow generation is in flight
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("path", ["/generate", "/generate-sse"])
def test_health_answers_while_slow_generation_is_in_flight(monkeypatch, path):
    completions = _Completions(block=True)
    monkeypatch.setattr(main, "synthetic_generator", _generator(completions))

    health, in_flight, resp = _run(_health_during(path, completions))

    assert health.status_code == 200
    assert in_flight, "/health only answered after the LLM call finished: event loop was blocked"
    assert resp.status_code == 200
    if path == "/generate":
        assert resp.headers["X-Generation-Method"] == "llm"
        assert len(resp.text.strip().splitlines()) == 9  # header + 8 rows
    else:
        final = json.loads(resp.text.strip().splitlines()[-1][len("data: "):])
        assert final["complete"] and final["generation_info"]["method"] == "llm"


# --------------------------------------------------------------------------- #
# 2. No fallback: AI failures are errors, never template data
# --------------------------------------------------------------------------- #

def test_template_fallback_code_path_no_longer_exists():
    assert not hasattr(SyntheticDataGenerator, "_generate_fallback_code")
    assert not hasattr(SyntheticDataGenerator, "_execute_code_directly")


def test_generate_without_ai_client_raises_instead_of_templating():
    gen = SyntheticDataGenerator(openai_client=None)
    gen.cache_manager = SimpleNamespace(find_similar_cached=lambda *a, **k: None)
    metadata = {"structure": {"shape": {"rows": 3, "columns": 1},
                              "columns": [{"name": "x", "dtype": "int64"}]},
                "statistics": {}, "patterns": {}}
    with pytest.raises(AINotConfiguredError):
        gen.generate(metadata, num_rows=3, use_cached=False)


class _Boom(Exception):
    status_code = 500


@pytest.mark.parametrize("kw,expect", [
    ({"exc": _Boom("provider said: secret prompt text")}, "HTTP 500"),
    ({"content": "partial", "finish_reason": "length"}, "finish_reason=length"),
    ({"content": "", "finish_reason": "stop"}, "empty response"),
])
@pytest.mark.parametrize("fmt", ["csv", "excel", "json"])
def test_llm_failure_returns_clear_error_not_data(monkeypatch, caplog, kw, expect, fmt):
    monkeypatch.setattr(main, "synthetic_generator", _generator(_Completions(**kw)))

    async def go():
        async with _client() as c:
            return await c.post("/generate", data={**FORM, "output_format": fmt},
                                files={"file": ("synthetic.csv", CSV, "text/csv")})

    with caplog.at_level("ERROR"):
        resp = _run(go())

    assert resp.status_code == 502
    body = resp.json()
    assert body["status"] == "error" and "data" not in body
    assert body["error"].startswith("AI generation failed:") and expect in body["error"]
    assert body["error"].endswith("No data was generated.")
    assert "secret prompt text" not in resp.text
    failures = [json.loads(r.getMessage()) for r in caplog.records
                if '"ai_generation_failed"' in r.getMessage()]
    assert failures and failures[0]["model"] == "gpt-5-nano"
    assert "subject_id" not in caplog.text  # no column names / data in logs


def test_sse_llm_failure_streams_error_event(monkeypatch):
    monkeypatch.setattr(main, "synthetic_generator",
                        _generator(_Completions(content="", finish_reason="stop")))

    async def go():
        async with _client() as c:
            return await c.post("/generate-sse", data=FORM,
                                files={"file": ("synthetic.csv", CSV, "text/csv")})

    last = json.loads(_run(go()).text.strip().splitlines()[-1][len("data: "):])
    assert "complete" not in last
    assert last["error"].startswith("AI generation failed:") and last["http_status"] == 502


def test_no_ai_client_means_503_and_not_ready(monkeypatch):
    monkeypatch.setattr(main, "synthetic_generator", SyntheticDataGenerator(openai_client=None))
    monkeypatch.setattr(llm_client, "not_ready_reason", "AZURE_OPENAI_ENDPOINT is not set")

    async def go():
        async with _client() as c:
            gen = await c.post("/generate", data=FORM,
                               files={"file": ("synthetic.csv", CSV, "text/csv")})
            return gen, await c.get("/ready"), await c.get("/health")

    gen, ready, health = _run(go())
    assert gen.status_code == 503 and "No data was generated" in gen.json()["error"]
    assert ready.status_code == 503 and ready.json()["ai_ready"] is False
    assert "AZURE_OPENAI_ENDPOINT" in ready.json()["ai_not_ready_reason"]
    assert health.status_code == 200 and health.json()["ai_ready"] is False  # liveness stays up


def test_ready_is_200_with_ai_client(monkeypatch):
    monkeypatch.setattr(main, "synthetic_generator", _generator(_Completions()))

    async def go():
        async with _client() as c:
            return await c.get("/ready")

    r = _run(go())
    assert r.status_code == 200 and r.json()["ai_ready"] is True


# --------------------------------------------------------------------------- #
# 3. Reasoning effort + budget
# --------------------------------------------------------------------------- #

META = {"structure": {"shape": {"rows": 3, "columns": 1},
                      "columns": [{"name": "x", "dtype": "int64"}]},
        "statistics": {}, "patterns": {}}


def test_reasoning_model_gets_low_effort_and_40k_budget():
    completions = _Completions()
    _generator(completions)._generate_code_with_llm(META, 3, 0.8)
    sent = completions.calls[0]
    assert sent["reasoning_effort"] == "low"
    assert sent["max_completion_tokens"] == LLM_MAX_COMPLETION_TOKENS == 40000
    assert LLM_MAX_COMPLETION_TOKENS >= 32000  # HARD RULE floor for reasoning models


@pytest.mark.parametrize("value,expected", [("off", None), ("medium", "medium"), ("HIGH", "high")])
def test_reasoning_effort_env_override(monkeypatch, value, expected):
    monkeypatch.setenv("LLM_REASONING_EFFORT", value)
    completions = _Completions()
    _generator(completions)._generate_code_with_llm(META, 3, 0.8)
    assert completions.calls[0].get("reasoning_effort") == expected


def test_rejected_reasoning_effort_is_dropped_and_retried():
    class BadRequest(Exception):
        status_code = 400

    class RejectOnce(_Completions):
        def create(self, **kwargs):
            if "reasoning_effort" in kwargs:
                self.calls.append(kwargs)
                raise BadRequest("Unsupported parameter: 'reasoning_effort'")
            return super().create(**kwargs)

    completions = RejectOnce()
    gen = _generator(completions)
    code, method, _ = gen._generate_code_with_llm(META, 3, 0.8)
    assert method == "llm" and code
    assert "reasoning_effort" in completions.calls[0]
    assert "reasoning_effort" not in completions.calls[1]
    # Remembered: the next call doesn't send it at all.
    gen._generate_code_with_llm(META, 3, 0.8)
    assert "reasoning_effort" not in completions.calls[2]


def test_non_reasoning_model_gets_no_effort(monkeypatch):
    from src.utils.config import settings
    monkeypatch.setattr(settings, "azure_openai_chat_deployment", "gpt-4o-mini")
    completions = _Completions()
    _generator(completions)._generate_code_with_llm(META, 3, 0.8)
    assert "reasoning_effort" not in completions.calls[0]
    assert completions.calls[0]["temperature"] == 0.3
