"""Browser tests of generating from a data dictionary (no data file).

Run with MDG_BASE_URL set (see conftest.py). The dictionaries are made up by the
fixtures. Tests that generate data make a real AI call.
"""

import pytest

import mdg_e2e_support as s
from mdg_e2e_support import (SECOND_DICTIONARY, SINGLE_DICTIONARY, TWO_TABLE_DICTIONARY, expect)

pytestmark = pytest.mark.e2e

# Requirement ids (RS section 1.4) each test checks.
REQUIREMENTS = {
    "test_E2E_10_dictionary_only_preview_and_download": ["MDG-REQ-008", "MDG-REQ-014"],
    "test_E2E_11_dictionary_with_several_tables": ["MDG-REQ-009"],
    "test_E2E_12_dictionary_private_to_each_session": ["MDG-REQ-019"],
}

GADGET_COLUMNS = list(SINGLE_DICTIONARY["columns"])
KITE_COLUMNS = list(SECOND_DICTIONARY["columns"])
BEEHIVE_COLUMNS = list(TWO_TABLE_DICTIONARY["$defs"]["Beehive"]["properties"])
NO_DICTIONARY_TEXT = "No data dictionary"


def test_E2E_10_dictionary_only_preview_and_download(mdg_page, dictionary_json, tmp_path):
    """Generate from a data dictionary alone, then download the same rows.

    Objective: with only a dictionary uploaded (no data file), the page generates
    data with exactly the dictionary's columns, and the download that follows holds
    the same rows the preview showed.

    Precondition: the site is running and its AI model is set up.

    Steps:
    1. Open the home page. Do not upload a data file.
    2. Upload the made-up dictionary (six columns: gadget_code, gadget_colour,
       length_mm, mass_g, checked_on, passed_check; gadget_colour allows teal, ochre,
       mauve; passed_check allows yes, no).
    3. Type 12 in the Rows box and click "Generate Synthetic Data".
    4. Read the preview: column headings, the sentence above the table, and every row.
    5. Click "Download File" and open the saved file.

    Expected result: the page says the dictionary was loaded with 6 columns. The
    preview has exactly the six dictionary columns in the dictionary's order and 12
    rows, all shown, with a DICTIONARY badge. The gadget_colour and passed_check
    values are only the allowed ones. The saved file's name ends in ".csv", has the
    same heading row, and its 12 rows equal the 12 preview rows, in the same order.
    """
    page = mdg_page
    s.open_home(page)
    uploaded = s.upload_dictionary(page, dictionary_json)
    assert uploaded["status"] == "success"
    assert "6 columns defined" in page.locator("#dictionaryStats").inner_text()
    expect(page.locator("#dictionaryDetails")).to_be_visible()

    s.set_rows(page, 12)
    result = s.generate_from_dictionary(page)

    headers = s.preview_headers(page)
    assert headers == GADGET_COLUMNS, f"preview columns {headers}, dictionary columns {GADGET_COLUMNS}"
    sentence = s.preview_sentence(page)
    assert s.stated_row_count(sentence) == 12
    assert "all 12 rows are shown below" in sentence
    shown_rows = s.preview_rows(page)
    assert len(shown_rows) == 12
    assert "DICTIONARY" in s.badges_text(page)
    assert result["column_names"] == GADGET_COLUMNS

    colour_at, passed_at = headers.index("gadget_colour"), headers.index("passed_check")
    assert {row[colour_at] for row in shown_rows} <= {"teal", "ochre", "mauve"}
    assert {row[passed_at] for row in shown_rows} <= {"yes", "no"}

    path, name = s.download_via(page, "#downloadFileBtn", tmp_path / "downloads")
    assert not s.error_text(page), f"download showed an error: {s.error_text(page)}"
    assert name.endswith(".csv"), f"downloaded file is named {name!r}"
    file_rows = s.read_csv_rows(path.read_bytes())
    assert file_rows[0] == GADGET_COLUMNS
    assert len(file_rows) - 1 == 12

    shown_normal = [s.normalise_row(row) for row in shown_rows]
    file_normal = [s.normalise_row(row) for row in file_rows[1:]]
    differing = [i + 1 for i, (a, b) in enumerate(zip(shown_normal, file_normal)) if a != b]
    assert not differing, (
        f"download rows differ from the preview at row(s) {differing}; "
        f"first difference: preview {shown_normal[differing[0] - 1]} / file {file_normal[differing[0] - 1]}")


