"""Shared generation service layer for all transports (REST, MCP, A2A).

This module provides plain-function wrappers around the core pipeline so that
REST, MCP, and A2A adapters can all call the same business logic without
duplicating any pipeline code.

All heavy imports (pandas, openai, src.core.*) are **lazy** — they happen
inside each function body so that importing this module is cheap and safe from
any stdlib-only context (e.g. the A2A agent wrapper loaded at import time).
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_generator():
    """Return a SyntheticDataGenerator, building the openai client lazily."""
    from src.core.synthetic_generator import SyntheticDataGenerator  # lazy

    from src.core.llm_client import build_llm_client  # lazy

    return SyntheticDataGenerator(openai_client=build_llm_client())


# ---------------------------------------------------------------------------
# Public API — one function per logical operation
# ---------------------------------------------------------------------------

def generate(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Generate synthetic data from a base64-encoded source file.

    This is the single entry point called by all three transports (REST, MCP,
    A2A).  It deliberately mirrors the core of ``main.py``'s ``/generate``
    endpoint so behaviour is identical across transports.

    Args:
        payload: A plain dict with the following keys:

            * ``data_content`` (str, required) — base64-encoded bytes of the
              source file (e.g. the raw CSV bytes).
            * ``file_name`` (str, optional) — original file name including
              extension, e.g. ``"patients.csv"``.  Defaults to
              ``"input.csv"``.
            * ``num_rows`` (int | None, optional) — number of rows to
              generate.  ``None`` means "match the source".
            * ``match_threshold`` (float, optional) — statistical matching
              threshold, 0–1.  Defaults to ``0.8``.
            * ``output_format`` (str, optional) — ``"csv"`` or ``"json"``.
              Defaults to ``"csv"``.
            * ``safety_mode`` (str, optional) — ``"balanced"``,
              ``"strict"``, or ``"permissive"``.  Defaults to
              ``"balanced"``.
            * ``use_cache`` (bool, optional) — whether to use the
              generation-code cache.  Defaults to ``True``.

    Returns:
        A JSON-serialisable dict::

            {
                "status": "success",
                "format": "csv",
                "shape": [<rows>, <cols>],
                "data": "<csv text or json records>",
                "generation_info": { ... },
            }

        On error::

            {"status": "error", "error": "<message>"}
    """
    # --- extract & validate payload keys ------------------------------------
    data_content: Optional[str] = payload.get("data_content")
    if not data_content:
        return {"status": "error", "error": "payload.data_content is required"}

    file_name: str = payload.get("file_name") or "input.csv"
    num_rows: Optional[int] = payload.get("num_rows")
    match_threshold: float = float(payload.get("match_threshold", 0.8))
    output_format: str = payload.get("output_format", "csv")
    safety_mode: str = payload.get("safety_mode", "balanced")
    use_cache: bool = bool(payload.get("use_cache", True))

    try:
        # --- decode source bytes -------------------------------------------
        try:
            file_bytes = base64.b64decode(data_content)
        except Exception as exc:
            return {"status": "error", "error": f"base64 decode failed: {exc}"}

        # --- lazy heavy imports -------------------------------------------
        from src.core.data_loader import DataLoader  # lazy
        from src.core.metadata_extractor import MetadataExtractor  # lazy

        # --- load dataframe -----------------------------------------------
        df = DataLoader().load_from_bytes(file_bytes, file_name)

        # --- extract metadata ---------------------------------------------
        extractor = MetadataExtractor(safety_mode=safety_mode)
        metadata = extractor.extract(df)

        # --- generate synthetic data --------------------------------------
        generator = _get_generator()
        synthetic_df, generation_info = generator.generate(
            metadata=metadata,
            num_rows=num_rows,
            match_threshold=match_threshold,
            use_cached=use_cache,
        )

        # --- serialise output ---------------------------------------------
        rows, cols = synthetic_df.shape

        if output_format == "json":
            import json  # stdlib always available

            records = json.loads(
                synthetic_df.to_json(orient="records", date_format="iso")
            )
            return {
                "status": "success",
                "format": "json",
                "shape": [rows, cols],
                "data": records,
                "generation_info": generation_info,
            }
        else:  # default: csv
            csv_text = synthetic_df.to_csv(index=False)
            return {
                "status": "success",
                "format": "csv",
                "shape": [rows, cols],
                "data": csv_text,
                "generation_info": generation_info,
            }

    except Exception as exc:  # noqa: BLE001
        logger.error("generation_service.generate error: %s", exc, exc_info=True)
        return {"status": "error", "error": str(exc)}


def extract_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract metadata from a base64-encoded source file.

    Args:
        payload: A plain dict with:

            * ``data_content`` (str, required) — base64-encoded file bytes.
            * ``file_name`` (str, optional) — original file name.  Defaults
              to ``"input.csv"``.
            * ``safety_mode`` (str, optional) — ``"balanced"``,
              ``"strict"``, or ``"permissive"``.  Defaults to
              ``"balanced"``.

    Returns:
        A JSON-serialisable dict::

            {"status": "success", "metadata": { ... }}

        On error::

            {"status": "error", "error": "<message>"}
    """
    data_content: Optional[str] = payload.get("data_content")
    if not data_content:
        return {"status": "error", "error": "payload.data_content is required"}

    file_name: str = payload.get("file_name") or "input.csv"
    safety_mode: str = payload.get("safety_mode", "balanced")

    try:
        try:
            file_bytes = base64.b64decode(data_content)
        except Exception as exc:
            return {"status": "error", "error": f"base64 decode failed: {exc}"}

        # lazy heavy imports
        from src.core.data_loader import DataLoader  # lazy
        from src.core.metadata_extractor import MetadataExtractor  # lazy

        df = DataLoader().load_from_bytes(file_bytes, file_name)
        extractor = MetadataExtractor(safety_mode=safety_mode)
        metadata = extractor.extract(df)

        return {"status": "success", "metadata": metadata}

    except Exception as exc:  # noqa: BLE001
        logger.error("generation_service.extract_metadata error: %s", exc, exc_info=True)
        return {"status": "error", "error": str(exc)}
