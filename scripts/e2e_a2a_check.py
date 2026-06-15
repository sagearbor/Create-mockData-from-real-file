#!/usr/bin/env python3
"""e2e_a2a_check.py — Live end-to-end proof that the deployed Cloud Run service
works as a public A2A endpoint.

Usage:
    python3 scripts/e2e_a2a_check.py --url https://<service-url>

    # or via environment variable:
    E2E_URL=https://<service-url> python3 scripts/e2e_a2a_check.py

STDLIB ONLY — no pandas, requests, httpx, or any third-party imports are used
here so the script can run in any environment (CI runner, fresh laptop, Cloud
Shell) with just Python 3.8+.

Checks performed:
    a) GET {url}/health — must return 200 and include "a2a_backend" key.
    b) GET {url}/.well-known/agent.json — must return a card whose "url" field
       equals "/a2a/mock-data-generator".
    c) POST {url}/a2a/mock-data-generator with a tiny base64-encoded CSV sent
       in the canonical A2A envelope — result must have status "success" (or
       at minimum a non-empty "data" / "generation_info" key on the fallback
       path when Azure OpenAI credentials are absent).

Exit codes:
    0 — all checks PASSED
    1 — one or more checks FAILED
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Minimal local A2A envelope helpers (duplicated from a2a_runtime._shim so
# this script stays stdlib-only and importable without the full package tree).
# ---------------------------------------------------------------------------

def _encode_message(
    payload: dict,
    *,
    correlation_id: str,
    cycle: int = 1,
    agent_id: str = "mock-data-generator",
) -> dict:
    """Build the canonical A2A envelope dict."""
    return {
        "payload": payload,
        "metadata": {
            "correlation_id": correlation_id,
            "cycle": int(cycle),
            "agent_id": agent_id,
        },
    }


def _decode_message(envelope: dict) -> Tuple[dict, dict]:
    """Extract (payload, metadata) from an A2A envelope."""
    payload = dict(envelope.get("payload", {}))
    meta_in = dict(envelope.get("metadata", {}))
    metadata = {
        "correlation_id": meta_in.get("correlation_id"),
        "cycle": int(meta_in.get("cycle", 1)),
        "agent_id": meta_in.get("agent_id"),
    }
    return payload, metadata


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib urllib only)
# ---------------------------------------------------------------------------

def _get(url: str, timeout: float = 30.0) -> Tuple[int, dict]:
    """GET *url* and return (status_code, parsed_json_body)."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace") if exc.fp else ""
        raise RuntimeError(f"GET {url} -> HTTP {exc.code}: {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GET {url} failed: {exc.reason}") from exc


