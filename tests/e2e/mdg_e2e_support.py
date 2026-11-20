"""Helpers shared by the browser-level (e2e) tests.

Everything here drives the real page through its real element ids (read from
src/web/index.html and src/web/static/js/app.js). No hostname lives in this
folder: the site under test comes only from the MDG_BASE_URL environment variable.
"""

import csv
import io
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # the tests are skipped (see conftest.py) when Playwright is not installed
    from playwright.sync_api import expect
except ImportError:  # pragma: no cover
    expect = None

Page = Response = Any  # only used as hints below

# One generation = one AI call that writes a script, plus running it.
GENERATION_TIMEOUT_MS = 180_000
SHORT_TIMEOUT_MS = 20_000

# The six progress steps the page shows while it generates from a data file.
PROGRESS_STEPS = ["extract-metadata", "check-cache", "prepare-llm",
                  "generate-code", "execute-code", "validate"]

PREVIEW_ROW_LIMIT = 50


# --------------------------------------------------------------------------- #
# Made-up test data (never real data)
# --------------------------------------------------------------------------- #

# Obviously made-up values. The name marker must never come back from the service.
MARKER_NAME = "Zzyzx Quillfeather"
DATA_COLUMNS = ["patient_id", "patient_name", "sex", "visit_date", "weight_kg", "site", "notes"]
DATA_ROW_COUNT = 40
SITE_LABELS = ["Northfield Test Site", "Lakemont Test Site", "Brindle Test Site", "Ostrava Test Site"]
HOSTILE_HEADER = '<img src=x onerror="window.__xss=1">'


SINGLE_DICTIONARY = {
    "columns": {
        "gadget_code": {"type": "string", "description": "Made-up gadget code, e.g. GX-0001"},
        "gadget_colour": {"type": "categorical", "description": "Colour of the gadget",
                          "constraints": {"allowed_values": ["teal", "ochre", "mauve"]}},
        "length_mm": {"type": "integer", "description": "Length in millimetres",
                      "constraints": {"min_value": 10, "max_value": 500}},
        "mass_g": {"type": "float", "description": "Mass in grams",
                   "constraints": {"min_value": 1, "max_value": 900}},
        "checked_on": {"type": "date", "description": "Date the gadget was checked"},
        "passed_check": {"type": "categorical", "description": "Result of the check",
                         "constraints": {"allowed_values": ["yes", "no"]}},
    }
}

SECOND_DICTIONARY = {
    "columns": {
        "kite_label": {"type": "string", "description": "Made-up kite label, e.g. KT-01"},
        "kite_shape": {"type": "categorical", "description": "Shape of the kite",
                       "constraints": {"allowed_values": ["delta", "box", "diamond"]}},
        "span_cm": {"type": "integer", "description": "Wing span in centimetres",
                    "constraints": {"min_value": 30, "max_value": 400}},
        "line_length_m": {"type": "float", "description": "Line length in metres",
                          "constraints": {"min_value": 5, "max_value": 150}},
        "flown_on": {"type": "date", "description": "Date of the flight"},
    }
}

# Two tables in one file (a JSON Schema with two definitions): the page must ask which one.
TWO_TABLE_DICTIONARY = {
    "title": "Made-up farm records",
    "$defs": {
        "Orchard": {
            "type": "object",
            "properties": {
                "orchard_code": {"type": "string", "description": "Made-up orchard code"},
                "tree_count": {"type": "integer", "minimum": 1, "maximum": 5000},
                "fruit_kind": {"type": "string", "enum": ["apple", "pear", "quince"]},
                "planted_on": {"type": "string", "format": "date"},
            },
            "required": ["orchard_code"],
        },
        "Beehive": {
            "type": "object",
            "properties": {
                "hive_code": {"type": "string", "description": "Made-up hive code"},
                "frame_count": {"type": "integer", "minimum": 4, "maximum": 12},
                "queen_marked": {"type": "string", "enum": ["yes", "no"]},
                "honey_kg": {"type": "number", "minimum": 0, "maximum": 60},
                "inspected_on": {"type": "string", "format": "date"},
            },
            "required": ["hive_code"],
        },
    },
}


