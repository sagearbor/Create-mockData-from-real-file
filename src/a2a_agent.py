"""A2A agent wrapper for the BYOD Synthetic Data Generator.

This module defines :class:`MockDataAgent`, which satisfies the
:class:`a2a_runtime.RunnableAgent` protocol and can be registered into the
default :class:`a2a_runtime.AgentRegistry` so that any A2A caller (in-process
or remote via the FastAPI ``/a2a/{agent_id}`` endpoint) can dispatch jobs to
it.

Heavy dependencies (pandas, openai, ``src.core.*``) are imported **lazily**
inside :meth:`MockDataAgent.run` so that importing *this* module requires only
the stdlib-based ``a2a_runtime`` package.

Usage
-----
Import and register once during application startup::

    from src.a2a_agent import register
    register()

Then any A2AClient can call the agent by its ``agent_id``::

    from a2a_runtime import A2AClient
    client = A2AClient()
    result = await client.call(
        "mock-data-generator",
        {"operation": "generate", "data_content": "<base64>", "file_name": "data.csv"},
        correlation_id="req-001",
    )
"""

from __future__ import annotations

import logging
from typing import Optional

from a2a_runtime import (
    AgentRegistry,
    build_agent_card,
    default_registry,
)

logger = logging.getLogger(__name__)

_AGENT_ID = "mock-data-generator"
_AGENT_VERSION = "1.0.0"


class MockDataAgent:
    """A2A agent that dispatches to :mod:`src.core.generation_service`.

    Attributes:
        agent_id: The canonical agent identifier, ``"mock-data-generator"``.
    """

    agent_id: str = _AGENT_ID

    async def run(self, payload: dict) -> dict:
        """Dispatch an A2A payload to the appropriate generation service function.

        The ``operation`` key in *payload* controls dispatch:

        * ``"generate"`` (default) — calls :func:`generation_service.generate`.
        * ``"metadata"`` or ``"extract_metadata"`` — calls
          :func:`generation_service.extract_metadata`.

        All remaining keys in *payload* are forwarded verbatim to the
        selected function.

        Args:
            payload: A plain dict decoded from the A2A envelope.  Must contain
                ``data_content`` (base64-encoded file bytes) for both
                operations.  See :func:`generation_service.generate` and
                :func:`generation_service.extract_metadata` for the full list
                of accepted keys.

        Returns:
            A JSON-serialisable dict with at minimum a ``"status"`` key.
        """
        # Lazy import so this module is stdlib-only at import time.
        from src.core import generation_service  # noqa: PLC0415

        operation = payload.get("operation", "generate")

        if operation == "generate":
            return generation_service.generate(payload)
        elif operation in ("metadata", "extract_metadata"):
            return generation_service.extract_metadata(payload)
        else:
            logger.warning("MockDataAgent: unknown operation %r", operation)
            return {
                "status": "error",
                "error": (
                    f"Unknown operation {operation!r}. "
                    "Supported operations: 'generate', 'metadata'."
                ),
            }


def build_card(internal_only: bool = False) -> dict:
    """Build the AgentCard dict for ``/.well-known/agent.json``.

    Args:
        internal_only: When ``True`` the card signals that the agent is
            restricted to org-internal callers.  Set to ``False`` (the
            default) for the public-facing ``/.well-known/agent.json``
            endpoint so that external integrators (e.g. dcri-ct-graph) can
            discover it.

    Returns:
        A plain dict following the AgentCard schema defined by
        :func:`a2a_runtime.build_agent_card`.
    """
    return build_agent_card(
        _AGENT_ID,
        name="BYOD Mock Data Generator",
        description=(
            "Generates privacy-safe synthetic data that preserves the "
            "statistical structure of a real source file. Supports CSV and "
            "JSON output. Accepts base64-encoded file content so that raw "
            "sensitive data never leaves the caller."
        ),
        version=_AGENT_VERSION,
        internal_only=internal_only,
    )


def register(registry: Optional[AgentRegistry] = None) -> None:
    """Idempotently register a :class:`MockDataAgent` into *registry*.

    If *registry* is ``None`` the module-level :data:`a2a_runtime.default_registry`
    is used.  Calling this function more than once is safe — the agent
    instance is replaced but the behaviour is identical.

    Args:
        registry: Target registry.  Defaults to
            :data:`a2a_runtime.default_registry`.
    """
    target = registry if registry is not None else default_registry
    agent = MockDataAgent()
    target.register(agent)
    logger.info(
        "A2A agent %r registered into %r",
        _AGENT_ID,
        target,
    )