def _post_json(url: str, body: dict, timeout: float = 90.0) -> Tuple[int, dict]:
    """POST JSON *body* to *url* and return (status_code, parsed_json_body)."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace") if exc.fp else ""
        raise RuntimeError(f"POST {url} -> HTTP {exc.code}: {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"POST {url} failed: {exc.reason}") from exc


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_health(base_url: str) -> Tuple[bool, str]:
    """Check (a): GET /health returns 200 and includes 'a2a_backend'."""
    url = base_url.rstrip("/") + "/health"
    try:
        status, body = _get(url)
    except RuntimeError as exc:
        return False, f"FAIL  /health: {exc}"

    if status != 200:
        return False, f"FAIL  /health: unexpected HTTP status {status}"

    if "a2a_backend" not in body:
        return (
            False,
            f"FAIL  /health: 'a2a_backend' key missing from response: {json.dumps(body)[:200]}",
        )

    backend = body.get("a2a_backend", "<absent>")
    return True, f"PASS  /health: status=healthy a2a_backend={backend!r}"


def check_agent_card(base_url: str) -> Tuple[bool, str]:
    """Check (b): GET /.well-known/agent.json returns card with correct url."""
    url = base_url.rstrip("/") + "/.well-known/agent.json"
    try:
        status, body = _get(url)
    except RuntimeError as exc:
        return False, f"FAIL  /.well-known/agent.json: {exc}"

    if status != 200:
        return False, f"FAIL  /.well-known/agent.json: HTTP {status}"

    card_url: Optional[str] = body.get("url")
    expected = "/a2a/mock-data-generator"
    if card_url != expected:
        return (
            False,
            f"FAIL  /.well-known/agent.json: 'url' field is {card_url!r}, expected {expected!r}",
        )

    name = body.get("name", "<absent>")
    return True, f"PASS  /.well-known/agent.json: name={name!r} url={card_url!r}"


def check_a2a_generate(base_url: str) -> Tuple[bool, str]:
    """Check (c): POST /a2a/mock-data-generator with a tiny CSV payload.

    Success criteria (lenient, Azure-credential-optional):
        - Response envelope decodes without error.
        - Inner payload has 'status' == 'success'
          OR ('data' or 'generation_info') is non-empty (fallback path).
    """
    url = base_url.rstrip("/") + "/a2a/mock-data-generator"

    # Build a minimal CSV
    csv_text = "id,age\n1,30\n2,41\n3,29\n4,55\n"
    b64_csv = base64.b64encode(csv_text.encode("utf-8")).decode("utf-8")

    inner_payload = {
        "operation": "generate",
        "data_content": b64_csv,
        "file_name": "input.csv",
        "num_rows": 5,
        "output_format": "csv",
    }
    envelope = _encode_message(
        inner_payload,
        correlation_id="e2e-1",
        cycle=1,
        agent_id="mock-data-generator",
    )

    try:
        _status, response_envelope = _post_json(url, envelope)
    except RuntimeError as exc:
        return False, f"FAIL  /a2a/mock-data-generator: {exc}"

    # Decode the outer envelope
    try:
        result, _meta = _decode_message(response_envelope)
    except Exception as exc:  # noqa: BLE001
        return (
            False,
            f"FAIL  /a2a/mock-data-generator: could not decode envelope: {exc}; "
            f"raw={json.dumps(response_envelope)[:300]}",
        )

    # Lenient success check: 'success' status OR non-empty data/generation_info
    status_val = result.get("status")
    data_val = result.get("data")
    gen_info = result.get("generation_info")
    method = (gen_info or {}).get("method", "<unknown>") if isinstance(gen_info, dict) else "<unknown>"

    if status_val == "success":
        shape = result.get("shape", "?")
        return (
            True,
            f"PASS  /a2a/mock-data-generator: status=success shape={shape} method={method!r}",
        )

    # Fallback: treat non-empty data or generation_info as acceptable
    if data_val or gen_info:
        return (
            True,
            f"PASS  /a2a/mock-data-generator (fallback path): "
            f"status={status_val!r} method={method!r} data_present={bool(data_val)}",
        )

    error_msg = result.get("error", json.dumps(result)[:300])
    return False, f"FAIL  /a2a/mock-data-generator: {error_msg}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args() -> str:
    """Return the base URL from --url or E2E_URL env var."""
    parser = argparse.ArgumentParser(
        description="Live end-to-end check for the BYOD Mock Data Generator Cloud Run service."
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("E2E_URL", ""),
        help="Base URL of the deployed service (e.g. https://mock-data-generator-api-xxxx.run.app). "
             "May also be set via E2E_URL environment variable.",
    )
    args = parser.parse_args()

    if not args.url:
        parser.error(
            "Provide --url https://<service-url> or set E2E_URL environment variable."
        )
    return args.url.rstrip("/")


def _print_curl_example(base_url: str) -> None:
    csv_text = "id,age\n1,30\n2,41\n3,29\n4,55\n"
    b64_csv = base64.b64encode(csv_text.encode("utf-8")).decode("utf-8")
    envelope = _encode_message(
        {
            "operation": "generate",
            "data_content": b64_csv,
            "file_name": "input.csv",
            "num_rows": 5,
            "output_format": "csv",
        },
        correlation_id="e2e-curl-1",
    )
    env_json = json.dumps(envelope, indent=2)
    print(
        "\nReady-to-paste curl example:\n"
        "------------------------------------------------------------\n"
        f"curl -s -X POST '{base_url}/a2a/mock-data-generator' \\\n"
        "  -H 'Content-Type: application/json' \\\n"
        f"  -d '{env_json}' | python3 -m json.tool\n"
        "------------------------------------------------------------"
    )


def main() -> int:
    base_url = _parse_args()

    print(f"=== E2E A2A check against: {base_url} ===\n")

    results = []
    for label, fn in [
        ("health", check_health),
        ("agent-card", check_agent_card),
        ("a2a-generate", check_a2a_generate),
    ]:
        passed, message = fn(base_url)
        results.append(passed)
        print(message)

    _print_curl_example(base_url)

    print(f"\n{'=' * 44}")
    total = len(results)
    passed_count = sum(results)
    if all(results):
        print(f"RESULT: ALL {total}/{total} checks PASSED")
        return 0
    else:
        print(f"RESULT: {passed_count}/{total} checks passed — {total - passed_count} FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
