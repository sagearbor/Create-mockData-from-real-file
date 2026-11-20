"""Browser tests of the home page: upload a data file, generate, preview, download.

Run with MDG_BASE_URL set (see conftest.py). Every test uploads only the made-up
files written by the fixtures. Tests that generate data make a real AI call.
"""

import io
import json
import re
import zipfile

import pytest
import mdg_e2e_support as s
from mdg_e2e_support import expect
from mdg_e2e_support import DATA_COLUMNS, DATA_ROW_COUNT, HOSTILE_HEADER, MARKER_NAME, SITE_LABELS

pytestmark = pytest.mark.e2e

# Requirement ids (RS section 1.4) each test checks.
REQUIREMENTS = {
    "test_E2E_01_home_page_loads": ["MDG-REQ-021"],
    "test_E2E_02_upload_generate_preview": ["MDG-REQ-001", "MDG-REQ-002", "MDG-REQ-003",
                                            "MDG-REQ-004", "MDG-REQ-011"],
    "test_E2E_03_download_csv": ["MDG-REQ-012"],
    "test_E2E_04_rows_setting": ["MDG-REQ-004", "MDG-REQ-011"],
    "test_E2E_05_several_files_zip": ["MDG-REQ-013"],
    "test_E2E_06_json_and_excel_download": ["MDG-REQ-012"],
    "test_E2E_07_model_choice_and_strict_privacy": ["MDG-REQ-015", "MDG-REQ-021", "MDG-REQ-023"],
    "test_E2E_08_extract_metadata_only": ["MDG-REQ-007", "MDG-REQ-016"],
    "test_E2E_09_hostile_column_name_shown_as_text": ["MDG-REQ-049"],
    "test_E2E_17_upload_notice_is_truthful": ["MDG-REQ-017", "MDG-REQ-056"],
    "test_E2E_18_unreadable_file_shows_plain_error": ["MDG-REQ-035"],
}

# Rows asked for by the tests that set the Rows box (small, to keep runs quick).
ROWS_SMALL = 25


def _preview_from_file(page, data_csv, rows=ROWS_SMALL):
    """Open the page, upload the made-up file, set Rows, Generate, wait for the preview."""
    s.open_home(page)
    s.upload_data_file(page, data_csv)
    s.set_rows(page, rows)
    return s.generate_from_file(page)


def test_E2E_01_home_page_loads(mdg_page, api):
    """Home page loads with the AI model and Privacy choices filled in.

    Objective: the page opens without script errors, the "AI model" list comes from
    the server with the server's default selected, and "Privacy" offers three modes.

    Precondition: the site is running.

    Steps:
    1. Open the home page.
    2. Ask the server for its list of AI models (GET /api/models).
    3. Read the choices in the "AI model" box and which one is selected.
    4. Read the choices in the "Privacy" box.
    5. Read the browser console.

    Expected result: the "AI model" box lists exactly the server's models, in the
    server's order, with the server's default selected and labelled "(default)".
    "Privacy" offers Balanced, Strict and Permissive, with Balanced selected.
    The upload boxes and the two action buttons are visible. The console has no errors.
    """
    page = mdg_page
    s.open_home(page)
    catalog = api.get("/api/models").json()
    names = [m["name"] for m in catalog["models"]]

    assert s.select_values(page, "#modelSelect") == names
    assert page.input_value("#modelSelect") == catalog["default"]
    selected_label = page.locator("#modelSelect option:checked").inner_text()
    assert "(default)" in selected_label, f"selected option is labelled {selected_label!r}"

    assert s.select_values(page, "#privacyMode") == ["balanced", "strict", "permissive"]
    assert page.input_value("#privacyMode") == "balanced"

    expect(page.locator("#uploadArea")).to_be_visible()
    expect(page.locator("#dictionaryUploadArea")).to_be_visible()
    expect(page.locator("#generateBtn")).to_be_visible()
    expect(page.locator("#extractMetadataBtn")).to_be_visible()

    page.wait_for_load_state("networkidle")
    assert page.console_log.errors == [], f"console errors on the home page: {page.console_log.errors}"


