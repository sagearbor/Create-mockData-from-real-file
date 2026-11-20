"""JSON API for other programs: ``/api/v1``.

* ``POST /api/v1/generate`` - send a small dataset as JSON (CSV text or base64
  file bytes), get synthetic rows back as typed JSON.
* ``GET /api/v1/version`` - service and API version.

Everything under ``/api/v1`` (and only there) gets:

* an optional API key: header ``X-API-Key`` must equal env ``MOCKDATA_API_KEY``;
  when the variable is unset or empty the check is off;
* a request size limit: env ``MOCKDATA_API_MAX_BYTES`` (default 10 MB);
* ONE error shape: ``{"status": "error", "error": "...", "error_class": "..."}``.

The older routes in ``main.py`` are not touched by any of this.
"""

import base64
import binascii
import hmac
import json
import os
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, FastAPI, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core import generation_service
from src.core.models import ModelNotAllowed, resolve_model
from src.core.synthetic_generator import AIGenerationError
from src.utils.config import APP_VERSION
from src.utils.logger import logger

PREFIX = "/api/v1"
API_KEY_ENV = "MOCKDATA_API_KEY"
API_KEY_HEADER = "X-API-Key"
MAX_BYTES_ENV = "MOCKDATA_API_MAX_BYTES"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB

# "format" -> file extension the DataLoader understands
_EXTENSIONS = {"csv": "csv", "tsv": "tsv", "json": "json", "excel": "xlsx", "parquet": "parquet"}


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #

class GenerateRequest(BaseModel):
    """Source data plus options. Send exactly one of ``csv_text`` / ``data_content``."""

    model_config = ConfigDict(extra="forbid")

    csv_text: Optional[str] = Field(
        default=None, description="The source data as plain CSV text (header row first).")
    data_content: Optional[str] = Field(
        default=None, description="The source file's bytes, base64-encoded. Use with `format`.")
    format: Literal["csv", "tsv", "json", "excel", "parquet"] = Field(
        default="csv", description="Format of `data_content` (ignored for `csv_text`).")
    num_rows: Optional[int] = Field(
        default=None, ge=1, le=100_000,
        description="Rows to generate. Omit to match the source row count.")
    match_threshold: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Statistical matching threshold, 0-1.")
    safety_mode: Literal["strict", "balanced", "permissive"] = Field(
        default="balanced", description="Privacy level for categorical values.")
    use_cache: bool = Field(
        default=True, description="Reuse a cached generation script for similar data.")
    # A plain string on purpose: the allow-list is server configuration, checked in
    # the route so a refused name gets the 400 ModelNotAllowed error, not a 422.
    model: Optional[str] = Field(
        default=None,
        description="AI model (deployment name) that writes the generation code. Must be "
                    "one of the names from GET /api/models. Omit for the server default.")

    @model_validator(mode="after")
    def _exactly_one_source(self):
        if bool(self.csv_text) == bool(self.data_content):
            raise ValueError("provide exactly one of csv_text or data_content")
        if self.data_content:
            try:
                base64.b64decode(self.data_content, validate=True)
            except (binascii.Error, ValueError):
                raise ValueError("data_content is not valid base64") from None
        return self


class GenerateResponse(BaseModel):
    status: Literal["success"] = "success"
    data: List[Dict[str, Any]] = Field(description="Synthetic rows, one object per row.")
    shape: List[int] = Field(description="[rows, columns]")
    columns: List[str] = Field(description="Column names, in order.")
    generation_info: Dict[str, Any] = Field(description="How the data was made (method, timings).")


class VersionResponse(BaseModel):
    service: str
    version: str
    api_version: str


class ErrorResponse(BaseModel):
    """The one error shape used by every /api/v1 failure."""

    status: Literal["error"] = "error"
    error: str
    error_class: str


def _error(status_code: int, message: str, error_class: str,
           headers: Optional[Dict[str, str]] = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, headers=headers,
        content={"status": "error", "error": message, "error_class": error_class})


def _is_v1(path: str) -> bool:
    return path == PREFIX or path.startswith(PREFIX + "/")


def max_request_bytes() -> int:
    """Request size limit for /api/v1, read per request so it can be changed by env."""
    try:
        value = int(os.environ.get(MAX_BYTES_ENV, ""))
    except ValueError:
        return DEFAULT_MAX_BYTES
    return value if value > 0 else DEFAULT_MAX_BYTES


# --------------------------------------------------------------------------- #
# Guard: API key + size limit, for /api/v1 paths only
# --------------------------------------------------------------------------- #

