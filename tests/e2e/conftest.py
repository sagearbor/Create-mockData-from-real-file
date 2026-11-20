"""Browser-level (e2e) tests for the Mock Data Generator.

How to run (the same command works for a local server and for a deployed site):

    MDG_BASE_URL=<address of the site> python -m pytest tests/e2e -m e2e -q \
        --junitxml=tmp/e2e-artifacts/results-e2e.xml

Environment variables:

* ``MDG_BASE_URL``  (required) address of the site under test. There is no default:
  when it is not set, every test in this folder is SKIPPED, so the ordinary
  ``pytest tests -q`` run never opens a browser or calls the AI model.
* ``MDG_API_KEY``   (optional) sent as ``X-API-Key`` to the ``/api/v1`` routes.
* ``MDG_BROWSER_CHANNEL`` (optional) e.g. ``chrome`` to use the installed Chrome
  instead of Playwright's own Chromium.
* ``MDG_HEADED=1``  (optional) show the browser window.

All test data is made up by the fixtures below. No real data is used.
On failure a screenshot and the page's console log are saved in ``tmp/e2e-artifacts/``.
"""

import csv
import json
import os
import re
from pathlib import Path

import pytest

BASE_URL_ENV = "MDG_BASE_URL"
API_KEY_ENV = "MDG_API_KEY"
E2E_DIR = Path(__file__).resolve().parent
REPO_ROOT = E2E_DIR.parents[1]
ARTIFACT_DIR = REPO_ROOT / "tmp" / "e2e-artifacts"

from mdg_e2e_support import (  # noqa: E402
    DATA_COLUMNS, DATA_ROW_COUNT, HOSTILE_HEADER, MARKER_NAME, SECOND_DICTIONARY,
    SINGLE_DICTIONARY, SITE_LABELS, TWO_TABLE_DICTIONARY)


def _base_url() -> str:
    return (os.environ.get(BASE_URL_ENV) or "").strip().rstrip("/")


def pytest_collection_modifyitems(config, items):
    """Skip every test in this folder when MDG_BASE_URL is not set (or Playwright is missing)."""
    ours = [item for item in items if E2E_DIR in Path(str(item.fspath)).resolve().parents]
    if not ours:
        return
    reason = None
    if not _base_url():
        reason = (f"{BASE_URL_ENV} is not set: browser-level tests need the address of a "
                  f"running site, e.g. {BASE_URL_ENV}=<site address> pytest tests/e2e -m e2e")
    else:
        try:
            import playwright.sync_api  # noqa: F401
        except ImportError:
            reason = "the playwright package is not installed (pip install playwright pytest-playwright)"
    if reason:
        skip = pytest.mark.skip(reason=reason)
        for item in ours:
            item.add_marker(skip)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Remember each phase's result on the test item, so fixtures can save evidence on failure."""
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"_e2e_report_{report.when}", report)


# --------------------------------------------------------------------------- #
# Site, browser, page
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="session")
def base_url() -> str:
    """Address of the site under test (overrides the fixture in tests/conftest.py)."""
    url = _base_url()
    if not url:
        pytest.skip(f"{BASE_URL_ENV} is not set")
    return url


@pytest.fixture(scope="session")
def api_key():
    return (os.environ.get(API_KEY_ENV) or "").strip() or None


@pytest.fixture(scope="session")
def e2e_playwright(base_url):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def e2e_browser(e2e_playwright):
    options = {"headless": os.environ.get("MDG_HEADED", "") not in ("1", "true", "yes")}
    channel = (os.environ.get("MDG_BROWSER_CHANNEL") or "").strip()
    if channel:
        options["channel"] = channel
    browser = e2e_playwright.chromium.launch(**options)
    yield browser
    browser.close()


class ConsoleLog:
    """What the page wrote to its console, and any script error it raised."""

    def __init__(self):
        self.lines = []
        self.errors = []

    def attach(self, page):
        def on_console(message):
            line = f"[{message.type}] {message.text}"
            self.lines.append(line)
            if message.type == "error":
                self.errors.append(line)

        def on_page_error(error):
            line = f"[pageerror] {error}"
            self.lines.append(line)
            self.errors.append(line)

        page.on("console", on_console)
        page.on("pageerror", on_page_error)