def test_E2E_02_upload_generate_preview(mdg_page, data_csv):
    """Upload a data file and generate with the default settings.

    Objective: with no setting changed, the page generates made-up data that has the
    uploaded file's column names in the same order and the same number of rows, shows
    its progress, and says plainly whether the preview shows all rows.

    Precondition: the site is running and its AI model is set up.

    Steps:
    1. Open the home page.
    2. Upload the made-up file (40 rows; columns patient_id, patient_name, sex,
       visit_date, weight_kg, site, notes).
    3. Leave every setting as it is (Rows box empty) and click "Generate Synthetic Data".
    4. Watch the progress steps.
    5. When the preview appears, read the column headings, the sentence above the
       table, and count the rows in the table.

    Expected result: the six progress steps are shown (Extract Metadata, Check Cache,
    AI Response, Generate Code, Create Data, Validate Output) and the first is ticked.
    The preview's column headings equal the uploaded file's, in the same order. The
    sentence says 40 rows and 7 columns were generated and that all 40 rows are shown;
    the table has 40 rows. A badge says whether the AI model or a saved script was used.
    """
    page = mdg_page
    s.open_home(page)
    s.upload_data_file(page, data_csv)
    assert page.input_value("#numRows") == "", "the Rows box should start empty"

    with page.expect_response(lambda r: r.url.endswith("/generate-sse"),
                              timeout=s.GENERATION_TIMEOUT_MS) as info:
        s.click_generate(page)
    assert info.value.status == 200

    expect(page.locator("#progressFlow")).to_be_visible()
    steps = page.locator("#progressFlow .progress-step")
    assert steps.evaluate_all("els => els.map(e => e.dataset.step)") == s.PROGRESS_STEPS
    expect(page.locator('.progress-step[data-step="extract-metadata"]')).to_have_class(
        re.compile(r"\bcompleted\b"), timeout=s.GENERATION_TIMEOUT_MS)

    s.wait_for_preview(page)
    result = s.final_stream_message(info.value)

    assert s.preview_headers(page) == DATA_COLUMNS
    sentence = s.preview_sentence(page)
    table_rows = s.preview_rows(page)
    assert s.stated_row_count(sentence) == DATA_ROW_COUNT, (
        f"with the Rows box empty the result should match the uploaded file's "
        f"{DATA_ROW_COUNT} rows; the page says: {sentence!r}")
    assert f"× {len(DATA_COLUMNS)} columns" in sentence
    assert f"all {DATA_ROW_COUNT} rows are shown below" in sentence
    assert len(table_rows) == DATA_ROW_COUNT
    assert result["column_names"] == DATA_COLUMNS
    assert result["total_rows"] == DATA_ROW_COUNT

    badges = s.badges_text(page)
    assert "LLM" in badges or "CACHED" in badges, f"no generation badge shown: {badges!r}"


def test_E2E_03_download_csv(mdg_page, data_csv, tmp_path):
    """Download the generated data as a CSV file.

    Objective: after a preview, "Download File" saves a CSV file holding the heading
    row and the number of rows that was asked for.

    Precondition: the site is running and its AI model is set up.

    Steps:
    1. Open the home page and upload the made-up file.
    2. Type 25 in the Rows box and click "Generate Synthetic Data".
    3. When the preview appears, click "Download File".
    4. Open the saved file.

    Expected result: a file whose name ends in ".csv" is saved. Its first line holds
    the uploaded file's column names in the same order. It has exactly 25 data rows.
    """
    page = mdg_page
    _preview_from_file(page, data_csv)
    assert s.stated_row_count(s.preview_sentence(page)) == ROWS_SMALL

    path, name = s.download_via(page, "#downloadFileBtn", tmp_path / "downloads")
    assert not s.error_text(page), f"download showed an error: {s.error_text(page)}"
    assert name.endswith(".csv"), f"downloaded file is named {name!r}"

    rows = s.read_csv_rows(path.read_bytes())
    assert rows[0] == DATA_COLUMNS
    assert len(rows) - 1 == ROWS_SMALL, f"expected {ROWS_SMALL} data rows, the file has {len(rows) - 1}"