# --------------------------------------------------------------------------- #
# Page actions
# --------------------------------------------------------------------------- #

def open_home(page: Page) -> None:
    """Open the home page and wait until the model list has been filled from the server."""
    with page.expect_response(lambda r: r.url.endswith("/api/models"), timeout=SHORT_TIMEOUT_MS):
        page.goto("/")
    page.wait_for_function(
        "() => { const s = document.getElementById('modelSelect');"
        " return s && s.options.length > 0 && s.options[0].value !== ''; }",
        timeout=SHORT_TIMEOUT_MS)


def upload_data_file(page: Page, path: Path) -> None:
    """Put a file in the 'Upload Data File' box (the hidden file input behind it)."""
    page.set_input_files("#fileInput", str(path))
    # app.js shows this section as soon as it has taken the file.
    expect(page.locator("#experimentalSection")).to_be_visible(timeout=SHORT_TIMEOUT_MS)


def upload_dictionary(page: Page, path: Path) -> Dict[str, Any]:
    """Put a file in the 'Upload Data Dictionary' box; returns the server's JSON answer."""
    with page.expect_response(lambda r: r.url.endswith("/dictionary/upload"),
                              timeout=SHORT_TIMEOUT_MS) as info:
        page.set_input_files("#dictionaryFileInput", str(path))
    response = info.value
    assert response.status == 200, f"dictionary upload answered {response.status}: {response.text()[:300]}"
    expect(page.locator("#dictionaryInfo")).to_be_visible(timeout=SHORT_TIMEOUT_MS)
    wait_overlay_gone(page)
    return response.json()


# Records the text fields of every form the page sends (never the file itself), so a
# test can check which settings really went to the server.
RECORD_SENT_FORMS = """
(() => {
  window.__sentForms = [];
  const realFetch = window.fetch;
  window.fetch = function (url, options) {
    try {
      if (options && options.body instanceof FormData) {
        const fields = {};
        for (const [key, value] of options.body.entries()) {
          if (typeof value === 'string') fields[key] = value;
        }
        window.__sentForms.push({url: String(url), fields: fields});
      }
    } catch (e) { /* recording must never break the page */ }
    return realFetch.apply(this, arguments);
  };
})();
"""


def sent_form_fields(page: Page, url_ending: str) -> Dict[str, str]:
    """Text fields of the last form the page sent to a route (needs RECORD_SENT_FORMS)."""
    forms = [f for f in page.evaluate("() => window.__sentForms || []") if f["url"].endswith(url_ending)]
    assert forms, f"the page sent no form to {url_ending}"
    return forms[-1]["fields"]


def set_rows(page: Page, rows: int) -> None:
    page.fill("#numRows", str(rows))


def wait_overlay_gone(page: Page, timeout: int = SHORT_TIMEOUT_MS) -> None:
    """The grey 'working' overlay covers the buttons; wait until it is gone."""
    expect(page.locator("#loadingOverlay")).to_be_hidden(timeout=timeout)


def error_text(page: Page) -> str:
    """Text of the error box if it is showing, else ''."""
    modal = page.locator("#errorModal")
    return page.locator("#errorMessage").inner_text() if modal.is_visible() else ""


def wait_for_preview(page: Page, timeout: int = GENERATION_TIMEOUT_MS) -> None:
    """Wait until the preview table has rows, or fail with the page's own error text."""
    page.wait_for_function(
        "() => document.querySelectorAll('#previewBody tr').length > 0"
        " || getComputedStyle(document.getElementById('errorModal')).display !== 'none'",
        timeout=timeout)
    shown_error = error_text(page)
    assert not shown_error, f"the page showed an error instead of a preview: {shown_error}"
    # The preview box opens a moment after its rows are filled in.
    expect(page.locator("#previewSection[open]")).to_be_visible()
    expect(page.locator("#previewInfo")).not_to_be_empty()
    wait_overlay_gone(page)


def click_generate(page: Page) -> None:
    page.click("#generateBtn")


