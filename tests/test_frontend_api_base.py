"""Regression: the web UI must call the API on its own origin.

Bug (2026-11-10, ACA image fd6087d): app.js rewrote API_BASE to
http://<hostname>:8201 whenever location.port != '8201'. On Azure Container Apps
the page is https://<fqdn> (no port), so every API call went to
http://<fqdn>:8201/... and the UI showed "Error: Failed to fetch".

Offline: reads the static files; the behavioural check runs resolveApiBase()
under node when node is installed, and is skipped otherwise.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "src" / "web"
APP_JS = WEB / "static" / "js" / "app.js"


def _resolve_api_base_source() -> str:
    src = APP_JS.read_text(encoding="utf-8")
    m = re.search(r"function resolveApiBase\(loc\) \{.*?\n\}", src, re.S)
    assert m, "app.js must define function resolveApiBase(loc)"
    return m.group(0)


def test_api_base_uses_resolver_on_window_location():
    src = APP_JS.read_text(encoding="utf-8")
    assert "const API_BASE = resolveApiBase(window.location);" in src


def test_no_port_8201_rewrite_for_http_origins():
    fn = _resolve_api_base_source()
    # The only :8201 literal allowed is the file:// fallback.
    assert fn.count(":8201") == 1
    assert "'file:'" in fn
    assert "hostname" not in fn and "location.port" not in fn


def test_static_frontend_has_no_other_hardcoded_api_hosts():
    """fetch() calls in static JS and the HTML pages must be relative or use API_BASE."""
    offenders = []
    files = list((WEB / "static" / "js").glob("*.js")) + list(WEB.glob("*.html"))
    for f in files:
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"fetch\(\s*[`'\"]https?://", line):
                offenders.append(f"{f.name}:{i}: {line.strip()}")
    assert not offenders, offenders


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize(
    "loc, expected",
    [
        # Hosted on ACA: HTTPS ingress, no explicit port -> same origin.
        ({"protocol": "https:", "hostname": "mock-data-generator.example.azurecontainerapps.io", "port": ""}, ""),
        # Local uvicorn on the default port.
        ({"protocol": "http:", "hostname": "127.0.0.1", "port": "8201"}, ""),
        ({"protocol": "http:", "hostname": "localhost", "port": "8201"}, ""),
        # Local uvicorn on any other port.
        ({"protocol": "http:", "hostname": "localhost", "port": "8299"}, ""),
        # Opened straight from disk: no server origin, use local dev server.
        ({"protocol": "file:", "hostname": "", "port": ""}, "http://127.0.0.1:8201"),
    ],
)
def test_resolve_api_base_behaviour(loc, expected):
    script = _resolve_api_base_source() + f"\nprocess.stdout.write(JSON.stringify(resolveApiBase({json.dumps(loc)})));\n"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30, check=True)
    assert json.loads(out.stdout) == expected