def test_E2E_04_rows_setting(mdg_page, data_csv):
    """Ask for more rows than the preview can show.

    Objective: the Rows setting is honoured, and when there are more rows than the
    preview shows, the page says so plainly.

    Precondition: the site is running and its AI model is set up.

    Steps:
    1. Open the home page and upload the made-up file (40 rows).
    2. Type 60 in the Rows box and click "Generate Synthetic Data".
    3. Read the sentence above the preview table and count the rows in the table.

    Expected result: the sentence says 60 rows were generated, that the first 50 are
    shown, and that the download gives all 60. The table has exactly 50 rows.
    """
    page = mdg_page
    result = _preview_from_file(page, data_csv, rows=60)

    sentence = s.preview_sentence(page)
    assert s.stated_row_count(sentence) == 60
    assert f"the first {s.PREVIEW_ROW_LIMIT} are shown below" in sentence
    assert "Download gives all 60" in sentence
    assert len(s.preview_rows(page)) == s.PREVIEW_ROW_LIMIT
    assert result["total_rows"] == 60
    assert s.preview_headers(page) == DATA_COLUMNS


def test_E2E_05_several_files_zip(mdg_page, data_csv, tmp_path):
    """Ask for three files and get them as one zip file.

    Objective: when more than one file is asked for, the download is a single zip
    file holding that many files, each with the rows asked for.

    Precondition: the site is running and its AI model is set up.

    Steps:
    1. Open the home page and upload the made-up file.
    2. Type 25 in the Rows box, choose 3 in the Files box, click "Generate Synthetic Data".
    3. When the preview appears, click "Download ZIP".
    4. Open the saved zip file and each file in it.

    Expected result: the page says "3 files generated" and offers "Download ZIP".
    The saved file's name ends in ".zip". It holds exactly 3 files with names ending
    in ".csv". Each has the uploaded file's column names and exactly 25 data rows.
    """
    page = mdg_page
    s.open_home(page)
    s.upload_data_file(page, data_csv)
    s.set_rows(page, ROWS_SMALL)
    page.select_option("#fileCount", "3")
    s.generate_from_file(page)

    assert "3 files generated" in s.preview_sentence(page)
    expect(page.locator("#downloadZipBtn")).to_be_visible()
    expect(page.locator("#downloadFileBtn")).to_be_hidden()

    path, name = s.download_via(page, "#downloadZipBtn", tmp_path / "downloads")
    assert not s.error_text(page), f"download showed an error: {s.error_text(page)}"
    assert name.endswith(".zip"), f"downloaded file is named {name!r}"

    with zipfile.ZipFile(path) as archive:
        members = archive.namelist()
        assert len(members) == 3, f"zip holds {members}"
        assert all(m.endswith(".csv") for m in members), f"zip holds {members}"
        assert len(set(members)) == 3
        for member in members:
            rows = s.read_csv_rows(archive.read(member))
            assert rows[0] == DATA_COLUMNS, f"{member}: heading row is {rows[0]}"
            assert len(rows) - 1 == ROWS_SMALL, f"{member}: {len(rows) - 1} data rows"


