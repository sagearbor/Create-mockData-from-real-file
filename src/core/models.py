"""Which AI models (Azure OpenAI deployment names) a request may choose.

The one place the allow-list lives. Every transport (form routes, /api/v1, MCP, A2A)
resolves a requested name here BEFORE any generation or model call.

* The server default is ``settings.azure_openai_chat_deployment``
  (env ``AZURE_OPENAI_CHAT_DEPLOYMENT_NAME``); it is always allowed and listed first.
* Env ``LLM_ALLOWED_MODELS`` (comma-separated deployment names) replaces the default list.

Settings and env are read on every call, so a change applies without a restart of
the list logic and tests can patch them.
"""

import os
from typing import Any, Dict, List, Optional

from src.utils.config import settings

ALLOWED_MODELS_ENV = "LLM_ALLOWED_MODELS"

# Each name made one real generation through this app on 2026-11-20
# (docs/release-1.0/model-probe-2026-11-20.txt, tools/release/probe_models.py).
# Add a name only after it passes that probe.
DEFAULT_ALLOWED_MODELS = (
    "gpt-5-nano",
    "gpt-5.4-nano",
    "gpt-5.4-mini",
    "gpt-5.5",
    "gpt-5.6-luna",
    "gpt-5.6-terra",
    "gpt-5.6-sol",
)


class ModelNotAllowed(ValueError):
    """The requested model is not on this server's allow-list."""


def default_model() -> str:
    """The deployment used when a request names no model."""
    return settings.azure_openai_chat_deployment


def allowed_models() -> List[str]:
    """Allowed deployment names: the server default first, then the configured list."""
    raw = os.environ.get(ALLOWED_MODELS_ENV, "")
    listed = [name.strip() for name in raw.split(",") if name.strip()] or list(DEFAULT_ALLOWED_MODELS)
    names: List[str] = []
    for name in [default_model(), *listed]:
        if name and name not in names:
            names.append(name)
    return names


def resolve_model(requested: Optional[str]) -> str:
    """The model to use for a request: the default when none is named.

    Raises:
        ModelNotAllowed: the name is not on the allow-list (the message lists the names).
    """
    name = (requested or "").strip()
    if not name:
        return default_model()
    allowed = allowed_models()
    if name not in allowed:
        raise ModelNotAllowed(
            f"Model {name[:100]!r} is not available on this server. "
            f"Allowed models: {', '.join(allowed)}.")
    return name


def model_catalog() -> Dict[str, Any]:
    """What GET /api/models returns. Labels are the names themselves: nothing here
    claims one model is better than another."""
    default = default_model()
    return {
        "default": default,
        "models": [
            {"name": name, "label": name, "note": "default" if name == default else ""}
            for name in allowed_models()
        ],
    }
