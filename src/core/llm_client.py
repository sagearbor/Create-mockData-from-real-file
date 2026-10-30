"""The one place this app builds its Azure OpenAI client.

All auth and telemetry come from the vendored ``src/dcri_llm.py``:

* ``LLM_AUTH=identity`` (default): managed identity on ACA
  (``AZURE_CLIENT_ID``), ``AzureCliCredential`` locally (``az login``).
* ``LLM_AUTH=key``: ``AZURE_OPENAI_API_KEY``, only for people without an identity.

Every call made through the returned client emits one ``llm_call`` telemetry
event (token counts and lengths only, never prompt or completion text).

If ``AZURE_OPENAI_ENDPOINT`` is unset, or the client cannot be built, this
returns ``None`` and the generator uses its template-based fallback. Token
acquisition happens lazily at call time, so an identity failure surfaces as a
failed call, which the generator also turns into the fallback.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def build_llm_client():
    """Return an instrumented AzureOpenAI client, or None if AI is not configured."""
    if not os.environ.get("AZURE_OPENAI_ENDPOINT"):
        logger.warning("AZURE_OPENAI_ENDPOINT not set; using template-based fallback generation")
        return None
    try:
        from src.dcri_llm import make_client  # lazy: pulls in openai + azure-identity

        client = make_client()
        logger.info(
            "Azure OpenAI client ready (auth=%s)",
            (os.environ.get("LLM_AUTH") or "identity").strip().lower(),
        )
        return client
    except Exception as exc:  # noqa: BLE001 - any failure means "no AI", not a crash
        # Never log the exception text: it could echo a key or endpoint detail.
        logger.warning(
            "AI DISABLED: could not build Azure OpenAI client (LLM_AUTH=%s, %s); "
            "all generation will use the template fallback. Check LLM_AUTH, "
            "AZURE_OPENAI_API_KEY (key mode) or azure-identity / az login (identity mode).",
            (os.environ.get("LLM_AUTH") or "identity").strip().lower(), type(exc).__name__,
        )
        return None