def test_E2E_06_json_and_excel_download(mdg_page, data_csv, tmp_path):
    """Download the generated data as JSON and as Excel.

    Objective: the JSON download is a list of rows, and the Excel download is a
    workbook that opens and has the right columns.

    Precondition: the site is running and its AI model is set up.

    Steps:
    1. Open the home page and upload the made-up file.
    2. Type 25 in the Rows box, choose JSON in the Format box, click
       "Generate Synthetic Data".
    3. When the preview appears, click "Download File" and open the saved file.
    4. Open "Generation Settings" again, change Format to Excel (no new generation),
       click "Download File" and open the saved file.

    Expected result:
    - JSON: the file name ends in ".json"; the file is a list of 25 row objects, each
      with the uploaded file's column names (not a wrapper around the rows).
    - Excel: the file name ends in ".xlsx"; the workbook opens; its first row holds
      the uploaded file's column names in order; it has 25 data rows.
    """
    page = mdg_page
    openpyxl = pytest.importorskip("openpyxl")
    problems = []

    s.open_home(page)
    s.upload_data_file(page, data_csv)
    s.set_rows(page, ROWS_SMALL)
    page.select_option("#outputFormat", "json")
    s.generate_from_file(page)

    # --- JSON ---
    json_path, json_name = s.download_via(page, "#downloadFileBtn", tmp_path / "json")
    assert not s.error_text(page), f"JSON download showed an error: {s.error_text(page)}"
    if not json_name.endswith(".json"):
        problems.append(f"JSON download is named {json_name!r}, expected a name ending in .json")
    parsed = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list):
        keys = list(parsed)[:8] if isinstance(parsed, dict) else type(parsed).__name__
        problems.append(
            "JSON download is not a list of row objects: the file's top level is "
            f"{type(parsed).__name__} with keys {keys}")
        rows_in_file = parsed.get("data") if isinstance(parsed, dict) else None
    else:
        rows_in_file = parsed
    if isinstance(rows_in_file, list):
        if len(rows_in_file) != ROWS_SMALL:
            problems.append(f"JSON download holds {len(rows_in_file)} rows, expected {ROWS_SMALL}")
        if not all(isinstance(r, dict) and list(r) == DATA_COLUMNS for r in rows_in_file):
            problems.append("JSON rows do not all have the uploaded file's column names in order")

    # --- Excel, from the same preview: only the Format box is changed ---
    page.locator("#configSection > summary .section-header").click()
    expect(page.locator("#outputFormat")).to_be_visible()
    page.select_option("#outputFormat", "excel")
    xlsx_path, xlsx_name = s.download_via(page, "#downloadFileBtn", tmp_path / "excel")
    assert not s.error_text(page), f"Excel download showed an error: {s.error_text(page)}"
    if not xlsx_name.endswith(".xlsx"):
        problems.append(f"Excel download is named {xlsx_name!r}, expected a name ending in .xlsx")
    workbook = openpyxl.load_workbook(io.BytesIO(xlsx_path.read_bytes()), read_only=True)
    sheet_rows = list(workbook.active.iter_rows(values_only=True))
    if list(sheet_rows[0]) != DATA_COLUMNS:
        problems.append(f"Excel heading row is {list(sheet_rows[0])}")
    if len(sheet_rows) - 1 != ROWS_SMALL:
        problems.append(f"Excel download holds {len(sheet_rows) - 1} data rows, expected {ROWS_SMALL}")

    assert not problems, "Download format problems:\n- " + "\n- ".join(problems)