def generate_from_file(page: Page) -> Dict[str, Any]:
    """Click Generate for an uploaded data file; wait for the preview.

    Returns the final message of the progress stream the page received (the
    preview rows, the column names, the row count and how the data was made).
    """
    with page.expect_response(lambda r: r.url.endswith("/generate-sse"),
                              timeout=GENERATION_TIMEOUT_MS) as info:
        click_generate(page)
    response = info.value
    assert response.status == 200, f"/generate-sse answered {response.status}: {response.text()[:300]}"
    wait_for_preview(page)
    return final_stream_message(response)


def generate_from_dictionary(page: Page) -> Dict[str, Any]:
    """Click Generate with only a dictionary loaded; wait for the preview.

    Returns the server's JSON answer for the preview.
    """
    with page.expect_response(lambda r: r.url.endswith("/generate-with-dictionary"),
                              timeout=GENERATION_TIMEOUT_MS) as info:
        click_generate(page)
    response = info.value
    body = response.text()
    assert response.status == 200, f"/generate-with-dictionary answered {response.status}: {body[:300]}"
    wait_for_preview(page)
    return json.loads(body)


def final_stream_message(response: Response) -> Dict[str, Any]:
    """The last 'complete' message of a /generate-sse answer (waits for the stream to end)."""
    response.finished()
    messages = stream_messages(response.text())
    done = [m for m in messages if m.get("complete")]
    assert done, f"the progress stream ended without a result; messages: {messages[-3:]}"
    return done[-1]


def stream_messages(text: str) -> List[Dict[str, Any]]:
    out = []
    for line in text.splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[len("data: "):]))
    return out


def download_via(page: Page, button_selector: str, target_dir: Path):
    """Click a download button and save the file. Returns (path, suggested file name)."""
    wait_overlay_gone(page)
    with page.expect_download(timeout=GENERATION_TIMEOUT_MS) as info:
        page.click(button_selector)
    download = info.value
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / download.suggested_filename
    download.save_as(str(path))
    wait_overlay_gone(page, timeout=GENERATION_TIMEOUT_MS)
    return path, download.suggested_filename


# --------------------------------------------------------------------------- #
# Reading the page
# --------------------------------------------------------------------------- #

def preview_headers(page: Page) -> List[str]:
    return page.locator("#previewHead th").all_text_contents()


def preview_rows(page: Page) -> List[List[str]]:
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('#previewBody tr')).map("
        "tr => Array.from(tr.querySelectorAll('td')).map(td => td.textContent))")


def preview_sentence(page: Page) -> str:
    return page.locator("#previewInfo").inner_text()


def stated_row_count(sentence: str) -> int:
    """The row count in the sentence above the preview table ('40 rows × 7 columns ...')."""
    match = re.search(r"([\d,]+)\s+rows\s+×", sentence)
    assert match, f"no row count found in the preview sentence: {sentence!r}"
    return int(match.group(1).replace(",", ""))


def badges_text(page: Page) -> str:
    return page.locator("#generationBadges").inner_text()


def select_values(page: Page, selector: str) -> List[str]:
    return page.evaluate(
        "(sel) => Array.from(document.querySelector(sel).options).map(o => o.value)", selector)


# --------------------------------------------------------------------------- #
# Reading downloaded files and comparing rows
# --------------------------------------------------------------------------- #

def read_csv_rows(data: bytes) -> List[List[str]]:
    """Header row first, then data rows, each a list of text cells."""
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))


def normalise_cell(value: Any) -> str:
    """One cell as comparable text: numbers by value, midnight timestamps as dates,
    empty / missing as ''. Used to compare a preview row with a downloaded row."""
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in ("", "nan", "none", "null", "nat"):
        return ""
    if text.lower() in ("true", "false"):
        return text.lower()
    match = re.match(r"^(\d{4}-\d{2}-\d{2})[T ]00:00:00(\.0+)?(Z|[+-]00:?00)?$", text)
    if match:
        return match.group(1)
    try:
        number = float(text)
        return repr(round(number, 6))
    except ValueError:
        return text


def normalise_row(cells: List[Any]) -> List[str]:
    return [normalise_cell(c) for c in cells]


def api_headers(api_key: Optional[str]) -> Dict[str, str]:
    """Headers for /api/v1 requests: the key only when the site needs one."""
    return {"X-API-Key": api_key} if api_key else {}
