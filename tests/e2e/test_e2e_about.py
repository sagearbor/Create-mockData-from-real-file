"""Browser test of the About page's "Use it from code" section.

Run with MDG_BASE_URL set (see conftest.py). Makes one AI call (the copied example).
"""

import json
import re

import pytest

import mdg_e2e_support as s
from mdg_e2e_support import expect

pytestmark = pytest.mark.e2e

# Requirement ids (RS section 1.4) each test checks.
REQUIREMENTS = {
    "test_E2E_15_about_use_it_from_code": ["MDG-REQ-052", "MDG-REQ-053", "MDG-REQ-054", "MDG-REQ-055"],
}

REQUEST_FIELDS = ["csv_text", "data_content", "format", "num_rows", "match_threshold",
                  "safety_mode", "use_cache", "model"]


def test_E2E_15_about_use_it_from_code(make_page, api, api_key):
    """The About page's copy-and-paste examples are complete, correct and work.

    Objective: the "Use it from code" section is shown without clicking anything, its
    examples use this site's own address, each Copy button copies the example exactly,
    the request fields are listed, and the first example really works when sent.

    Precondition: the site is running and its AI model is set up. The browser is
    allowed to read the clipboard. If the site needs an API key, MDG_API_KEY is set.

    Steps:
    1. Open the About page.
    2. Without clicking anything, find the section "Use it from code" and its example
       blocks.
    3. Read the first example (curl, POST /api/v1/generate) and the address in it.
    4. For every example block, click its Copy button and read the clipboard.
    5. Read the table of request fields and the link to the interactive API reference.
    6. Take the JSON text after -d in the first example and send it, unchanged, to
       POST /api/v1/generate.

    Expected result: the section heading and every example are visible. There are
    curl, Python and JavaScript examples. Every block has a Copy button. No example
    still says "YOUR-SITE"; the first example's address is this site's own address
    followed by /api/v1/generate, and it sends the X-API-Key header from an
    environment variable (no real key in the page). After each Copy click the button
    says "Copied" and the clipboard holds exactly the block's text. The field table
    lists csv_text, data_content, format, num_rows, match_threshold, safety_mode,
    use_cache and model. There is a link to /docs. The request in step 6 answers 200
    with the number of rows and the columns the example asked for.
    """
    page = make_page(permissions=["clipboard-read", "clipboard-write"])
    response = page.goto("/about")
    assert response.status == 200
    origin = page.evaluate("() => window.location.origin")

    section = page.locator("#use-it-from-code")
    expect(section.locator("h2")).to_be_visible()
    expect(section.locator("h2")).to_contain_text("Use it from code")

    blocks = section.locator(".api-block")
    count = blocks.count()
    assert count >= 3, f"only {count} example blocks found"
    languages = blocks.evaluate_all("els => els.map(e => e.dataset.lang)")
    assert {"curl", "python", "javascript"} <= set(languages), f"languages offered: {languages}"

    for index in range(count):
        block = blocks.nth(index)
        label = block.get_attribute("data-block")
        expect(block.locator("pre code")).to_be_visible()
        button = block.locator(".copy-btn")
        expect(button).to_be_visible()
        expect(button).to_have_text("Copy")
        code_text = block.locator("pre code").evaluate("el => el.textContent")
        assert "YOUR-SITE" not in code_text, f"block {label} still holds the placeholder address"

        button.click()
        expect(button).to_have_text("Copied")
        copied = page.evaluate("() => navigator.clipboard.readText()")
        assert copied == code_text, f"block {label}: the clipboard does not hold the block's exact text"

    curl_text = section.locator('.api-block[data-block="curl-json"] pre code').evaluate(
        "el => el.textContent")
    assert f'"{origin}/api/v1/generate"' in curl_text, f"address in the curl example: {curl_text[:120]!r}"
    assert "X-API-Key: $MOCKDATA_API_KEY" in curl_text
    if api_key:
        assert api_key not in page.content(), "the page holds the real API key"

    fields = page.locator("#api-fields tbody tr").evaluate_all("rows => rows.map(r => r.dataset.field)")
    assert fields == REQUEST_FIELDS, f"request fields listed: {fields}"
    expect(page.locator("#api-fields tr[data-field='model']")).to_be_visible()
    expect(page.locator('#api-reference-links a[href="/docs"]')).to_be_visible()
    expect(page.locator("#api-limits")).to_contain_text("100,000")
    expect(section.locator('.api-block[data-block="error-shape"] pre code')).to_contain_text("error_class")

    match = re.search(r"-d '(.*)'\s*$", curl_text, flags=re.S)
    assert match, "could not find the JSON body (-d '...') in the curl example"
    request_body = json.loads(match.group(1))
    source_header = request_body["csv_text"].splitlines()[0].split(",")

    answer = api.post("/api/v1/generate", headers=s.api_headers(api_key), data=request_body)
    assert answer.status == 200, f"the example request answered {answer.status}: {answer.text()[:400]}"
    body = answer.json()
    assert body["status"] == "success"
    assert body["columns"] == source_header
    assert body["shape"] == [request_body["num_rows"], len(source_header)]
    assert len(body["data"]) == request_body["num_rows"]
