"""MCP stdio server exposing the BYOD synthetic-data generation capabilities.

This server exposes two MCP tools:

  * ``generate_synthetic_data`` — generate synthetic rows from a base64-
    encoded source file.
  * ``extract_metadata`` — extract statistical/structural metadata from a
    base64-encoded source file without generating any synthetic data.

Launch with:

    python -m src.mcp_server

Both tools delegate to :mod:`src.core.generation_service`, which lazy-imports
all heavy dependencies (pandas, openai, etc.) so this module itself starts
quickly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MCP server definition
# ---------------------------------------------------------------------------

async def main() -> None:
    """Run the MCP stdio server."""
    try:
        import mcp.server.stdio  # type: ignore
        from mcp.server import Server  # type: ignore
        from mcp.types import TextContent, Tool  # type: ignore
    except ImportError as exc:
        print(
            f"ERROR: 'mcp' package not installed. Install it with: pip install mcp>=0.4.0\n{exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    server = Server("mock-data-generator")

    # -----------------------------------------------------------------------
    # Tool registry
    # -----------------------------------------------------------------------

    @server.list_tools()
    async def list_tools() -> list[Tool]:  # type: ignore[override]
        """Advertise the two available tools."""
        return [
            Tool(
                name="generate_synthetic_data",
                description=(
                    "Generate synthetic/mock data that preserves the statistical "
                    "structure of a real source file. The source file must be "
                    "base64-encoded. Returns the synthetic dataset as CSV text or "
                    "JSON records together with generation metadata."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["data_content"],
                    "properties": {
                        "data_content": {
                            "type": "string",
                            "description": (
                                "Base64-encoded bytes of the source data file "
                                "(e.g. the raw content of a CSV file)."
                            ),
                        },
                        "file_name": {
                            "type": "string",
                            "description": (
                                "Original file name including extension, e.g. "
                                "'patients.csv'. Used to detect file format."
                            ),
                        },
                        "num_rows": {
                            "type": "integer",
                            "description": (
                                "Number of synthetic rows to generate. "
                                "Omit to match the source row count."
                            ),
                        },
                        "match_threshold": {
                            "type": "number",
                            "description": (
                                "Statistical matching threshold, 0–1. "
                                "Higher values require closer statistical "
                                "similarity to the source. Default: 0.8."
                            ),
                        },
                        "output_format": {
                            "type": "string",
                            "enum": ["csv", "json"],
                            "description": "Output format: 'csv' (default) or 'json'.",
                        },
                        "safety_mode": {
                            "type": "string",
                            "enum": ["balanced", "strict", "permissive"],
                            "description": (
                                "Data-privacy mode: 'strict' preserves only data "
                                "types; 'balanced' (default) preserves non-sensitive "
                                "categorical values; 'permissive' trusts the LLM."
                            ),
                        },
                        "use_cache": {
                            "type": "boolean",
                            "description": (
                                "Whether to reuse previously generated code for "
                                "similar schemas. Default: true."
                            ),
                        },
                    },
                },
            ),
            Tool(
                name="extract_metadata",
                description=(
                    "Extract statistical and structural metadata from a source data "
                    "file without generating any synthetic data. Useful for "
                    "inspecting column types, distributions, and value ranges before "
                    "deciding on generation parameters. The source file must be "
                    "base64-encoded."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["data_content"],
                    "properties": {
                        "data_content": {
                            "type": "string",
                            "description": "Base64-encoded bytes of the source data file.",
                        },
                        "file_name": {
                            "type": "string",
                            "description": "Original file name including extension.",
                        },
                        "safety_mode": {
                            "type": "string",
                            "enum": ["balanced", "strict", "permissive"],
                            "description": (
                                "Data-privacy mode controlling how much detail "
                                "is preserved in the metadata. Default: 'balanced'."
                            ),
                        },
                    },
                },
            ),
        ]

    # -----------------------------------------------------------------------
    # Tool dispatch
    # -----------------------------------------------------------------------

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:  # type: ignore[override]
        """Dispatch tool calls to generation_service."""
        # Lazy import: avoids pulling pandas/openai at MCP server import time.
        from src.core import generation_service  # noqa: PLC0415

        if name == "generate_synthetic_data":
            result = generation_service.generate(arguments)
        elif name == "extract_metadata":
            result = generation_service.extract_metadata(arguments)
        else:
            result = {"status": "error", "error": f"Unknown tool: {name!r}"}

        return [TextContent(type="text", text=json.dumps(result, default=str))]

    # -----------------------------------------------------------------------
    # Run server over stdio
    # -----------------------------------------------------------------------
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
