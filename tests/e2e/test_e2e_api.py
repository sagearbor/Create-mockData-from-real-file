"""Tests of the site's HTTP routes through the real server: refusals, the JSON API,
health and readiness.

Run with MDG_BASE_URL set (see conftest.py). Only test_E2E_14 makes an AI call.
"""

import pytest

import mdg_e2e_support as s
from mdg_e2e_support import expect

pytestmark = pytest.mark.e2e

# Requirement ids (RS section 1.4) each test checks.
REQUIREMENTS = {
    "test_E2E_13_limits_and_refusals": ["MDG-REQ-022", "MDG-REQ-029", "MDG-REQ-036", "MDG-REQ-038"],
    "test_E2E_14_json_api_happy_path": ["MDG-REQ-026", "MDG-REQ-027", "MDG-REQ-028"],
    "test_E2E_16_health_and_readiness": ["MDG-REQ-042"],
}

SMALL_CSV = (
    "crate_id,crate_colour,weight_kg\n"
    "CR-01,teal,12.5\nCR-02,ochre,14.1\nCR-03,mauve,11.8\n"
    "CR-04,teal,13.3\nCR-05,ochre,12.9\nCR-06,mauve,15.0\n"
)
SMALL_CSV_COLUMNS = ["crate_id", "crate_colour", "weight_kg"]
UNLISTED_MODEL = "made-up-model-not-on-the-list"


def _upload(fields=None):
    """A multipart form holding the small made-up CSV file plus the given fields."""
    form = {"file": {"name": "e2e_crates_made_up.csv", "mimeType": "text/csv",
                     "buffer": SMALL_CSV.encode("utf-8")}}
    form.update(fields or {})
    return form


def _detail(response) -> str:
    body = response.json()
    return str(body.get("detail") or body.get("error") or "")


def _assert_v1_error(response, status, error_class=None):
    assert response.status == status, f"expected {status}, got {response.status}: {response.text()[:300]}"
    body = response.json()
    assert set(body) == {"status", "error", "error_class"}, f"error shape is {sorted(body)}"
    assert body["status"] == "error"
    assert isinstance(body["error"], str) and body["error"]
    assert isinstance(body["error_class"], str) and body["error_class"]
    if error_class:
        assert body["error_class"] == error_class, body
    return body


def test_E2E_13_limits_and_refusals(api, api_key):
    """Requests outside the limits are refused with a clear answer.

    Objective: the server refuses, before doing any work, a row count or file count
    outside the allowed range, an AI model that is not on its list, an unknown
    privacy mode, and batch generation; the JSON API refuses bad requests with its
    one error shape.

    Precondition: the site is running. No AI call is expected (every request is refused).

    Steps (each is one request with a small made-up file, sent without a browser):
    1. POST /generate and POST /generate-sse with num_rows = 0, then with 100001.
    2. POST /generate and POST /generate-sse with file_count = 21, then with 0.
    3. POST /generate and POST /generate-sse with a model name that is not on the
       server's list.
    4. POST /generate with safety_mode = "open".
    5. POST /generate/batch.
    6. POST /api/v1/generate with both csv_text and data_content.
    7. POST /api/v1/generate with a field the API does not know.
    8. POST /api/v1/generate with a model name that is not on the server's list.
    9. POST /api/v1/generate with num_rows = 0.

    Expected result:
    1. Status 400; the message says num_rows must be between 1 and 100000.
    2. Status 400; the message says file_count must be between 1 and 20.
    3. Status 400; the message says the model is not available and lists the allowed
       models (the same names GET /api/models returns).
    4. Status 400; the message names the three allowed modes.
    5. Status 501; the message says batch generation is not available.
    6, 7, 9. Status 422 with exactly the keys status ("error"), error and error_class.
    8. Status 400 with the same three keys; the message lists the allowed models.
    """
    allowed = [m["name"] for m in api.get("/api/models").json()["models"]]
    v1_headers = s.api_headers(api_key)

    for route in ("/generate", "/generate-sse"):
        for rows in ("0", "100001"):
            refused = api.post(route, multipart=_upload({"num_rows": rows}))
            assert refused.status == 400, f"{route} num_rows={rows}: {refused.status} {refused.text()[:200]}"
            assert "num_rows must be between 1 and 100000" in _detail(refused)

        for count in ("21", "0"):
            refused = api.post(route, multipart=_upload({"file_count": count}))
            assert refused.status == 400, f"{route} file_count={count}: {refused.status} {refused.text()[:200]}"
            assert "file_count must be between 1 and 20" in _detail(refused)

        refused = api.post(route, multipart=_upload({"model": UNLISTED_MODEL}))
        assert refused.status == 400, f"{route} model: {refused.status} {refused.text()[:200]}"
        message = _detail(refused)
        assert "not available" in message and "Allowed models" in message
        assert all(name in message for name in allowed), f"allowed models missing from: {message}"

    refused = api.post("/generate", multipart=_upload({"safety_mode": "open"}))
    assert refused.status == 400, f"safety_mode=open: {refused.status} {refused.text()[:200]}"
    assert all(mode in _detail(refused) for mode in ("strict", "balanced", "permissive"))

    batch = api.post("/generate/batch")
    assert batch.status == 501, f"/generate/batch: {batch.status} {batch.text()[:200]}"
    assert "not available" in _detail(batch)

    both = api.post("/api/v1/generate", headers=v1_headers,
                    data={"csv_text": SMALL_CSV, "data_content": "YSxiCjEsMgo="})
    body = _assert_v1_error(both, 422, "RequestValidationError")
    assert "exactly one of csv_text or data_content" in body["error"]

    unknown = api.post("/api/v1/generate", headers=v1_headers,
                       data={"csv_text": SMALL_CSV, "made_up_field": 1})
    body = _assert_v1_error(unknown, 422, "RequestValidationError")
    assert "made_up_field" in body["error"]

    wrong_model = api.post("/api/v1/generate", headers=v1_headers,
                           data={"csv_text": SMALL_CSV, "model": UNLISTED_MODEL})
    body = _assert_v1_error(wrong_model, 400, "ModelNotAllowed")
    assert all(name in body["error"] for name in allowed)

    zero_rows = api.post("/api/v1/generate", headers=v1_headers,
                         data={"csv_text": SMALL_CSV, "num_rows": 0})
    _assert_v1_error(zero_rows, 422, "RequestValidationError")


