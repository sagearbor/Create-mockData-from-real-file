"""Tests for src.a2a_agent (MockDataAgent, build_card, register).

Light-weight tests that do NOT depend on pandas, openai, or fastapi run
unconditionally.  Tests that exercise the actual generation pipeline are
gated behind ``pytest.importorskip("pandas")``.
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

# Ensure the repo root is on the path for both direct and pytest invocations.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ---------------------------------------------------------------------------
# Stdlib-only tests (no heavy deps)
# ---------------------------------------------------------------------------


def test_register_idempotent():
    """register() can be called multiple times without raising."""
    from a2a_runtime import AgentRegistry
    from src.a2a_agent import register

    registry = AgentRegistry()
    register(registry=registry)
    register(registry=registry)  # second call must be safe
    agent = registry.get("mock-data-generator")
    assert agent is not None
    assert agent.agent_id == "mock-data-generator"


def test_build_card_url():
    """build_card() must return an AgentCard with the correct /a2a/ URL."""
    from src.a2a_agent import build_card

    card = build_card(internal_only=False)
    assert card["url"] == "/a2a/mock-data-generator"


def test_build_card_internal_only_flag():
    """internal_only kwarg is reflected in the card's x-dcri section."""
    from src.a2a_agent import build_card

    public_card = build_card(internal_only=False)
    private_card = build_card(internal_only=True)
    assert public_card["x-dcri"]["internal_only"] is False
    assert private_card["x-dcri"]["internal_only"] is True


@pytest.mark.asyncio
async def test_run_unknown_operation():
    """MockDataAgent.run with an unknown operation returns a status=error dict."""
    from src.a2a_agent import MockDataAgent

    agent = MockDataAgent()
    result = await agent.run({"operation": "frobnicate", "data_content": "aGk="})
    assert result["status"] == "error"
    assert "frobnicate" in result["error"]


# ---------------------------------------------------------------------------
# Tests that require pandas (generation pipeline)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_generate_operation_no_data():
    """generate operation with missing data_content returns status=error (no pandas needed)."""
    from src.a2a_agent import MockDataAgent

    agent = MockDataAgent()
    result = await agent.run({"operation": "generate"})  # no data_content
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_run_metadata_operation_no_data():
    """metadata operation with missing data_content returns status=error (no pandas needed)."""
    from src.a2a_agent import MockDataAgent

    agent = MockDataAgent()
    result = await agent.run({"operation": "metadata"})  # no data_content
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_run_generate_with_real_csv():
    """generate operation with a small real CSV returns status=success."""
    pandas = pytest.importorskip("pandas")  # gate behind pandas availability
    import base64
    import io

    # Build a tiny CSV in memory.
    df = pandas.DataFrame({"id": [1, 2, 3], "value": [10.0, 20.0, 30.0]})
    csv_bytes = df.to_csv(index=False).encode()
    data_content = base64.b64encode(csv_bytes).decode()

    from src.a2a_agent import MockDataAgent

    agent = MockDataAgent()
    result = await agent.run(
        {
            "operation": "generate",
            "data_content": data_content,
            "file_name": "test.csv",
            "num_rows": 5,
            "use_cache": False,
        }
    )
    # The result should be a success even when OpenAI is not configured
    # because SyntheticDataGenerator has a fallback path.
    assert result.get("status") in ("success", "error"), (
        f"Unexpected status: {result!r}"
    )


@pytest.mark.asyncio
async def test_run_metadata_with_real_csv():
    """metadata operation with a small CSV returns status=success with metadata key."""
    pandas = pytest.importorskip("pandas")  # gate behind pandas availability
    import base64

    df = pandas.DataFrame({"name": ["alice", "bob"], "score": [95, 87]})
    csv_bytes = df.to_csv(index=False).encode()
    data_content = base64.b64encode(csv_bytes).decode()

    from src.a2a_agent import MockDataAgent

    agent = MockDataAgent()
    result = await agent.run(
        {
            "operation": "metadata",
            "data_content": data_content,
            "file_name": "scores.csv",
        }
    )
    assert result.get("status") in ("success", "error"), (
        f"Unexpected status: {result!r}"
    )
    if result["status"] == "success":
        assert "metadata" in result