class ApiV1Guard:
    """Pure ASGI middleware; passes every non-/api/v1 request through untouched."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not _is_v1(scope["path"]) or scope["method"] == "OPTIONS":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])

        expected = os.environ.get(API_KEY_ENV, "")
        if expected:
            supplied = headers.get(API_KEY_HEADER.lower().encode(), b"")
            if not hmac.compare_digest(supplied, expected.encode()):
                await _error(401, f"Missing or invalid API key (header {API_KEY_HEADER}).",
                             "InvalidApiKey")(scope, receive, send)
                return

        limit = max_request_bytes()
        too_large = _error(413, f"Request body is larger than the {limit}-byte limit.",
                           "RequestTooLarge")
        declared = headers.get(b"content-length", b"")
        if declared.isdigit() and int(declared) > limit:
            await too_large(scope, receive, send)
            return

        if scope["method"] in ("POST", "PUT", "PATCH"):
            # Read the body here, counting bytes, so a missing or wrong
            # Content-Length cannot get past the limit; then replay it.
            chunks, total, more = [], 0, True
            while more:
                message = await receive()
                if message["type"] != "http.request":
                    return  # client went away
                chunk = message.get("body", b"")
                total += len(chunk)
                if total > limit:
                    await too_large(scope, receive, send)
                    return
                chunks.append(chunk)
                more = message.get("more_body", False)
            body, replayed = b"".join(chunks), False

            async def replay():
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            await self.app(scope, replay, send)
            return

        await self.app(scope, receive, send)


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #

_ERROR_RESPONSES = {
    code: {"model": ErrorResponse, "description": text}
    for code, text in {
        400: "The source data could not be read or used, or the model is not allowed",
        401: "Missing or invalid API key",
        413: "Request body too large",
        422: "Request validation failed",
        502: "AI generation failed; no data was generated",
        503: "AI is not configured; no data was generated",
    }.items()
}

router = APIRouter(prefix=PREFIX, tags=["api-v1"])


@router.get("/version", response_model=VersionResponse,
            responses={401: _ERROR_RESPONSES[401]})
def version():
    """Service version and API version."""
    return VersionResponse(service="BYOD Synthetic Data Generator",
                           version=APP_VERSION, api_version="v1")


@router.post("/generate", response_model=GenerateResponse, responses=_ERROR_RESPONSES)
def generate_json(req: GenerateRequest):
    """Generate synthetic rows from a dataset sent as JSON.

    Plain ``def`` on purpose: FastAPI runs it in the threadpool, so the slow,
    synchronous LLM call never blocks the event loop (or /health).
    """
    # Before anything is decoded or any model is called.
    try:
        model = resolve_model(req.model)
    except ModelNotAllowed as exc:
        return _error(400, str(exc), "ModelNotAllowed")

    if req.csv_text:
        data_content = base64.b64encode(req.csv_text.encode("utf-8")).decode("ascii")
        file_name = "input.csv"
    else:
        data_content = req.data_content
        file_name = f"input.{_EXTENSIONS[req.format]}"

    try:
        result = generation_service.generate({
            "data_content": data_content,
            "file_name": file_name,
            "num_rows": req.num_rows,
            "match_threshold": req.match_threshold,
            "output_format": "json",
            "safety_mode": req.safety_mode,
            "use_cache": req.use_cache,
            "model": model,
        }, raise_ai_errors=True)

        if result.get("status") != "success":
            return _error(400, str(result.get("error") or "generation failed"), "GenerationError")

        return GenerateResponse(
            data=result["data"],
            shape=result["shape"],
            columns=result["columns"],
            # generation_info can hold numpy numbers; make it plain JSON
            generation_info=json.loads(json.dumps(result.get("generation_info") or {}, default=str)),
        )
    except AIGenerationError:
        raise  # main.py's handler answers with the same error shape (502/503)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"/api/v1/generate failed: {type(exc).__name__}", exc_info=True)
        return _error(500, "Internal error. No data was generated.", "InternalError")


# --------------------------------------------------------------------------- #
# Uniform errors for /api/v1; every other path keeps FastAPI's defaults
# --------------------------------------------------------------------------- #

async def _validation_error(request: Request, exc: RequestValidationError):
    if not _is_v1(request.url.path):
        return await request_validation_exception_handler(request, exc)
    problems = "; ".join(
        f"{'.'.join(str(part) for part in err.get('loc', ()))}: {err.get('msg', 'invalid')}"
        for err in exc.errors())
    return _error(422, f"Invalid request: {problems}", "RequestValidationError")


async def _http_error(request: Request, exc: StarletteHTTPException):
    if not _is_v1(request.url.path):
        return await http_exception_handler(request, exc)
    return _error(exc.status_code, str(exc.detail), "HTTPException",
                  headers=getattr(exc, "headers", None))


def install(app: FastAPI) -> None:
    """Mount the /api/v1 routes and their error handlers on ``app``."""
    app.include_router(router)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