def _safe_name(nodeid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", nodeid.split("::")[-1])[:120]


@pytest.fixture
def make_page(e2e_browser, base_url, request):
    """Factory: a new page in its own browser context (its own cookies and storage).

    Every page made here is recorded; if the test fails, a screenshot and the
    console log of each page are saved under tmp/e2e-artifacts/.
    """
    made = []

    def _make(**context_options):
        context = e2e_browser.new_context(
            base_url=base_url, accept_downloads=True, ignore_https_errors=True,
            viewport={"width": 1400, "height": 1000}, **context_options)
        context.set_default_timeout(20_000)
        page = context.new_page()
        log = ConsoleLog()
        log.attach(page)
        page.console_log = log
        made.append((context, page, log))
        return page

    yield _make

    report = getattr(request.node, "_e2e_report_call", None)
    failed = report is not None and (report.failed or hasattr(report, "wasxfail"))
    for index, (context, page, log) in enumerate(made):
        if failed:
            ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
            stem = _safe_name(request.node.nodeid) + (f"_page{index + 1}" if len(made) > 1 else "")
            try:
                page.screenshot(path=str(ARTIFACT_DIR / f"{stem}.png"), full_page=True)
            except Exception as error:  # the page may already be closed
                log.lines.append(f"[screenshot failed] {error}")
            (ARTIFACT_DIR / f"{stem}.console.log").write_text(
                f"url: {page.url}\n" + "\n".join(log.lines) + "\n", encoding="utf-8")
        context.close()


@pytest.fixture
def mdg_page(make_page):
    """One browser page on the site under test.

    Not called ``page``: that name belongs to the pytest-playwright plugin, which
    would add "[chromium]" to every test name in the results file.
    """
    return make_page()


@pytest.fixture
def api(e2e_playwright, base_url):
    """Plain HTTP requests to the site (no browser page), for the refusal and API checks."""
    context = e2e_playwright.request.new_context(
        base_url=base_url, ignore_https_errors=True, timeout=200_000)
    yield context
    context.dispose()


# --------------------------------------------------------------------------- #
# Made-up test files (written fresh for every test; never real data)
# --------------------------------------------------------------------------- #

def _write_csv(path: Path, header, rows) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return path


@pytest.fixture
def marker_names():
    """Every made-up person name written into the sample data file."""
    return [f"{MARKER_NAME} {i}" for i in range(1, DATA_ROW_COUNT + 1)]


@pytest.fixture
def data_csv(tmp_path) -> Path:
    """A 40-row made-up 'visits' table with obviously fake values."""
    rows = []
    for i in range(1, DATA_ROW_COUNT + 1):
        rows.append([
            f"ZZ-{1000 + i}",
            f"{MARKER_NAME} {i}",
            "F" if i % 2 else "M",
            f"2031-{1 + i % 12:02d}-{1 + i % 28:02d}",
            round(50 + i * 1.3, 1),
            SITE_LABELS[i % len(SITE_LABELS)],
            f"Made-up note {i} for {MARKER_NAME} {i}",
        ])
    return _write_csv(tmp_path / "e2e_visits_made_up.csv", DATA_COLUMNS, rows)


@pytest.fixture
def hostile_csv(tmp_path) -> Path:
    """A made-up table whose middle column NAME is a piece of HTML that would run script
    if the page inserted it as HTML instead of showing it as text."""
    labels = ["alpha", "beta", "gamma"]
    rows = [[i, labels[i % 3], round(i * 2.5, 1)] for i in range(1, 13)]
    return _write_csv(tmp_path / "e2e_hostile_header_made_up.csv",
                      ["item_id", HOSTILE_HEADER, "amount"], rows)


def _write_json(path: Path, content) -> Path:
    path.write_text(json.dumps(content, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def dictionary_json(tmp_path) -> Path:
    """A small made-up data dictionary: six columns, two of them with allowed values."""
    return _write_json(tmp_path / "e2e_gadgets_dictionary_made_up.json", SINGLE_DICTIONARY)


@pytest.fixture
def second_dictionary_json(tmp_path) -> Path:
    """A different made-up dictionary (other column names), for the two-session test."""
    return _write_json(tmp_path / "e2e_kites_dictionary_made_up.json", SECOND_DICTIONARY)


@pytest.fixture
def two_table_dictionary_json(tmp_path) -> Path:
    """A made-up dictionary file that defines two tables: Orchard and Beehive."""
    return _write_json(tmp_path / "e2e_two_tables_dictionary_made_up.json", TWO_TABLE_DICTIONARY)
