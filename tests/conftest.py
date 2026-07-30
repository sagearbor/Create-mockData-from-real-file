"""Shared pytest configuration.

Several files under tests/ are integration tests that drive the HTTP API rather
than importing it: they need a server already listening on API_BASE_URL. Without
this hook they report as hard failures on a developer machine with no server
running, which buries real regressions in a wall of red.

Start the server first to run them:

    python main.py                       # or: uvicorn main:app --port 8201
    pytest                               # integration tests now execute

Override the target with API_BASE_URL=http://host:port pytest
"""

import os
import socket
from urllib.parse import urlparse

import pytest

DEFAULT_BASE_URL = "http://localhost:8201"


def api_base_url() -> str:
    return os.environ.get("API_BASE_URL", DEFAULT_BASE_URL)


def _server_is_reachable(url: str, timeout: float = 0.5) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def pytest_collection_modifyitems(config, items):
    """Skip server-dependent tests when nothing is listening."""
    marked = [item for item in items if item.get_closest_marker("requires_server")]
    if not marked:
        return

    url = api_base_url()
    if _server_is_reachable(url):
        return

    skip = pytest.mark.skip(
        reason=f"no API server reachable at {url} — start it with `python main.py`"
    )
    for item in marked:
        item.add_marker(skip)


@pytest.fixture(scope="session")
def base_url() -> str:
    """The API base URL used by the integration tests."""
    return api_base_url()