def test_E2E_07_model_choice_and_strict_privacy(mdg_page, data_csv, marker_names):
    """Generate with another AI model and Strict privacy.

    Objective: the chosen AI model is the one used and the page says so; in Strict
    privacy no text from the uploaded file comes back in the generated rows.

    Precondition: the site is running, its AI model is set up, and the server offers
    at least two AI models.

    Steps:
    1. Open the home page and upload the made-up file (every patient_name starts with
       "Zzyzx Quillfeather"; every site ends with "Test Site").
    2. In the "AI model" box choose the first model that is not the default.
    3. In the "Privacy" box choose Strict.
    4. Type 25 in the Rows box and click "Generate Synthetic Data".
    5. Read the badges above the preview, the server's answer for the preview, and
       the preview rows.

    Expected result: the request the page sent names the chosen model and Strict.
    The server's answer names the chosen model as the one that wrote the generation
    script. A badge above the preview shows that model's name, and hovering it says
    it is the AI model that wrote the generation code. No made-up person name and no
    site label from the uploaded file appears in the previewed rows.
    """
    page = mdg_page
    page.add_init_script(s.RECORD_SENT_FORMS)
    s.open_home(page)
    default_model = page.input_value("#modelSelect")
    others = [v for v in s.select_values(page, "#modelSelect") if v and v != default_model]
    if not others:
        pytest.skip("the server offers only one AI model, so no other model can be chosen")
    chosen = others[0]

    s.upload_data_file(page, data_csv)
    page.select_option("#modelSelect", chosen)
    page.select_option("#privacyMode", "strict")
    s.set_rows(page, ROWS_SMALL)

    with page.expect_response(lambda r: r.url.endswith("/generate-sse"),
                              timeout=s.GENERATION_TIMEOUT_MS) as info:
        s.click_generate(page)
    response = info.value
    assert response.status == 200, response.text()[:300]
    sent = s.sent_form_fields(page, "/generate-sse")
    assert sent.get("model") == chosen, f"the page sent model {sent.get('model')!r}"
    assert sent.get("safety_mode") == "strict", f"the page sent privacy {sent.get('safety_mode')!r}"

    s.wait_for_preview(page)
    result = s.final_stream_message(response)

    assert result["generation_info"].get("model") == chosen, (
        f"server reports model {result['generation_info'].get('model')!r}, chosen was {chosen!r}")

    model_badge = page.locator("#generationBadges .badge-model")
    expect(model_badge).to_be_visible()
    assert chosen in model_badge.inner_text()
    model_badge.hover()
    assert "AI model that wrote" in (model_badge.get_attribute("title") or "")

    assert s.preview_headers(page) == DATA_COLUMNS
    preview_text = "\n".join(" | ".join(row) for row in s.preview_rows(page))
    returned_text = json.dumps(result["preview"])
    for text, where in ((preview_text, "the preview table"), (returned_text, "the server's answer")):
        assert MARKER_NAME not in text and "Quillfeather" not in text and "Zzyzx" not in text, \
            f"a made-up person name from the uploaded file appears in {where}"
        leaked = [name for name in marker_names if name in text]
        assert not leaked, f"names from the uploaded file appear in {where}: {leaked[:3]}"
        leaked_sites = [label for label in SITE_LABELS if label in text]
        assert not leaked_sites, (
            f"Strict privacy: site labels from the uploaded file appear in {where}: {leaked_sites}")


def test_E2E_08_extract_metadata_only(mdg_page, data_csv, marker_names):
    """Extract Metadata Only shows the description of the file without generating data.

    Objective: the description lists the columns; in Balanced privacy, values of the
    name column are replaced by placeholders while the labels of the repeated
    category "sex" are kept; no person name from the file is in the description.

    Precondition: the site is running. No AI call is made.

    Steps:
    1. Open the home page and upload the made-up file. Leave Privacy on Balanced.
    2. Click "Extract Metadata Only".
    3. Read the summary ("Metadata Extracted") and the "Extracted Metadata" panel.

    Expected result: the summary says 40 rows and 7 columns and lists the seven
    column names in order. In the panel, the most common values of patient_name are
    placeholders (value_0, value_1, ...), and those of sex are the real labels F and M.
    No "Zzyzx Quillfeather" name appears in the summary, in the panel, or in the
    server's answer. No preview of generated data is shown.

    Note: the page also shows the uploaded file's own rows in "Data Preview & Editor";
    the browser reads those from the file itself, so that box is not part of this check.
    """
    page = mdg_page
    s.open_home(page)
    s.upload_data_file(page, data_csv)
    assert page.input_value("#privacyMode") == "balanced"

    with page.expect_response(lambda r: r.url.endswith("/metadata"), timeout=s.SHORT_TIMEOUT_MS) as info:
        page.click("#extractMetadataBtn")
    response = info.value
    assert response.status == 200, response.text()[:300]
    expect(page.locator("#metadataSection")).to_be_visible()
    s.wait_overlay_gone(page)

    summary = page.locator("#resultsContent")
    expect(summary).to_be_visible()
    assert page.locator("#resultsContent li strong").all_text_contents() == DATA_COLUMNS
    summary_text = summary.inner_text()
    assert f"Rows: {DATA_ROW_COUNT}" in summary_text
    assert f"Columns: {len(DATA_COLUMNS)}" in summary_text

    panel_text = page.locator("#metadataContent").inner_text()
    shown = json.loads(panel_text)
    name_values = shown["statistics"]["patient_name"]["most_common_values"]
    assert name_values, "no most-common values listed for patient_name"
    assert all(re.fullmatch(r"value_\d+", key) for key in name_values), \
        f"patient_name values are not all placeholders: {list(name_values)}"
    assert set(shown["statistics"]["sex"]["most_common_values"]) == {"F", "M"}

    for text, where in ((summary_text, "the summary"), (panel_text, "the Extracted Metadata panel"),
                        (response.text(), "the server's answer")):
        assert "Quillfeather" not in text and "Zzyzx" not in text, f"a person name appears in {where}"
        assert not [n for n in marker_names if n in text]

    expect(page.locator("#previewSection")).to_be_hidden()


