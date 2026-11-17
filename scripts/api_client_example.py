#!/usr/bin/env python3
"""Small example client for the mock data generator's JSON API (/api/v1).

Standard library only, so another program can copy this file as-is.

    python scripts/api_client_example.py                       # http://localhost:8201
    python scripts/api_client_example.py --base-url http://host:8201 --api-key KEY

The base URL and key can also come from the environment:
MOCKDATA_API_URL and MOCKDATA_API_KEY. The key is only needed when the server
has MOCKDATA_API_KEY set. The demo sends a tiny made-up CSV; generation needs
the server to have AI configured, otherwise the error is printed.
"""

import argparse
import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

DEFAULT_BASE_URL = "http://localhost:8201"

# Made-up rows, not real data.
DEMO_CSV = (
    "widget_id,colour,weight_g\n"
    "W001,red,12.5\n"
    "W002,blue,14.1\n"
    "W003,green,11.8\n"
    "W004,red,13.2\n"
)


class MockDataClient:
    """health(), version() and generate() against one server."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None,
                 timeout: float = 300.0):
        self.base_url = (base_url or os.environ.get("MOCKDATA_API_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("MOCKDATA_API_KEY")
        self.timeout = timeout  # generation calls an LLM and can take a minute or more

    # -- request building (no network; this is what the tests check) ---------

    def build_request(self, method: str, path: str,
                      body: Optional[Dict[str, Any]] = None) -> urllib.request.Request:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        return urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)

    def build_generate_request(self, csv_text: Optional[str] = None,
                               file_bytes: Optional[bytes] = None, format: str = "csv",
                               num_rows: Optional[int] = None, match_threshold: float = 0.8,
                               use_cache: bool = True,
                               safety_mode: str = "balanced") -> urllib.request.Request:
        if (csv_text is None) == (file_bytes is None):
            raise ValueError("give exactly one of csv_text or file_bytes")
        body: Dict[str, Any] = {"match_threshold": match_threshold, "use_cache": use_cache,
                                "safety_mode": safety_mode}
        if csv_text is not None:
            body["csv_text"] = csv_text
        else:
            body["data_content"] = base64.b64encode(file_bytes).decode("ascii")
            body["format"] = format
        if num_rows is not None:
            body["num_rows"] = num_rows
        return self.build_request("POST", "/api/v1/generate", body)

    # -- calls ---------------------------------------------------------------

    def _send(self, request: urllib.request.Request) -> Tuple[int, Dict[str, Any]]:
        """Return (HTTP status, JSON body). API errors come back as a body, not an exception."""
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", "replace")
            try:
                return exc.code, json.loads(text)
            except ValueError:
                return exc.code, {"status": "error", "error": text, "error_class": "NonJsonResponse"}

    def health(self) -> Tuple[int, Dict[str, Any]]:
        return self._send(self.build_request("GET", "/health"))

    def version(self) -> Tuple[int, Dict[str, Any]]:
        return self._send(self.build_request("GET", "/api/v1/version"))

    def generate(self, **kwargs) -> Tuple[int, Dict[str, Any]]:
        return self._send(self.build_generate_request(**kwargs))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=None, help=f"default: $MOCKDATA_API_URL or {DEFAULT_BASE_URL}")
    parser.add_argument("--api-key", default=None, help="default: $MOCKDATA_API_KEY")
    parser.add_argument("--num-rows", type=int, default=5)
    args = parser.parse_args()

    client = MockDataClient(args.base_url, args.api_key)
    try:
        print("health  :", client.health())
        print("version :", client.version())
        status, body = client.generate(csv_text=DEMO_CSV, num_rows=args.num_rows)
    except urllib.error.URLError as exc:
        print(f"Could not reach {client.base_url}: {exc.reason}")
        return 2

    if status == 200:
        print(f"generate: {body['shape'][0]} rows x {body['shape'][1]} columns {body['columns']}")
        for row in body["data"]:
            print("  ", row)
        return 0
    print(f"generate: HTTP {status} {body.get('error_class')}: {body.get('error')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