def test_E2E_11_dictionary_with_several_tables(mdg_page, two_table_dictionary_json):
    """A dictionary that defines two tables: the page asks which one to use.

    Objective: when the dictionary file defines more than one table, the page asks
    the user to choose one before it generates, and then generates for that table.

    Precondition: the site is running and its AI model is set up.

    Steps:
    1. Open the home page. Upload the made-up dictionary that defines two tables,
       Orchard and Beehive.
    2. Without choosing a table, click "Generate Synthetic Data". Read the message
       and close it.
    3. In "This file defines several tables. Choose one:" pick Beehive.
    4. Type 10 in the Rows box and click "Generate Synthetic Data".

    Expected result: after the upload the page says 2 tables were found and none is
    chosen, and the list offers Orchard and Beehive. Clicking Generate before choosing
    gives a message asking to choose a table, and no data. After Beehive is picked the
    page names it as the loaded table, and the preview has exactly the Beehive columns
    (hive_code, frame_count, queen_marked, honey_kg, inspected_on) and 10 rows.
    """
    page = mdg_page
    s.open_home(page)
    uploaded = s.upload_dictionary(page, two_table_dictionary_json)
    assert uploaded["status"] == "choose_table"
    assert sorted(uploaded["tables"]) == ["Beehive", "Orchard"]

    expect(page.locator("#dictionaryTableChooser")).to_be_visible()
    assert "2 tables found; none chosen yet" in page.locator("#dictionaryStats").inner_text()
    offered = [v for v in s.select_values(page, "#dictionaryTableSelect") if v]
    assert sorted(offered) == ["Beehive", "Orchard"]

    s.click_generate(page)
    expect(page.locator("#errorModal")).to_be_visible()
    asked = page.locator("#errorMessage").inner_text()
    assert "2 tables" in asked and "Choose one" in asked, f"unexpected message: {asked!r}"
    expect(page.locator("#previewSection")).to_be_hidden()
    page.locator("#errorModal button", has_text="Close").click()

    with page.expect_response(lambda r: r.url.endswith("/dictionary/table"),
                              timeout=s.SHORT_TIMEOUT_MS) as info:
        page.select_option("#dictionaryTableSelect", "Beehive")
    assert info.value.status == 200, info.value.text()[:300]
    expect(page.locator("#dictionaryFileName")).to_contain_text("(table Beehive)")
    s.wait_overlay_gone(page)

    s.set_rows(page, 10)
    result = s.generate_from_dictionary(page)
    assert s.preview_headers(page) == BEEHIVE_COLUMNS
    assert result["column_names"] == BEEHIVE_COLUMNS
    assert s.stated_row_count(s.preview_sentence(page)) == 10
    assert len(s.preview_rows(page)) == 10


def test_E2E_12_dictionary_private_to_each_session(make_page, api, dictionary_json,
                                                   second_dictionary_json):
    """Two people's dictionaries do not mix, and a dictionary cannot be used without its id.

    Objective: a dictionary uploaded in one browser session is used only by that
    session; a request that does not carry the id the server gave for an upload is
    told that no dictionary has been uploaded.

    Precondition: the site is running and its AI model is set up.

    Steps:
    1. Open the home page in two separate browser sessions, A and B (no shared
       cookies or storage).
    2. In A upload the "gadgets" dictionary. In B upload the "kites" dictionary
       (different column names).
    3. In A type 8 in the Rows box and click "Generate Synthetic Data". Then do the
       same in B.
    4. Without a browser, send POST /dictionary/table with a table name and no
       dictionary id; send it again with an id that was never issued.
    5. Without a browser, send POST /generate-with-dictionary with no dictionary id
       and no dictionary file.

    Expected result: A and B received different ids. A's preview has only the gadget
    columns; B's preview has only the kite columns. Each request in steps 4 and 5 is
    refused with status 400 and a message that no data dictionary has been uploaded
    or provided; none of them returns data.
    """
    page_a, page_b = make_page(), make_page()
    s.open_home(page_a)
    s.open_home(page_b)
    upload_a = s.upload_dictionary(page_a, dictionary_json)
    upload_b = s.upload_dictionary(page_b, second_dictionary_json)
    assert upload_a["dictionary_id"] and upload_b["dictionary_id"]
    assert upload_a["dictionary_id"] != upload_b["dictionary_id"]

    s.set_rows(page_a, 8)
    s.generate_from_dictionary(page_a)
    s.set_rows(page_b, 8)
    s.generate_from_dictionary(page_b)

    assert s.preview_headers(page_a) == GADGET_COLUMNS
    assert s.preview_headers(page_b) == KITE_COLUMNS
    assert len(s.preview_rows(page_a)) == 8 and len(s.preview_rows(page_b)) == 8

    without_id = api.post("/dictionary/table", multipart={"table": "Beehive"})
    assert without_id.status == 400, without_id.text()[:300]
    body = without_id.json()
    assert NO_DICTIONARY_TEXT in (body.get("error") or body.get("detail") or ""), body
    assert "dictionary" not in body or not body["dictionary"]

    unknown_id = api.post("/dictionary/table",
                          multipart={"table": "Beehive", "dictionary_id": "made-up-id-never-issued"})
    assert unknown_id.status == 400, unknown_id.text()[:300]
    assert NO_DICTIONARY_TEXT in (unknown_id.json().get("error") or "")

    generate = api.post("/generate-with-dictionary",
                        multipart={"num_rows": "5", "preview_only": "true"})
    assert generate.status == 400, generate.text()[:300]
    generate_body = generate.json()
    assert NO_DICTIONARY_TEXT in (generate_body.get("detail") or generate_body.get("error") or "")
    assert "preview" not in generate_body