def test_E2E_09_hostile_column_name_shown_as_text(mdg_page, hostile_csv):
    """A column name that is a piece of HTML is shown as text and never runs.

    Objective: text from an uploaded file is shown as text. A column whose name is
    an HTML image tag with a script in it must appear literally and must not run.

    Precondition: the site is running and its AI model is set up.

    Steps:
    1. Open the home page and upload the made-up file whose middle column is named
       <img src=x onerror="window.__xss=1"> (12 rows, values alpha / beta / gamma).
    2. Click "Extract Metadata Only". Look at the summary.
    3. Type 12 in the Rows box and click "Generate Synthetic Data". Look at the
       preview's column headings.
    4. Open the Usage Dashboard page and look at the list of saved scripts.

    Expected result: on every page the column name is visible exactly as typed, no
    image element was created from it, and the script in it did not run (the page's
    marker window.__xss stays unset). If the dashboard's list does not show an entry
    for this file, that is recorded and only the "did not run" checks apply there.
    """
    page = mdg_page
    def assert_not_live(where):
        page.wait_for_timeout(700)  # a script in an image tag would run a moment later
        assert page.evaluate("() => typeof window.__xss") == "undefined", \
            f"{where}: the script inside the column name ran"
        assert page.locator('img[src="x"]').count() == 0, \
            f"{where}: the column name was inserted as a live image element"
        assert page.locator("[onerror]").count() == 0, f"{where}: an element with onerror exists"

    s.open_home(page)
    s.upload_data_file(page, hostile_csv)
    assert_not_live("after upload")

    with page.expect_response(lambda r: r.url.endswith("/metadata"), timeout=s.SHORT_TIMEOUT_MS):
        page.click("#extractMetadataBtn")
    expect(page.locator("#metadataSection")).to_be_visible()
    s.wait_overlay_gone(page)
    assert_not_live("after Extract Metadata Only")
    summary_names = page.locator("#resultsContent li strong").all_text_contents()
    assert summary_names == ["item_id", HOSTILE_HEADER, "amount"]
    expect(page.locator("#resultsContent li strong").nth(1)).to_be_visible()

    s.set_rows(page, 12)
    s.generate_from_file(page)
    assert_not_live("after Generate")
    assert s.preview_headers(page) == ["item_id", HOSTILE_HEADER, "amount"]
    expect(page.locator("#previewHead th").nth(1)).to_be_visible()

    with page.expect_response(lambda r: "/api/cache-info" in r.url, timeout=s.SHORT_TIMEOUT_MS):
        page.goto("/dashboard")
    expect(page.locator("#cacheEntriesList")).to_be_visible()
    assert_not_live("on the dashboard")
    entries_text = page.locator("#cacheEntriesList").inner_text()
    entry_shown = HOSTILE_HEADER in entries_text
    print(f"\n[E2E_09] dashboard cache list shows the hostile column name literally: {entry_shown}")