def test_E2E_14_json_api_happy_path(api, api_key):
    """The JSON API generates rows and reports its version.

    Objective: a program can send a small table as JSON to POST /api/v1/generate and
    get made-up rows back in the documented shape; GET /api/v1/version answers with
    the service name and versions.

    Precondition: the site is running and its AI model is set up. If the site needs
    an API key, MDG_API_KEY is set.

    Steps:
    1. POST /api/v1/generate with csv_text (a made-up table with columns crate_id,
       crate_colour, weight_kg and six rows) and num_rows = 8.
    2. GET /api/v1/version.
    3. GET /api/models.

    Expected result:
    1. Status 200. The answer has status "success"; shape is [8, 3]; columns are
       crate_id, crate_colour, weight_kg in that order; data is a list of 8 objects,
       each with exactly those columns; generation_info names the AI model, and that
       model is the server's default from step 3.
    2. Status 200 with a non-empty service, version and api_version; api_version is "v1".
    """
    headers = s.api_headers(api_key)
    response = api.post("/api/v1/generate", headers=headers,
                        data={"csv_text": SMALL_CSV, "num_rows": 8})
    assert response.status == 200, f"{response.status}: {response.text()[:400]}"
    body = response.json()
    assert set(body) >= {"status", "data", "shape", "columns", "generation_info"}
    assert body["status"] == "success"
    assert body["shape"] == [8, len(SMALL_CSV_COLUMNS)]
    assert body["columns"] == SMALL_CSV_COLUMNS
    assert isinstance(body["data"], list) and len(body["data"]) == 8
    assert all(isinstance(row, dict) and list(row) == SMALL_CSV_COLUMNS for row in body["data"])

    default_model = api.get("/api/models").json()["default"]
    used = body["generation_info"].get("model")
    assert isinstance(used, str) and used, f"generation_info has no model: {body['generation_info']}"
    assert used == default_model

    version = api.get("/api/v1/version", headers=headers)
    assert version.status == 200, version.text()[:300]
    info = version.json()
    assert set(info) == {"service", "version", "api_version"}
    assert all(isinstance(info[key], str) and info[key] for key in info)
    assert info["api_version"] == "v1"


def test_E2E_16_health_and_readiness(api, mdg_page):
    """The health, readiness, model-list and API-reference pages answer.

    Objective: the site reports that it is up, that its AI model is set up, which
    AI models it offers, and it serves the interactive API reference.

    Precondition: the site is running and its AI model is set up.

    Steps:
    1. GET /health.
    2. GET /ready.
    3. GET /api/models.
    4. Open /docs in the browser.
    5. GET /openapi.json.

    Expected result:
    1. Status 200 with status "healthy".
    2. Status 200 with status "ready" and ai_ready true.
    3. Status 200 with a default model that is in the list of models; every entry
       has a name.
    4. The page loads with status 200 and shows the API reference with the routes.
    5. Status 200; the description includes /api/v1/generate and /api/v1/version.
    """
    page = mdg_page
    health = api.get("/health")
    assert health.status == 200
    assert health.json()["status"] == "healthy"

    ready = api.get("/ready")
    assert ready.status == 200, f"/ready answered {ready.status}: {ready.text()[:300]}"
    assert ready.json()["status"] == "ready"
    assert ready.json()["ai_ready"] is True

    models = api.get("/api/models")
    assert models.status == 200
    catalog = models.json()
    names = [m.get("name") for m in catalog["models"]]
    assert names and all(isinstance(n, str) and n for n in names)
    assert catalog["default"] in names
    assert len(names) == len(set(names))

    docs = page.goto("/docs")
    assert docs.status == 200
    expect(page.locator("#swagger-ui")).to_be_attached()
    expect(page.locator("#swagger-ui .opblock").first).to_be_visible(timeout=s.SHORT_TIMEOUT_MS)

    openapi = api.get("/openapi.json")
    assert openapi.status == 200
    paths = openapi.json()["paths"]
    assert "/api/v1/generate" in paths and "/api/v1/version" in paths
