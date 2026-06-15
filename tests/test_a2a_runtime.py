"""Tests for the a2a_runtime package (shim or real).

These tests use ONLY the Python standard library so they run under plain
``python3 tests/test_a2a_runtime.py`` in environments where pytest is not
installed.  They also pass under ``pytest tests/test_a2a_runtime.py`` when
pytest is available.

Covered:
  - encode_message / decode_message round-trip
  - cycle coercion to int (handles float coming off the wire)
  - AgentRegistry basic registration and dispatch
  - A2AClient in-process call (short-circuit via registry)
  - A2AClient raises LookupError for unknown remote agents
  - build_agent_card produces the correct /a2a/mock-data-generator URL
"""

from __future__ import annotations

import asyncio
import sys
import os
import traceback

# Make sure the repo root is on sys.path so ``a2a_runtime`` is importable
# when running as ``python3 tests/test_a2a_runtime.py`` from any cwd.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from a2a_runtime import (
    A2AClient,
    AgentRegistry,
    build_agent_card,
    decode_message,
    encode_message,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PASSED: list[str] = []
_FAILED: list[tuple[str, str]] = []


def _run(name: str, fn):
    """Run a synchronous or async test function and record the result."""
    try:
        if asyncio.iscoroutinefunction(fn):
            asyncio.run(fn())
        else:
            fn()
        _PASSED.append(name)
        print(f"  PASS  {name}")
    except Exception:  # noqa: BLE001
        tb = traceback.format_exc()
        _FAILED.append((name, tb))
        print(f"  FAIL  {name}")
        print(tb)


# ---------------------------------------------------------------------------
# Test functions — each is a plain callable or async callable
# ---------------------------------------------------------------------------

def test_encode_decode_round_trip():
    """encode_message -> decode_message should preserve payload and metadata."""
    payload = {"operation": "generate", "file_name": "demo.csv"}
    msg = encode_message(payload, correlation_id="cid-001", cycle=1, agent_id="mock-data-generator")

    decoded_payload, decoded_meta = decode_message(msg)

    assert decoded_payload == payload, f"Payload mismatch: {decoded_payload!r}"
    assert decoded_meta["correlation_id"] == "cid-001"
    assert decoded_meta["cycle"] == 1
    assert decoded_meta["agent_id"] == "mock-data-generator"


def test_cycle_coercion_to_int():
    """cycle must be coerced to int on decode even when stored as float."""
    # Simulate protobuf/JSON transport storing cycle as a float.
    msg = {
        "payload": {"x": 1},
        "metadata": {"correlation_id": "cid-float", "cycle": 2.0, "agent_id": None},
    }
    _, meta = decode_message(msg)
    assert isinstance(meta["cycle"], int), f"Expected int, got {type(meta['cycle'])}"
    assert meta["cycle"] == 2


def test_agent_registry_register_and_get():
    """AgentRegistry should store and return agents by agent_id."""
    registry = AgentRegistry()

    class _DummyAgent:
        agent_id = "dummy"

        async def run(self, payload: dict) -> dict:
            return {"echo": payload}

    agent = _DummyAgent()
    registry.register(agent)

    retrieved = registry.get("dummy")
    assert retrieved is agent, "Registry did not return the same agent instance."
    assert registry.get("nonexistent") is None


async def test_a2a_client_in_process_call():
    """A2AClient.call should short-circuit to the locally registered agent."""
    registry = AgentRegistry()

    class _EchoAgent:
        agent_id = "echo-agent"

        async def run(self, payload: dict) -> dict:
            return {"echoed": payload}

    registry.register(_EchoAgent())
    client = A2AClient(registry=registry)

    result = await client.call(
        "echo-agent",
        {"hello": "world"},
        correlation_id="cid-echo",
        cycle=1,
    )

    assert result == {"echoed": {"hello": "world"}}, f"Unexpected result: {result!r}"


async def test_a2a_client_remote_lookup_error():
    """A2AClient.call should raise LookupError for an unregistered remote agent."""
    registry = AgentRegistry()  # empty registry, no remote_sender configured
    client = A2AClient(registry=registry)

    try:
        await client.call(
            "no-such-agent",
            {},
            correlation_id="cid-missing",
            cycle=1,
        )
        raise AssertionError("Expected LookupError was not raised.")
    except LookupError:
        pass  # Correct behaviour.


def test_build_agent_card_url():
    """build_agent_card must produce /a2a/mock-data-generator as the URL."""
    card = build_agent_card(
        "mock-data-generator",
        name="Test Agent",
        description="desc",
        version="1.0.0",
    )
    assert card["url"] == "/a2a/mock-data-generator", (
        f"Unexpected card URL: {card['url']!r}"
    )


def test_encode_empty_payload():
    """encode_message should handle an empty payload dict without raising."""
    msg = encode_message({}, correlation_id="cid-empty", cycle=3)
    payload, meta = decode_message(msg)
    assert payload == {}
    assert meta["cycle"] == 3


# ---------------------------------------------------------------------------
# pytest-compatible fixtures (when pytest is available)
# ---------------------------------------------------------------------------

# The test functions above are also discovered by pytest automatically because
# they are named ``test_*`` and live in a ``tests/test_*.py`` file.
# The ``asyncio.iscoroutinefunction`` check inside ``_run`` is NOT needed by
# pytest (pytest-asyncio handles async tests), but it is used by the stdlib
# runner below.

# Mark async tests for pytest-asyncio when available.
try:
    import pytest  # noqa: F401

    pytest_plugins = ("pytest_asyncio",)

    # Re-export async tests as regular pytest test functions so pytest-asyncio
    # can discover them.  (pytest already discovers them by name, but we add
    # the marker explicitly for clarity.)
    import pytest as _pytest

    test_a2a_client_in_process_call = _pytest.mark.asyncio(test_a2a_client_in_process_call)
    test_a2a_client_remote_lookup_error = _pytest.mark.asyncio(test_a2a_client_remote_lookup_error)

except ImportError:
    pass  # pytest not installed; stdlib runner below is used instead.


# ---------------------------------------------------------------------------
# Stdlib runner (``python3 tests/test_a2a_runtime.py``)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Running a2a_runtime tests (stdlib runner)...\n")

    _run("test_encode_decode_round_trip", test_encode_decode_round_trip)
    _run("test_cycle_coercion_to_int", test_cycle_coercion_to_int)
    _run("test_agent_registry_register_and_get", test_agent_registry_register_and_get)
    _run("test_a2a_client_in_process_call", test_a2a_client_in_process_call)
    _run("test_a2a_client_remote_lookup_error", test_a2a_client_remote_lookup_error)
    _run("test_build_agent_card_url", test_build_agent_card_url)
    _run("test_encode_empty_payload", test_encode_empty_payload)

    print(f"\nResults: {len(_PASSED)} passed, {len(_FAILED)} failed.\n")
    if _FAILED:
        sys.exit(1)