def test_E2E_17_upload_notice_is_truthful(mdg_page):
    """The note beside "Upload Data File" says truthfully what happens to the file.

    Objective: the page tells the user the file is sent to the server and that real
    study data must not be uploaded; it does not claim the file stays in the browser.

    Precondition: the site is running. No AI call is made.

    Steps:
    1. Open the home page.
    2. Point at the small "i" beside "Upload Data File".
    3. Read the note that appears.

    Expected result: the note is shown and contains "Your file is sent to this server"
    and "Do not upload real study data". Neither the note nor the rest of the page
    says "never leaves your browser" or "Safe to upload".
    """
    page = mdg_page
    s.open_home(page)
    page.locator(".info-tooltip-upload .info-tooltip-icon").hover()
    tooltip = page.locator("#global-tooltip")
    expect(tooltip).to_be_visible()
    shown = tooltip.inner_text()
    source = page.locator(".info-tooltip-upload .info-tooltip-content").text_content()

    for text, where in ((shown, "the note shown on hover"), (source, "the note in the page")):
        flat = " ".join(text.split())
        assert "Your file is sent to this server" in flat, f"missing from {where}: {flat!r}"
        assert "Do not upload real study data" in flat, f"missing from {where}"

    whole_page = " ".join(page.content().split()).lower()
    assert "never leaves your browser" not in whole_page
    assert "safe to upload" not in whole_page


def test_E2E_18_unreadable_file_shows_plain_error(mdg_page, tmp_path):
    """A file that is not a table gives a readable error and no preview.

    Objective: when the uploaded file cannot be read as a table, the page says so in
    plain words, shows no preview, and does not show internal program error text.

    Precondition: the site is running. No AI call is expected.

    Steps:
    1. Open the home page.
    2. Upload a made-up ".csv" file that holds only meaningless bytes (not text).
    3. Click "Generate Synthetic Data" and read the error box. Close it.
    4. Upload an empty ".csv" file, click "Generate Synthetic Data", read the error box.

    Expected result: each time an error box appears with a sentence a person can
    read, and no preview of generated data is shown. The sentence does not contain
    internal program error text (for example the name of a text decoder or a byte code).
    """
    page = mdg_page
    binary = tmp_path / "e2e_not_a_table_made_up.csv"
    binary.write_bytes(bytes(range(256)) * 4)
    empty = tmp_path / "e2e_empty_made_up.csv"
    empty.write_bytes(b"")

    messages = {}
    s.open_home(page)
    for label, path in (("meaningless bytes", binary), ("empty file", empty)):
        page.set_input_files("#fileInput", str(path))
        expect(page.locator("#experimentalSection")).to_be_visible()
        s.click_generate(page)
        expect(page.locator("#errorModal")).to_be_visible(timeout=s.SHORT_TIMEOUT_MS)
        message = page.locator("#errorMessage").inner_text().strip()
        messages[label] = message
        assert len(message) >= 10, f"{label}: the error box is (nearly) empty: {message!r}"
        assert "[object" not in message and "undefined" not in message and not message.startswith("{"), \
            f"{label}: the error is not a readable sentence: {message!r}"
        expect(page.locator("#previewSection")).to_be_hidden()
        assert page.locator("#previewBody tr").count() == 0
        page.locator("#errorModal button", has_text="Close").click()
        expect(page.locator("#errorModal")).to_be_hidden()
        s.wait_overlay_gone(page)

    print(f"\n[E2E_18] error messages shown: {messages}")
    internal = re.compile(r"codec can't decode|Traceback|0x[0-9a-fA-F]{2}|Errno|Exception|\.py\b")
    raw = {label: m for label, m in messages.items() if internal.search(m)}
    assert not raw, f"the page shows internal program error text to the user: {raw}"
