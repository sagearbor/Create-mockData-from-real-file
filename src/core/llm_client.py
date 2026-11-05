"""The one place this app builds its Azure OpenAI client.

All auth and telemetry come from the vendored ``src/dcri_llm.py``:

* ``LLM_AUTH=identity`` (default): managed identity on ACA
  (``AZURE_CLIENT_ID``), ``AzureCliCredential`` locally (``az login``).
* ``LLM_AUTH=key``: ``AZURE_OPENAI_API_KEY``, only for people without an identity.

Every call made through the returned client emits one ``llm_call`` telemetry
event (token counts and lengths only, never prompt or completion text).

There is NO template fallback. If ``AZURE_OPENAI_ENDPOINT`` is unset or the
client cannot be built, this returns ``None``, logs an ERROR, and records the
reason in :data:`not_ready_reason`; ``/ready`` then answers 503 and every
generation request fails with a clear error instead of returning template data.
Token acquisition happens lazily at call time, so an identity failure surfaces
as a failed request (HTTP 502), not here.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Why AI is unavailable (short, content-free), or None when the client built.
not_ready_reason: Optional[str] = None


def build_llm_client():
    """Return an instrumented AzureOpenAI client, or None (with an ERROR log) if AI is unavailable."""
    global not_ready_reason
    auth = (os.environ.get("LLM_AUTH") or "identity").strip().lower()
    if not os.environ.get("AZURE_OPENAI_ENDPOINT"):
        not_ready_reason = "AZURE_OPENAI_ENDPOINT is not set"
        logger.error("AI NOT READY: AZURE_OPENAI_ENDPOINT not set; generation requests will fail "
                     "(no template fallback).")
        return None
    try:
        from src.dcri_llm import make_client  # lazy: pulls in openai + azure-identity

        client = make_client()
        not_ready_reason = None
        logger.info("Azure OpenAI client ready (auth=%s)", auth)
        return client
    except Exception as exc:  # noqa: BLE001 - reported via /ready, not a crash
        # Never log the exception text: it could echo a key or endpoint detail.
        not_ready_reason = f"could not build Azure OpenAI client (LLM_AUTH={auth}, {type(exc).__name__})"
        logger.error(
            "AI NOT READY: %s; generation requests will fail (no template fallback). "
            "Check LLM_AUTH, AZURE_OPENAI_API_KEY (key mode) or azure-identity / az login "
            "(identity mode).", not_ready_reason,
        )
        return None
