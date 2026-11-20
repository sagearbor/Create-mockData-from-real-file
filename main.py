"""Main FastAPI application for BYOD Synthetic Data Generator."""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import json
import re
import io
import time
import secrets
import threading

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import pandas as pd
import uvicorn
import zipfile
from datetime import datetime

from src.core.data_loader import DataLoader
from src.core.metadata_extractor import MetadataExtractor
from src.core.synthetic_generator import SyntheticDataGenerator, AIGenerationError, CodeExecutionError
from src.core.cache_manager import CacheManager, cache_variant
from src.core.models import ModelNotAllowed, model_catalog, resolve_model
from src.core.data_dictionary import (
    DataDictionary,
    DictionaryError,
    DictionaryTooLarge,
    NoDictionaryLoaded,
    max_dictionary_bytes,
)
from src.utils.config import settings, APP_VERSION
from src.api import v1 as api_v1
from src.utils.logger import logger

# Initialize components
data_loader = DataLoader()
# A second object on the generator's cache folder, with its own index copy read at
# start-up: it never writes that copy back (persist_removals=False).
cache_manager = CacheManager()
# Used only for its stateless helpers (parsing, validation, prompt budget). Routes never
# store an upload on it: one object is shared by every user of the process.
data_dictionary = DataDictionary()
# Rows of recent dictionary-only previews, so the download that follows sends the same rows.
# Keyed by an unguessable id handed only to the browser that made the preview; a few
# entries, each dropped after 30 minutes.
_dictionary_previews: Dict[str, Dict[str, Any]] = {}
# Rows shown in the on-page preview. Small files are shown whole, so the table
# matches the row count beside it; bigger ones show the first PREVIEW_ROWS.
PREVIEW_ROWS = 50
_PREVIEW_KEEP_SECONDS = 1800
_PREVIEW_KEEP_COUNT = 20


def _remember_preview(df, info, num_rows, model=None) -> str:
    now = time.time()
    for key in [k for k, v in _dictionary_previews.items() if now - v["at"] > _PREVIEW_KEEP_SECONDS]:
        _dictionary_previews.pop(key, None)
    while len(_dictionary_previews) >= _PREVIEW_KEEP_COUNT:
        _dictionary_previews.pop(min(_dictionary_previews, key=lambda k: _dictionary_previews[k]["at"]), None)
    preview_id = secrets.token_urlsafe(24)
    _dictionary_previews[preview_id] = {"df": df, "info": info, "num_rows": num_rows,
                                        "model": model, "at": now}
    return preview_id


def _recall_preview(preview_id, num_rows, model=None):
    """The remembered preview, unless it is unknown, expired, or was made for another
    row count or another model than this request asks for."""
    entry = _dictionary_previews.get(preview_id or "")
    if not entry or time.time() - entry["at"] > _PREVIEW_KEEP_SECONDS or entry["num_rows"] != num_rows:
        return None
    if entry.get("model") != model:
        return None
    return entry

# Uploaded dictionaries, one entry per upload, keyed by an unguessable id returned only to
# the client that uploaded it. A request can reach a dictionary only by sending its id, so
# one user's upload is never read or used by another. A parsed catalog can be large, so at
# most _DICTIONARY_KEEP_COUNT are kept (least recently used dropped first); an entry
# expires 30 minutes after its last use.
_dictionary_uploads: Dict[str, Dict[str, Any]] = {}
_dictionary_uploads_lock = threading.Lock()
_DICTIONARY_KEEP_SECONDS = _PREVIEW_KEEP_SECONDS
_DICTIONARY_KEEP_COUNT = 10


def _remember_dictionary(catalog, dictionary) -> str:
    now = time.time()
    with _dictionary_uploads_lock:
        for key in [k for k, v in _dictionary_uploads.items() if now - v["at"] > _DICTIONARY_KEEP_SECONDS]:
            _dictionary_uploads.pop(key, None)
        while len(_dictionary_uploads) >= _DICTIONARY_KEEP_COUNT:
            _dictionary_uploads.pop(min(_dictionary_uploads, key=lambda k: _dictionary_uploads[k]["at"]), None)
        dictionary_id = secrets.token_urlsafe(24)
        _dictionary_uploads[dictionary_id] = {"catalog": catalog, "dictionary": dictionary, "at": now}
    return dictionary_id


def _recall_dictionary(dictionary_id):
    """The upload with this id, or None if absent, unknown or expired. A successful
    recall restarts the 30 minutes, so a dictionary does not expire while in use."""
    if not dictionary_id or not isinstance(dictionary_id, str):
        return None
    now = time.time()
    with _dictionary_uploads_lock:
        entry = _dictionary_uploads.get(dictionary_id)
        if not entry:
            return None
        if now - entry["at"] > _DICTIONARY_KEEP_SECONDS:
            _dictionary_uploads.pop(dictionary_id, None)
            return None
        entry["at"] = now
        return entry


# Limits for the form routes (/generate, /generate-sse, /generate-with-dictionary).
MIN_NUM_ROWS, MAX_NUM_ROWS = 1, 100_000
MIN_FILE_COUNT, MAX_FILE_COUNT = 1, 20
# Client-supplied metadata (metadata_json). 1 MB is also the most the form parser
# accepts for a text field (Starlette's max_part_size), so a larger cap would never apply.
MAX_METADATA_JSON_BYTES = 1024 * 1024
MAX_METADATA_COLUMNS = 2000
MAX_COLUMN_NAME_CHARS = 200
# Request body limit for every route outside /api/v1 (which has its own, see ApiV1Guard).
MAX_UPLOAD_BYTES_ENV = "MOCKDATA_MAX_UPLOAD_BYTES"
DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
BATCH_NOT_AVAILABLE = "Batch generation is not available in this release."


def _check_generation_limits(num_rows: Optional[int], file_count: Optional[int]) -> None:
    """400 when num_rows or file_count is outside the allowed range (None = not given)."""
    if num_rows is not None and not MIN_NUM_ROWS <= num_rows <= MAX_NUM_ROWS:
        raise HTTPException(status_code=400, detail=(
            f"num_rows must be between {MIN_NUM_ROWS} and {MAX_NUM_ROWS} (got {num_rows})."))
    if file_count is not None and not MIN_FILE_COUNT <= file_count <= MAX_FILE_COUNT:
        raise HTTPException(status_code=400, detail=(
            f"file_count must be between {MIN_FILE_COUNT} and {MAX_FILE_COUNT} (got {file_count})."))


PRIVACY_MODES = ("strict", "balanced", "permissive")

_UNREADABLE_FILE = "The file could not be read as a table. Check that it is a CSV, TSV, JSON or Excel file."


def _public_error(exc: Exception) -> str:
    """What a caller is told when a request fails unexpectedly.

    Python and pandas put offending values in quotes, so a message is passed on only
    when it quotes nothing; otherwise the caller gets a plain sentence and the error's
    type. Raw internal text and cell values never reach the page."""
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    if isinstance(exc, (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError)):
        return _UNREADABLE_FILE
    message = str(exc).strip()
    if message and len(message) <= 200 and not re.search(r"[\'\"`]", message):
        return message
    return f"The request could not be processed ({type(exc).__name__})."


def _rows_for_request(num_rows: Optional[int], metadata: Dict[str, Any]) -> None:
    """With no row count given, the uploaded file's own count is used: it must be in range too."""
    if num_rows is None:
        try:
            file_rows = int(metadata["structure"]["shape"]["rows"])
        except (KeyError, TypeError, ValueError):
            return
        if file_rows > MAX_NUM_ROWS:
            raise HTTPException(status_code=400, detail=(
                f"The file has {file_rows} rows. Set Rows to a number up to {MAX_NUM_ROWS}."))


def _privacy_mode_or_400(safety_mode: Optional[str]) -> str:
    """The privacy mode for this request, lower-cased; 400 for anything but the three modes."""
    mode = (safety_mode or "balanced").strip().lower()
    if mode not in PRIVACY_MODES:
        raise HTTPException(status_code=400, detail=(
            f"safety_mode must be one of {', '.join(PRIVACY_MODES)} (got {safety_mode!r})."))
    return mode


def _resolve_model_or_400(model: Optional[str]) -> str:
    """The model for this request (empty/absent = server default); 400 naming the
    allowed models for any other name. Called before any generation or model call."""
    try:
        return resolve_model(model)
    except ModelNotAllowed as e:
        raise HTTPException(status_code=400, detail=str(e))


def _find_cached(metadata: Dict[str, Any], match_threshold: float, num_rows: Optional[int], model: str):
    """This module's cache lookup: only a script written by the same model, from a
    description in the same privacy mode, for the same row count (see cache_variant)."""
    return cache_manager.find_similar_cached(
        metadata, match_threshold,
        num_rows=num_rows or metadata["structure"]["shape"]["rows"],
        variant=cache_variant(metadata, model))


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validated_client_metadata(raw: str) -> Dict[str, Any]:
    """Parse and check a client-supplied ``metadata_json``; 400 if it is not usable.

    The result is rebuilt from known keys only: ``generation_constraints`` (text that
    would go into the AI prompt as instructions) and every other unknown top-level or
    column key is dropped. That includes ``privacy_mode``: a client cannot claim one, so
    its metadata gets the fixed "client" cache variant and never shares cached scripts
    with descriptions this server extracted.
    """
    def bad(reason: str) -> HTTPException:
        return HTTPException(status_code=400, detail=f"Invalid metadata_json: {reason}")

    if len(raw.encode("utf-8", errors="replace")) > MAX_METADATA_JSON_BYTES:
        raise bad(f"larger than the {MAX_METADATA_JSON_BYTES}-byte limit.")
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError):
        raise bad("not valid JSON.")
    if not isinstance(data, dict):
        raise bad("expected a JSON object.")

    structure = data.get("structure")
    if not isinstance(structure, dict):
        raise bad("'structure' must be an object.")
    columns = structure.get("columns")
    if not isinstance(columns, list) or not columns:
        raise bad("'structure.columns' must be a non-empty list.")
    if len(columns) > MAX_METADATA_COLUMNS:
        raise bad(f"more than {MAX_METADATA_COLUMNS} columns.")
    clean_columns = []
    for col in columns:
        if not isinstance(col, dict):
            raise bad("each entry of 'structure.columns' must be an object.")
        name, dtype = col.get("name"), col.get("dtype")
        if not isinstance(name, str) or not name or len(name) > MAX_COLUMN_NAME_CHARS:
            raise bad(f"each column needs a 'name' of 1 to {MAX_COLUMN_NAME_CHARS} characters.")
        if not isinstance(dtype, str) or not dtype or len(dtype) > MAX_COLUMN_NAME_CHARS:
            raise bad(f"each column needs a 'dtype' of 1 to {MAX_COLUMN_NAME_CHARS} characters.")
        clean = {"name": name, "dtype": dtype}
        python_type = col.get("python_type")
        if python_type is not None:
            if not isinstance(python_type, str) or len(python_type) > MAX_COLUMN_NAME_CHARS:
                raise bad(f"'python_type' must be text of at most {MAX_COLUMN_NAME_CHARS} characters.")
            clean["python_type"] = python_type
        if isinstance(col.get("nullable"), bool):
            clean["nullable"] = col["nullable"]
        for key in ("unique_count", "null_count"):
            if _is_int(col.get(key)) and col[key] >= 0:
                clean[key] = col[key]
        clean_columns.append(clean)

    shape = structure.get("shape")
    if not isinstance(shape, dict):
        raise bad("'structure.shape' must be an object.")
    rows, column_count = shape.get("rows"), shape.get("columns")
    if not _is_int(rows) or not MIN_NUM_ROWS <= rows <= MAX_NUM_ROWS:
        raise bad(f"'structure.shape.rows' must be a whole number between {MIN_NUM_ROWS} and {MAX_NUM_ROWS}.")
    if not _is_int(column_count) or not 1 <= column_count <= MAX_METADATA_COLUMNS:
        raise bad(f"'structure.shape.columns' must be a whole number between 1 and {MAX_METADATA_COLUMNS}.")

    statistics = data.get("statistics")
    if not isinstance(statistics, dict) or not all(isinstance(v, dict) for v in statistics.values()):
        raise bad("'statistics' must be an object of per-column objects.")

    metadata = {
        "structure": {"shape": {"rows": rows, "columns": column_count}, "columns": clean_columns},
        "statistics": statistics,
    }
    for key in ("patterns", "correlations"):
        if key in data and data[key] is not None:
            if not isinstance(data[key], dict):
                raise bad(f"'{key}' must be an object.")
            metadata[key] = data[key]
    return metadata


def max_upload_bytes() -> int:
    """Request body limit outside /api/v1, read per request so env changes apply."""
    try:
        value = int(os.environ.get(MAX_UPLOAD_BYTES_ENV, ""))
    except ValueError:
        return DEFAULT_MAX_UPLOAD_BYTES
    return value if value > 0 else DEFAULT_MAX_UPLOAD_BYTES


class RequestBodyLimit:
    """Pure ASGI middleware: 413 for a request body over the limit, on every route
    that ApiV1Guard does not cover.

    Refuses on Content-Length when present; otherwise counts the bytes as the app
    reads them (nothing is buffered here) and stops the read at the limit. Requests
    without a body (health probes) and all responses, streamed ones included, pass
    through untouched.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS")
                or api_v1._is_v1(scope["path"])):
            await self.app(scope, receive, send)
            return

        limit = max_upload_bytes()
        too_large = JSONResponse(status_code=413, content={
            "status": "error",
            "error": f"Request body is larger than the {limit}-byte limit ({MAX_UPLOAD_BYTES_ENV}).",
            "error_class": "RequestTooLarge"})
        declared = dict(scope.get("headers") or []).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > limit:
            await too_large(scope, receive, send)
            return

        total, over, started = 0, False, False

        async def counting_receive():
            nonlocal total, over
            if over:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > limit:
                    over = True
                    # End the app's read here; whatever it answers is replaced by the 413.
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message):
            nonlocal started
            if over and not started:
                return  # dropped: the 413 is sent below instead
            started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except Exception:
            if not (over and not started):
                raise
        if over and not started:
            await too_large(scope, receive, send)


# Initialize synthetic generator (OpenAI client will be added when API key is provided)
synthetic_generator = None


def _run_cached_code(cached_result, num_rows=None):
    """Run a cached script. Returns None when it cannot serve this request, so the
    caller generates fresh code instead: the script no longer runs (the entry is
    dropped), or it writes a different number of rows than asked for (entry kept)."""
    if not (cached_result and "generation_code" in cached_result):
        return None
    try:
        df = synthetic_generator._execute_generation_code(cached_result["generation_code"])
        if num_rows is not None and len(df) != num_rows:
            logger.info("Cached generation script makes a different number of rows; generating new code")
            return None
        return df
    except CodeExecutionError:
        logger.warning("Cached generation script failed to run; generating new code instead")
        synthetic_generator.forget_cached(cached_result)
        # This module's own index copy: forget it in memory only (the generator's is saved).
        cache_manager.remove_entry(cached_result.get("cache_file") or "", save=False)
        return None

def initialize_openai_client():
    """Build the generator with an Azure OpenAI client when AI is configured.

    Auth and telemetry live in src/dcri_llm.py (managed identity by default,
    LLM_AUTH=key only as an opt-in). With no endpoint, or if the client cannot
    be built, there is NO fallback: /ready answers 503 and generation requests
    fail with a clear error.
    """
    global synthetic_generator
    from src.core.llm_client import build_llm_client

    logger.info(f"Chat deployment: {settings.azure_openai_chat_deployment}")
    client = build_llm_client()
    synthetic_generator = SyntheticDataGenerator(openai_client=client)
    # One cache object for the routes, the dashboard and the generator: two objects each
    # kept their own copy of the index, so the dashboard and "Cache Hit" lagged behind.
    synthetic_generator.cache_manager = cache_manager
    return client is not None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan."""
    # Startup
    logger.info("Starting BYOD Synthetic Data Generator")
    initialize_openai_client()

    # Register the A2A agent into the default registry so the /a2a/* routes
    # can dispatch to it without re-importing generation_service at module load.
    from src.a2a_agent import register as _register_a2a_agent
    _register_a2a_agent()
    logger.info("A2A agent registered.")

    # Ensure directories exist
    settings.ensure_local_directories()

    # Mount static files directory if it exists
    static_dir = Path(__file__).parent / "src" / "web" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    yield

    # Shutdown
    logger.info("Shutting down BYOD Synthetic Data Generator")

# Initialize FastAPI app with lifespan
app = FastAPI(
    title="BYOD Synthetic Data Generator",
    description="Generate made-up data with the same structure and similar statistics as an uploaded file",
    version=APP_VERSION,
    lifespan=lifespan
)

# Add CORS middleware with secure configuration
# Per-request action_id + Easy Auth user for LLM telemetry (dcri_llm).
from src.dcri_llm import asgi_middleware as _dcri_llm_middleware
app.add_middleware(_dcri_llm_middleware)

# /api/v1 only: optional X-API-Key check and request size limit. Added before
# CORS so CORS stays outermost and 401/413 answers still carry CORS headers.
app.add_middleware(api_v1.ApiV1Guard)
# Every other route: one request body size limit (MOCKDATA_MAX_UPLOAD_BYTES).
app.add_middleware(RequestBodyLimit)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins(),  # Environment-specific origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],  # Only methods needed (GET for reading, POST for file uploads/generation, OPTIONS for preflight)
    allow_headers=["*"],
    max_age=3600,  # Cache preflight requests for 1 hour
)


@app.exception_handler(AIGenerationError)
async def ai_generation_error_handler(request: Request, exc: AIGenerationError):
    """AI failed: tell the user plainly; no template data is ever substituted."""
    return JSONResponse(
        status_code=exc.http_status,
        content={"status": "error", "error": exc.user_message, "error_class": exc.error_class},
    )


@app.exception_handler(DictionaryError)
async def dictionary_error_handler(request: Request, exc: DictionaryError):
    """Dictionary unreadable, ambiguous or too big: 4xx in the same error shape."""
    return JSONResponse(
        status_code=exc.http_status,
        content={"status": "error", "error": str(exc), "error_class": exc.error_class},
    )


def _download_headers(filename: str, generation_info: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Headers for file downloads: say how the data was made (llm or cached)."""
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    method = (generation_info or {}).get("method")
    if method:
        headers["X-Generation-Method"] = str(method)
    model = (generation_info or {}).get("model")
    if model:
        headers["X-Generation-Model"] = str(model)
    trimming = (generation_info or {}).get("dictionary_trimming") or {}
    if trimming.get("trimmed"):
        headers["X-Dictionary-Trimmed"] = (
            f"kept={trimming['columns_kept']}; dropped={trimming['columns_dropped']}; "
            f"total={trimming['columns_total']}")
    return headers


def _read_dictionary_upload(upload: UploadFile) -> bytes:
    """Read an uploaded dictionary file, refusing (413) anything over the size limit.

    Reads at most limit + 1 bytes, so an oversized upload is never held in memory.
    """
    limit = max_dictionary_bytes()
    too_large = DictionaryTooLarge(
        f"The dictionary file is larger than the {limit}-byte limit "
        f"(MOCKDATA_DICTIONARY_MAX_BYTES).")
    if upload.size is not None and upload.size > limit:
        raise too_large
    upload.file.seek(0)
    content = upload.file.read(limit + 1)
    if len(content) > limit:
        raise too_large
    return content


def _dictionary_loaded_response(filename: Optional[str], catalog, table_name: str,
                                dictionary: Dict[str, Any], dictionary_id: str) -> Dict[str, Any]:
    """Success body for a loaded dictionary (one table)."""
    try:
        _, budget = data_dictionary.fit_to_prompt_budget(dictionary)
    except Exception as exc:  # noqa: BLE001 - a preview must never fail an upload
        logger.warning(f"Prompt budget preview skipped: {type(exc).__name__}")
        budget = None
    return {
        "status": "success",
        "filename": filename,
        "dictionary_id": dictionary_id,
        "columns_defined": len(dictionary.get("columns", {})),
        "dictionary": dictionary,
        "dictionary_format": catalog.shape,
        "table": table_name or None,
        "table_count": len(catalog.names),
        "notes": catalog.notes[:20],
        "prompt_budget": budget,
    }

@app.get("/")
async def root():
    """Serve the main web interface."""
    html_file = Path(__file__).parent / "src" / "web" / "index.html"
    if html_file.exists():
        with open(html_file, 'r') as f:
            content = f.read()
        return HTMLResponse(content=content)
    else:
        # Fallback to API info if HTML not found
        return {
            "service": "BYOD Synthetic Data Generator",
            "version": APP_VERSION,
            "status": "running",
            "endpoints": {
                "upload": "/upload",
                "generate": "/generate",
                "metadata": "/metadata",
                "health": "/health",
                "docs": "/docs"
            }
        }

@app.get("/about")
async def about():
    """Serve the about page with no-cache headers."""
    from fastapi.responses import Response

    html_file = Path(__file__).parent / "src" / "web" / "about.html"
    if html_file.exists():
        with open(html_file, 'r') as f:
            content = f.read()

        # Add cache-busting headers
        response = HTMLResponse(content=content)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    else:
        return HTMLResponse(content="<h1>About page not found</h1>")

@app.get("/dashboard")
async def dashboard():
    """Serve the usage dashboard page."""
    from fastapi.responses import Response

    html_file = Path(__file__).parent / "src" / "web" / "dashboard.html"
    if html_file.exists():
        with open(html_file, 'r') as f:
            content = f.read()

        # Add cache-busting headers for real-time updates
        response = HTMLResponse(content=content)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    else:
        return HTMLResponse(content="<h1>Dashboard page not found</h1>")

@app.get("/favicon.ico")
async def favicon():
    """Serve favicon.ico directly if it exists, otherwise redirect to favicon.svg."""
    from fastapi.responses import FileResponse, RedirectResponse

    # Check if favicon.ico exists
    ico_path = Path(__file__).parent / "src" / "web" / "static" / "img" / "favicon.ico"
    if ico_path.exists():
        return FileResponse(ico_path, media_type="image/x-icon")

    # Otherwise redirect to favicon.svg
    return RedirectResponse(url="/static/img/favicon.svg", status_code=301)

@app.get("/api")
async def api_info():
    """API information endpoint."""
    return {
        "service": "BYOD Synthetic Data Generator",
        "version": APP_VERSION,
        "status": "running",
        "endpoints": {
            "upload": "/upload",
            "generate": "/generate",
            "metadata": "/metadata",
            "health": "/health",
            "docs": "/docs"
        }
    }

def _ai_status() -> Dict[str, Any]:
    from src.core import llm_client
    ready = synthetic_generator is not None and synthetic_generator.openai_client is not None
    return {"ai_ready": ready,
            "ai_not_ready_reason": None if ready else (llm_client.not_ready_reason or "AI client not initialised")}


@app.get("/health")
async def health_check():
    """Liveness: the process is up. Always 200 (see /ready for AI readiness)."""
    from a2a_runtime import A2A_BACKEND
    ai = _ai_status()
    return {
        "status": "healthy",
        "openai_configured": ai["ai_ready"],
        **ai,
        "cache_enabled": True,
        "environment": settings.environment,
        "a2a_backend": A2A_BACKEND,
    }

@app.get("/ready")
async def readiness_check():
    """Readiness: 200 only when an Azure OpenAI client is configured, else 503.

    Used by the ACA readiness probe and deploy verification, so a revision
    without working AI config never takes traffic (there is no template mode).
    """
    ai = _ai_status()
    return JSONResponse(status_code=200 if ai["ai_ready"] else 503,
                        content={"status": "ready" if ai["ai_ready"] else "not_ready", **ai})

@app.get("/api/models")
async def list_models():
    """AI models a generation request may choose: the server default and the allow-list."""
    return model_catalog()


@app.get("/api/cache-info")
async def get_cache_info():
    """
    Get information about cached generation programs.

    Returns:
        Cache statistics and list of cached programs
    """
    try:
        cache_index = cache_manager.cache_index
        cache_dir = cache_manager.cache_dir

        # Calculate statistics
        total_entries = sum(len(entries) for entries in cache_index.values())
        format_hashes = len(cache_index)

        # Calculate cache size
        cache_size = 0
        for file_path in cache_dir.glob("*"):
            if file_path.is_file():
                cache_size += file_path.stat().st_size

        # Get detailed cache entries
        cache_entries = []
        for format_hash, entries in cache_index.items():
            for entry in entries:
                # Parse metadata if available
                metadata_file = entry.get("metadata_file")
                column_info = []
                if metadata_file and Path(metadata_file).exists():
                    try:
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)
                            columns = metadata.get("structure", {}).get("columns", [])
                            column_info = [col["name"] for col in columns]
                    except:
                        pass

                cache_entries.append({
                    "cache_key": entry.get("cache_key"),
                    "format_hash": format_hash,
                    "timestamp": entry.get("timestamp"),
                    "columns": column_info,
                    "version": entry.get("version")
                })

        # Sort by timestamp (newest first)
        cache_entries.sort(key=lambda x: x["timestamp"] if x["timestamp"] else "", reverse=True)

        return {
            "statistics": {
                "total_entries": total_entries,
                "unique_formats": format_hashes,
                "cache_size_bytes": cache_size,
                "cache_size_mb": round(cache_size / (1024 * 1024), 2)
            },
            "entries": cache_entries[:50]  # Return only the 50 most recent
        }
    except Exception as e:
        logger.error(f"Error getting cache info: {e}")
        raise HTTPException(status_code=500, detail=_public_error(e))

@app.delete("/api/cache/clear")
async def clear_cache(older_than_days: Optional[int] = None):
    """
    Clear cache entries.

    Args:
        older_than_days: Clear only entries older than specified days (optional)
    """
    try:
        cache_manager.clear_cache(older_than_days=older_than_days)

        if older_than_days:
            message = f"Cleared cache entries older than {older_than_days} days"
        else:
            message = "Cleared all cache entries"

        logger.info(message)
        return {"status": "success", "message": message}
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=_public_error(e))

@app.get("/api/usage-logs")
async def get_usage_logs(start: str = None, end: str = None):
    """
    Fetch usage logs for the dashboard.

    Args:
        start: Start date in YYYY-MM-DD format
        end: End date in YYYY-MM-DD format
    """
    import json
    from datetime import datetime, timedelta
    from collections import defaultdict

    # Default to last 7 days if no range specified
    if not end:
        end_date = datetime.now()
    else:
        end_date = datetime.strptime(end, "%Y-%m-%d")

    if not start:
        start_date = end_date - timedelta(days=7)
    else:
        start_date = datetime.strptime(start, "%Y-%m-%d")

    logs = []
    log_dir = Path(__file__).parent / "logs" / "usage"

    # Iterate through date range
    current_date = start_date
    while current_date <= end_date:
        log_file = log_dir / f"usage_{current_date.strftime('%Y-%m-%d')}.jsonl"

        if log_file.exists():
            with open(log_file, 'r') as f:
                for line in f:
                    try:
                        log_entry = json.loads(line)
                        logs.append(log_entry)
                    except json.JSONDecodeError:
                        continue

        current_date += timedelta(days=1)

    # Calculate metrics
    total_requests = len(logs)
    cache_hits = sum(1 for log in logs if log.get('cache_hit', False))
    total_rows = sum(log.get('num_rows') or 0 for log in logs)
    avg_response_time = sum(log.get('total_time', 0) for log in logs) / max(total_requests, 1)

    # Group by day for chart data
    daily_stats = defaultdict(lambda: {'requests': 0, 'cache_hits': 0})
    for log in logs:
        timestamp = log.get('timestamp', '')
        if timestamp:
            date_key = timestamp.split('T')[0]
            daily_stats[date_key]['requests'] += 1
            if log.get('cache_hit', False):
                daily_stats[date_key]['cache_hits'] += 1

    # Convert to list for frontend
    daily = [
        {'date': date, **stats}
        for date, stats in sorted(daily_stats.items())
    ]

    return {
        "logs": logs,
        "metrics": {
            "total_requests": total_requests,
            "cache_hits": cache_hits,
            "total_rows": total_rows,
            "avg_response_time": avg_response_time
        },
        "daily": daily
    }

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    extract_metadata_only: bool = Form(False)
):
    """
    Upload a file and optionally extract only metadata.
    
    Args:
        file: Uploaded file
        extract_metadata_only: If true, only return metadata without generating synthetic data
    """
    try:
        # Read file content
        content = await file.read()
        
        # Load data using DataLoader
        df = data_loader.load_from_bytes(content, file.filename)

        # Extract metadata with default safety mode
        extractor = MetadataExtractor(safety_mode="balanced")
        metadata = extractor.extract(df)
        
        if extract_metadata_only:
            # Return only metadata
            return JSONResponse(content={
                "status": "success",
                "filename": file.filename,
                "metadata": metadata
            })
        
        # Store metadata for later use
        metadata_key = cache_manager.generate_format_hash(metadata)
        
        return JSONResponse(content={
            "status": "success",
            "filename": file.filename,
            "metadata_key": metadata_key,
            "shape": metadata["structure"]["shape"],
            "columns": len(metadata["structure"]["columns"]),
            "message": "File uploaded and analyzed. Use /generate endpoint to create synthetic data."
        })
        
    except Exception as e:
        logger.error(f"Error processing upload: {e}")
        raise HTTPException(status_code=400, detail=_public_error(e))

@app.post("/metadata")
async def extract_metadata(file: UploadFile = File(...)):
    """
    Extract and return metadata from uploaded file.
    
    Args:
        file: Uploaded file
    """
    try:
        # Read file content
        content = await file.read()
        
        # Load data
        df = data_loader.load_from_bytes(content, file.filename)

        # Extract metadata
        extractor = MetadataExtractor(safety_mode="balanced")
        metadata = extractor.extract(df)

        # Convert to secure JSON
        secure_metadata = extractor.to_secure_json(metadata)
        
        return JSONResponse(content={
            "status": "success",
            "filename": file.filename,
            "metadata": json.loads(secure_metadata)
        })
        
    except Exception as e:
        logger.error(f"Error extracting metadata: {e}")
        raise HTTPException(status_code=400, detail=_public_error(e))

@app.post("/generate")
def generate_synthetic_data(
    file: Optional[UploadFile] = File(None),
    metadata_json: Optional[str] = Form(None),
    edited_data: Optional[str] = Form(None),
    num_rows: Optional[int] = Form(None),
    match_threshold: float = Form(0.8),
    output_format: str = Form("csv"),
    use_cache: bool = Form(True),
    cache_mode: str = Form("structure_stats"),  # off, structure, structure_stats
    file_count: int = Form(1),
    preview_only: bool = Form(False),
    safety_mode: str = Form("balanced"),
    model: Optional[str] = Form(None)
):
    """
    Generate synthetic data based on uploaded file or metadata.

    Args:
        file: Optional uploaded file
        metadata_json: Optional metadata JSON string
        num_rows: Number of rows to generate
        match_threshold: Statistical matching threshold (0-1)
        output_format: Output format (csv, json, excel)
        use_cache: Whether to use cached generation scripts
        file_count: Number of files to generate
        preview_only: If True, return preview data instead of file download
        model: AI model to write the generation code (a name from GET /api/models;
            empty = server default; any other name is refused with 400)

    Plain ``def`` on purpose: FastAPI runs it in the threadpool, so the slow,
    synchronous LLM call never blocks the event loop (or /health).
    """
    try:
        _check_generation_limits(num_rows, file_count)
        model = _resolve_model_or_400(model)

        # Track overall timing
        all_timings = {}
        request_start = time.time()

        # Create metadata extractor with specified safety mode
        extractor = MetadataExtractor(safety_mode=_privacy_mode_or_400(safety_mode))

        # Get metadata from edited data, file, or JSON
        metadata_start = time.time()
        if edited_data:
            # Parse edited CSV data
            df = pd.read_csv(io.StringIO(edited_data))
            metadata = extractor.extract(df)
        elif file:
            content = file.file.read()
            df = data_loader.load_from_bytes(content, file.filename)
            metadata = extractor.extract(df)
        elif metadata_json:
            # Client-supplied: checked and rebuilt from known keys, never used verbatim.
            metadata = _validated_client_metadata(metadata_json)
        else:
            raise HTTPException(status_code=400, detail="Either file or metadata_json must be provided")

        all_timings['metadata_extraction'] = time.time() - metadata_start
        
        # Cache "Off" on the page means off: nothing is read from or written to the cache.
        use_cache = use_cache and cache_mode != "off"

        # Check cache based on cache_mode
        cached_result = None
        cache_start = time.time()

        # Determine cache behavior based on mode
        if cache_mode == "off" or not use_cache:
            # No caching
            cached_result = None
        elif cache_mode == "structure":
            # Use lower threshold for structure-only matching
            cached_result = _find_cached(metadata, 0.5, num_rows, model)
        else:  # structure_stats (default)
            # Use provided threshold for full statistical matching
            cached_result = _find_cached(metadata, match_threshold, num_rows, model)

        all_timings['cache_check'] = time.time() - cache_start

        # If preview only, generate single file and return preview data
        if preview_only:
            # Generate single synthetic dataset
            code_start = time.time()
            synthetic_df = _run_cached_code(cached_result, num_rows or metadata["structure"]["shape"]["rows"])
            if synthetic_df is not None:
                logger.info("Used cached generation script for preview")
                all_timings['code_execution'] = time.time() - code_start
                generation_info = {"method": "cached", "cache_hit": True,
                                   "model": cached_result.get("model")}
                # Log usage for cached generation
                synthetic_generator._log_usage("cached", metadata, num_rows, all_timings)
            else:
                synthetic_df, generation_info = synthetic_generator.generate(
                    metadata=metadata,
                    num_rows=num_rows,
                    match_threshold=match_threshold,
                    use_cached=use_cache,
                    model=model
                )
                # Merge timings
                if 'step_timings' in generation_info:
                    all_timings.update(generation_info['step_timings'])

            # Calculate total time
            all_timings['total'] = time.time() - request_start

            # Always add all_timings to generation_info
            generation_info['all_timings'] = all_timings

            # Prepare preview data (first PREVIEW_ROWS rows)
            preview_rows = min(PREVIEW_ROWS, len(synthetic_df))
            preview_df = synthetic_df.head(preview_rows)

            # Convert DataFrame to dict for JSON serialization
            # to_json handles dates, NaN and numpy types; to_dict leaves Timestamps that JSON cannot carry
            preview_data = json.loads(preview_df.to_json(orient="records", date_format="iso"))

            # Generate download data for all files
            download_data = {}
            if file_count > 1:
                # Generate all files for download preparation
                base_filename = file.filename if file else "synthetic_data"
                base_name = base_filename.rsplit('.', 1)[0] if '.' in base_filename else base_filename

                synthetic_files = []
                for i in range(file_count):
                    if i == 0:
                        # Use already generated data for first file
                        synthetic_files.append((f"{base_name}_synthetic_{i+1:03d}", synthetic_df))
                    else:
                        # Generate additional files
                        additional_df, _ = synthetic_generator.generate(
                            metadata=metadata,
                            num_rows=num_rows,
                            match_threshold=match_threshold,
                            use_cached=use_cache,
                            model=model
                        )
                        synthetic_files.append((f"{base_name}_synthetic_{i+1:03d}", additional_df))

                download_data['file_count'] = file_count
                download_data['files'] = []
                for fname, df in synthetic_files:
                    download_data['files'].append({
                        'name': fname,
                        'rows': len(df),
                        'columns': len(df.columns)
                    })

            return JSONResponse(content={
                "status": "success",
                "preview": preview_data,
                "total_rows": len(synthetic_df),
                "total_columns": len(synthetic_df.columns),
                "column_names": list(synthetic_df.columns),
                "file_count": file_count,
                "download_info": download_data,
                "generation_info": generation_info
            })

        # Generate multiple files if requested
        if file_count > 1:
            # Generate multiple synthetic datasets
            synthetic_files = []
            base_filename = file.filename if file else "synthetic_data"
            base_name = base_filename.rsplit('.', 1)[0] if '.' in base_filename else base_filename

            zip_info = None
            for i in range(file_count):
                synthetic_df = _run_cached_code(cached_result, num_rows or metadata["structure"]["shape"]["rows"])
                if synthetic_df is not None:
                    logger.info(f"Used cached generation script for file {i+1}/{file_count}")
                    zip_info = zip_info or {"method": "cached", "model": cached_result.get("model")}
                else:
                    cached_result = None  # failed once: do not try it again for later files
                    # Generate new synthetic data
                    synthetic_df, zip_info = synthetic_generator.generate(
                        metadata=metadata,
                        num_rows=num_rows,
                        match_threshold=match_threshold,
                        use_cached=use_cache,
                        model=model
                    )

                # Store generated dataframe with filename
                filename = f"{base_name}_synthetic_{i+1:03d}"
                synthetic_files.append((filename, synthetic_df))

            # Create ZIP file
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for filename, df in synthetic_files:
                    if output_format == "json":
                        json_data = df.to_json(orient="records", indent=2)
                        zipf.writestr(f"{filename}.json", json_data)
                    elif output_format == "excel":
                        excel_buffer = io.BytesIO()
                        df.to_excel(excel_buffer, index=False)
                        excel_buffer.seek(0)
                        zipf.writestr(f"{filename}.xlsx", excel_buffer.getvalue())
                    else:  # CSV
                        csv_data = df.to_csv(index=False)
                        zipf.writestr(f"{filename}.csv", csv_data)

            zip_buffer.seek(0)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return StreamingResponse(
                zip_buffer,
                media_type="application/zip",
                headers=_download_headers(f"synthetic_data_{timestamp}.zip", zip_info)
            )

        # Single file generation (existing logic)
        code_start = time.time()
        synthetic_df = _run_cached_code(cached_result, num_rows or metadata["structure"]["shape"]["rows"])
        if synthetic_df is not None:
            logger.info("Used cached generation script")
            code_execution_time = time.time() - code_start
            generation_info = {
                "method": "cached",
                "cache_hit": True,
                "model": cached_result.get("model"),
                "all_timings": {
                    "metadata_extraction": all_timings.get('metadata_extraction', 0),
                    "cache_check": all_timings.get('cache_check', 0),
                    "code_execution": code_execution_time,
                    "total": time.time() - request_start
                }
            }
            # Log usage for cached generation
            synthetic_generator._log_usage("cached", metadata, num_rows, generation_info['all_timings'])
        else:
            # Generate new synthetic data
            synthetic_df, generation_info = synthetic_generator.generate(
                metadata=metadata,
                num_rows=num_rows,
                match_threshold=match_threshold,
                use_cached=use_cache,
                model=model
            )

            # Cache the result if generation was successful
            if use_cache and synthetic_generator.openai_client:
                # Get the generation code (would need to modify generator to return it)
                # For now, we'll skip caching the code
                pass

        # Convert to requested format
        if output_format == "json":
            output_data = synthetic_df.to_json(orient="records")
            return JSONResponse(content={
                "status": "success",
                "data": json.loads(output_data),
                "shape": list(synthetic_df.shape),
                "columns": list(synthetic_df.columns),
                "generation_info": generation_info
            })

        elif output_format == "excel":
            output = io.BytesIO()
            synthetic_df.to_excel(output, index=False)
            output.seek(0)

            return StreamingResponse(
                output,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers=_download_headers("synthetic_data.xlsx", generation_info)
            )

        else:  # Default to CSV
            output = io.StringIO()
            synthetic_df.to_csv(output, index=False)
            output.seek(0)

            return StreamingResponse(
                io.BytesIO(output.getvalue().encode()),
                media_type="text/csv",
                headers=_download_headers("synthetic_data.csv", generation_info)
            )
            
    except (HTTPException, AIGenerationError):
        raise
    except Exception as e:
        logger.error(f"Error generating synthetic data: {e}")
        raise HTTPException(status_code=500, detail=_public_error(e))


@app.post("/generate-sse")
async def generate_with_sse(
    file: Optional[UploadFile] = File(None),
    edited_data: Optional[str] = Form(None),
    metadata_json: Optional[str] = Form(None),
    num_rows: Optional[int] = Form(None),  # None = as many rows as the uploaded file
    match_threshold: float = Form(0.8),
    output_format: str = Form("csv"),
    use_cache: bool = Form(True),
    cache_mode: str = Form("structure_stats"),
    file_count: int = Form(1),
    preview_only: bool = Form(False),
    safety_mode: str = Form("balanced"),
    model: Optional[str] = Form(None)
):
    """Generate synthetic data with Server-Sent Events for progress updates"""
    import asyncio
    from typing import AsyncGenerator

    # Refused before the stream starts, so the client gets a real 400.
    _check_generation_limits(num_rows, file_count)
    model = _resolve_model_or_400(model)

    # Read file content before the generator to avoid closed file issues
    file_content = None
    file_name = None
    if file:
        file_content = await file.read()
        file_name = file.filename

    # Client-supplied metadata is checked (never used verbatim) when it is the source.
    client_metadata = None
    if not edited_data and not file_content and metadata_json:
        client_metadata = _validated_client_metadata(metadata_json)

    # Cache "Off" on the page means off: nothing is read from or written to the cache.
    use_cache = use_cache and cache_mode != "off"
    # Checked before the stream starts, so a bad value is a real 400.
    privacy_mode = _privacy_mode_or_400(safety_mode)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # Send initial event
            yield f"data: {json.dumps({'step': 'extract-metadata', 'status': 'active'})}\n\n"
            await asyncio.sleep(0.01)  # Small delay for browser to process

            # Track timing
            all_timings = {}
            request_start = time.time()

            # Extract metadata
            metadata_start = time.time()
            extractor = MetadataExtractor(safety_mode=privacy_mode)

            if edited_data:
                df = pd.read_csv(io.StringIO(edited_data))
                metadata = extractor.extract(df)
            elif file_content:
                df = data_loader.load_from_bytes(file_content, file_name)
                metadata = extractor.extract(df)
            elif client_metadata is not None:
                metadata = client_metadata
            elif file_name:
                yield f"data: {json.dumps({'error': 'The uploaded file is empty.', 'http_status': 400})}\n\n"
                return
            else:
                yield f"data: {json.dumps({'error': 'No data provided'})}\n\n"
                return
            _rows_for_request(num_rows, metadata)

            metadata_time = time.time() - metadata_start
            all_timings['metadata_extraction'] = metadata_time
            yield f"data: {json.dumps({'step': 'extract-metadata', 'status': 'completed', 'duration': metadata_time})}\n\n"

            # Check cache
            yield f"data: {json.dumps({'step': 'check-cache', 'status': 'active'})}\n\n"
            cache_start = time.time()

            cached_result = None
            if cache_mode == "off" or not use_cache:
                cached_result = None
            elif cache_mode == "structure":
                cached_result = await run_in_threadpool(_find_cached, metadata, 0.5, num_rows, model)
            else:
                cached_result = await run_in_threadpool(_find_cached, metadata, match_threshold, num_rows, model)

            cache_time = time.time() - cache_start
            all_timings['cache_check'] = cache_time

            cache_hit = cached_result and "generation_code" in cached_result
            cache_text = 'Cache Hit ✓' if cache_hit else 'Cache Miss'
            yield f"data: {json.dumps({'step': 'check-cache', 'status': 'completed', 'duration': cache_time, 'text': cache_text})}\n\n"

            # Generate code. Cached code that no longer runs is dropped and replaced by new code.
            synthetic_df = None
            if cache_hit:
                exec_start = time.time()
                synthetic_df = await run_in_threadpool(_run_cached_code, cached_result, num_rows or metadata["structure"]["shape"]["rows"])

            if synthetic_df is not None:
                yield f"data: {json.dumps({'step': 'prepare-llm', 'status': 'skipped'})}\n\n"
                yield f"data: {json.dumps({'step': 'generate-code', 'status': 'skipped', 'text': 'Using Cached Code'})}\n\n"
                yield f"data: {json.dumps({'step': 'execute-code', 'status': 'active'})}\n\n"
                exec_time = time.time() - exec_start
                all_timings['code_execution'] = exec_time
                yield f"data: {json.dumps({'step': 'execute-code', 'status': 'completed', 'duration': exec_time})}\n\n"

                generation_info = {"method": "cached", "cache_hit": True, "all_timings": all_timings,
                                   "model": cached_result.get("model")}
                # Log usage for cached generation
                synthetic_generator._log_usage("cached", metadata, num_rows, all_timings)

            else:
                # Generate with LLM (includes prepare, generate, and execute)
                yield f"data: {json.dumps({'step': 'prepare-llm', 'status': 'active'})}\n\n"
                gen_start = time.time()

                # Off the event loop: the LLM call takes tens of seconds and
                # must not starve /health (ACA liveness) or other requests.
                synthetic_df, generation_info = await run_in_threadpool(
                    synthetic_generator.generate,
                    metadata=metadata,
                    num_rows=num_rows,
                    match_threshold=match_threshold,
                    use_cached=use_cache,
                    model=model,
                )

                # Extract individual step timings from generation_info
                if 'step_timings' in generation_info:
                    step_timings = generation_info['step_timings']
                    all_timings.update(step_timings)

                    # Report actual timings for each step
                    if 'llm_response' in step_timings and step_timings['llm_response'] > 0:
                        # LLM was actually called - report real timings
                        yield f"data: {json.dumps({'step': 'prepare-llm', 'status': 'completed', 'duration': 0})}\n\n"
                        yield f"data: {json.dumps({'step': 'generate-code', 'status': 'active'})}\n\n"
                        yield f"data: {json.dumps({'step': 'generate-code', 'status': 'completed', 'duration': step_timings.get('llm_response', 0)})}\n\n"
                        yield f"data: {json.dumps({'step': 'execute-code', 'status': 'active'})}\n\n"
                        yield f"data: {json.dumps({'step': 'execute-code', 'status': 'completed', 'duration': step_timings.get('code_execution', 0)})}\n\n"
                    else:
                        # No model call was needed: the generator reused a cached script.
                        yield f"data: {json.dumps({'step': 'prepare-llm', 'status': 'skipped'})}\n\n"
                        yield f"data: {json.dumps({'step': 'generate-code', 'status': 'skipped', 'text': 'Using Cached Code'})}\n\n"
                        yield f"data: {json.dumps({'step': 'execute-code', 'status': 'active'})}\n\n"
                        yield f"data: {json.dumps({'step': 'execute-code', 'status': 'completed', 'duration': step_timings.get('code_execution', 0)})}\n\n"
                else:
                    # No step timings available
                    gen_time = time.time() - gen_start
                    yield f"data: {json.dumps({'step': 'prepare-llm', 'status': 'skipped'})}\n\n"
                    yield f"data: {json.dumps({'step': 'generate-code', 'status': 'skipped'})}\n\n"
                    yield f"data: {json.dumps({'step': 'execute-code', 'status': 'completed', 'duration': gen_time})}\n\n"

            # Validate
            yield f"data: {json.dumps({'step': 'validate', 'status': 'active'})}\n\n"
            validate_start = time.time()
            # Actual validation would happen here if needed
            validate_time = time.time() - validate_start
            all_timings['validation'] = validate_time
            yield f"data: {json.dumps({'step': 'validate', 'status': 'completed', 'duration': validate_time})}\n\n"

            # Send completion with data
            all_timings['total'] = time.time() - request_start
            generation_info['all_timings'] = all_timings

            # Prepare result
            if preview_only:
                preview_rows = min(PREVIEW_ROWS, len(synthetic_df))
                preview_df = synthetic_df.head(preview_rows)

                # Always use to_json() for proper datetime serialization, regardless of output_format
                # Since preview is always shown in table format in UI
                preview_data = json.loads(preview_df.to_json(orient="records", date_format="iso"))

                result = {
                    "complete": True,
                    "status": "success",
                    "preview": preview_data,
                    "total_rows": len(synthetic_df),
                    "total_columns": len(synthetic_df.columns),
                    "column_names": list(synthetic_df.columns),
                    "file_count": file_count,
                    "generation_info": generation_info
                }
            else:
                if output_format == "json":
                    data = json.loads(synthetic_df.to_json(orient="records", date_format="iso"))
                else:
                    data = synthetic_df.to_csv(index=False)

                result = {
                    "complete": True,
                    "data": data,
                    "generation_info": generation_info
                }

            yield f"data: {json.dumps(result)}\n\n"

        except AIGenerationError as e:
            # Already logged as a structured ai_generation_failed line.
            yield f"data: {json.dumps({'error': e.user_message, 'error_class': e.error_class, 'http_status': e.http_status})}\n\n"
        except Exception as e:
            # Type only: the message can quote a value from the uploaded file.
            logger.error(f"SSE generation error: {type(e).__name__}")
            payload = {'error': _public_error(e)}
            if isinstance(e, HTTPException):
                payload['http_status'] = e.status_code
            yield f"data: {json.dumps(payload)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )

@app.post("/dictionary/upload")
def upload_data_dictionary(
    file: UploadFile = File(...),
    format: Optional[str] = Form("auto"),
    table: Optional[str] = Form(None)
):
    """
    Upload and parse a data dictionary.

    Plain ``def``: parsing a large file (tens of MB) runs in the threadpool.

    Args:
        file: Data dictionary file (JSON, YAML, CSV, Excel, or text)
        format: Format hint ('json', 'yaml', 'csv', 'excel', 'text', 'auto')
        table: Which table to load when the file defines several (e.g. a FHIR
            resource name in a Bundle). Without it such a file answers
            ``status: "choose_table"`` with the table names; pick one with
            ``POST /dictionary/table`` (no re-upload needed).

    The response carries ``dictionary_id``: send it with later requests to use this
    upload. Without the id no other request can read or use it.
    """
    try:
        content = _read_dictionary_upload(file)

        # Parse the dictionary into its table(s)
        catalog = data_dictionary.load_catalog(content, format or "auto", filename=file.filename or "")

        if catalog.is_multi_table and not (table or "").strip():
            # Kept under its own id; nothing usable until a table is chosen
            dictionary_id = _remember_dictionary(catalog, {})
            return JSONResponse(content={
                "status": "choose_table",
                "filename": file.filename,
                "dictionary_id": dictionary_id,
                "dictionary_format": catalog.shape,
                "table_count": len(catalog.names),
                "tables": catalog.names,
                "message": (f"This file defines {len(catalog.names)} tables. Choose one "
                            f"to generate data for."),
            })

        table_name, parsed_dict = catalog.select(table)

        # Keep it for this client's later requests (they send the id back)
        dictionary_id = _remember_dictionary(catalog, parsed_dict)

        # Return parsed structure
        return JSONResponse(content=_dictionary_loaded_response(
            file.filename, catalog, table_name, parsed_dict, dictionary_id))

    except DictionaryError:
        raise
    except Exception as e:
        logger.error(f"Error parsing data dictionary: {e}")
        raise HTTPException(status_code=400, detail=_public_error(e))

@app.post("/dictionary/table")
def select_dictionary_table(table: str = Form(...), dictionary_id: Optional[str] = Form(None)):
    """Choose one table of an uploaded multi-table dictionary (no re-upload).

    ``dictionary_id`` is the id ``/dictionary/upload`` returned; absent, unknown or
    expired answers the same 400 as when nothing has been uploaded.
    """
    entry = _recall_dictionary(dictionary_id)
    if entry is None:
        raise NoDictionaryLoaded("No data dictionary has been uploaded yet; upload one first.")
    catalog = entry["catalog"]
    table_name, parsed_dict = catalog.select(table)
    entry["dictionary"] = parsed_dict
    return JSONResponse(content=_dictionary_loaded_response(
        None, catalog, table_name, parsed_dict, dictionary_id))

@app.post("/dictionary/validate")
async def validate_with_dictionary(
    data_file: UploadFile = File(...),
    dictionary_file: Optional[UploadFile] = File(None),
    use_stored: bool = Form(True),
    table: Optional[str] = Form(None),
    dictionary_id: Optional[str] = Form(None)
):
    """
    Validate data against a data dictionary.

    Args:
        data_file: Data file to validate
        dictionary_file: Optional dictionary file (used for this request only)
        use_stored: Accepted for compatibility, no effect (an upload is used only by id)
        dictionary_id: Id returned by /dictionary/upload, used when no file is sent
    """
    try:
        # Load the data
        data_content = await data_file.read()
        df = data_loader.load_from_bytes(data_content, data_file.filename)

        # Get dictionary
        if dictionary_file:
            dict_content = _read_dictionary_upload(dictionary_file)
            dictionary = data_dictionary.parse_dictionary(
                dict_content, filename=dictionary_file.filename or "", table=table)
        else:
            entry = _recall_dictionary(dictionary_id)
            if entry is not None and (table or "").strip():
                _, dictionary = entry["catalog"].select(table)
            elif entry is not None and entry["dictionary"]:
                dictionary = entry["dictionary"]
            else:
                raise HTTPException(status_code=400, detail="No data dictionary provided or stored")

        # Validate
        errors = data_dictionary.validate_data(df, dictionary)

        return JSONResponse(content={
            "status": "success" if not errors else "validation_failed",
            "data_file": data_file.filename,
            "rows_validated": len(df),
            "columns_validated": len(df.columns),
            "errors": errors,
            "valid": len(errors) == 0
        })

    except DictionaryError:
        raise
    except Exception as e:
        logger.error(f"Error validating data: {e}")
        raise HTTPException(status_code=400, detail=_public_error(e))

@app.post("/generate-with-dictionary")
def generate_with_dictionary(
    dictionary_file: Optional[UploadFile] = File(None),
    data_file: Optional[UploadFile] = File(None),
    use_stored_dictionary: bool = Form(True),
    num_rows: Optional[int] = Form(100),
    output_format: str = Form("csv"),
    file_count: int = Form(1),
    preview_only: bool = Form(False),
    table: Optional[str] = Form(None),
    preview_id: Optional[str] = Form(None),
    dictionary_id: Optional[str] = Form(None),
    safety_mode: str = Form("balanced"),
    model: Optional[str] = Form(None)
):
    """
    ``dictionary_id``: the id /dictionary/upload (or a preview made with an inline
    ``dictionary_file``) returned; it is the only way to use an uploaded dictionary.
    ``preview_id``: the id a preview response returned. A download that sends it gets the
    rows that preview showed instead of a newly generated set (falls back to generating
    if the id is unknown or has expired).
    Generate synthetic data using data dictionary constraints.

    The dictionary text sent to the model is kept under the prompt budget
    (env MOCKDATA_DICTIONARY_PROMPT_MAX_CHARS); if it had to be trimmed the
    response says so (``dictionary_trimming``, header ``X-Dictionary-Trimmed``).

    Args:
        dictionary_file: Optional dictionary file
        data_file: Optional data file for statistical reference
        use_stored_dictionary: Accepted for compatibility, no effect (an upload is used only by id)
        num_rows: Number of rows to generate
        output_format: Output format
        file_count: Number of files to generate
        preview_only: Return preview instead of download
        table: Which table to use when the dictionary defines several
        safety_mode: Privacy level used when reading ``data_file``
        model: AI model to write the generation code (a name from GET /api/models;
            empty = server default; any other name is refused with 400)
    """
    try:
        _check_generation_limits(num_rows, file_count)
        model = _resolve_model_or_400(model)

        # Get dictionary: an inline file (this request only) or this client's own upload
        if dictionary_file:
            dict_content = _read_dictionary_upload(dictionary_file)
            catalog = data_dictionary.load_catalog(
                dict_content, filename=dictionary_file.filename or "")
            _, dictionary = catalog.select(table)  # several tables, no choice: 400 with names
            # Kept only when the id can be handed back (a preview), for the download that follows
            dictionary_id = _remember_dictionary(catalog, dictionary) if preview_only else None
        else:
            entry = _recall_dictionary(dictionary_id)
            if entry is None:
                raise HTTPException(status_code=400, detail="No data dictionary provided")
            if (table or "").strip():
                _, dictionary = entry["catalog"].select(table)
                entry["dictionary"] = dictionary
            elif entry["dictionary"]:
                dictionary = entry["dictionary"]
            else:
                _, dictionary = entry["catalog"].select(None)  # several tables: 400 with names

        # Only a bounded copy of the dictionary goes into the prompt.
        dictionary, dictionary_trimming = data_dictionary.fit_to_prompt_budget(dictionary)

        # Create metadata from dictionary
        metadata = {
            "structure": {
                "columns": [],
                "shape": {"rows": num_rows, "columns": len(dictionary.get("columns", {}))}
            },
            "statistics": {}
        }

        # If data file provided, extract base statistics
        if data_file:
            data_content = data_file.file.read()
            df = data_loader.load_from_bytes(data_content, data_file.filename)
            metadata = MetadataExtractor(safety_mode=_privacy_mode_or_400(safety_mode)).extract(df)

        # Apply dictionary constraints to metadata
        metadata = data_dictionary.apply_to_metadata(metadata, dictionary)

        # With no data file there are no structure columns: the check after generation
        # compares against the dictionary's column names instead.
        if not metadata.get("structure", {}).get("columns"):
            metadata["expected_columns"] = list((dictionary.get("columns") or {}).keys())

        # Add dictionary constraints to generation prompt
        if "generation_constraints" not in metadata:
            metadata["generation_constraints"] = data_dictionary.to_generation_constraints(dictionary)

        # Generate synthetic data
        if preview_only:
            synthetic_df, generation_info = synthetic_generator.generate(
                metadata=metadata,
                num_rows=num_rows,
                match_threshold=0.9,
                model=model
            )
            generation_info["dictionary_trimming"] = dictionary_trimming
            new_preview_id = _remember_preview(synthetic_df, generation_info, num_rows, model)

            preview_rows = min(PREVIEW_ROWS, len(synthetic_df))
            preview_df = synthetic_df.head(preview_rows)

            return JSONResponse(content={
                "status": "success",
                "preview": json.loads(preview_df.to_json(orient="records", date_format="iso")),
                "total_rows": len(synthetic_df),
                "total_columns": len(synthetic_df.columns),
                "column_names": list(synthetic_df.columns),
                "file_count": file_count,
                "dictionary_applied": True,
                "dictionary_trimming": dictionary_trimming,
                "preview_id": new_preview_id,
                "dictionary_id": dictionary_id,
                "generation_info": generation_info
            })

        # Generate actual files
        last = _recall_preview(preview_id, num_rows, model)

        def _generate(index):
            if last and index == 0:
                return last["df"], dict(last["info"])
            return synthetic_generator.generate(
                metadata=metadata, num_rows=num_rows, match_threshold=0.9, model=model)

        if file_count > 1:
            synthetic_files = []
            zip_info = None
            for i in range(file_count):
                synthetic_df, zip_info = _generate(i)
                zip_info["dictionary_trimming"] = dictionary_trimming
                synthetic_files.append((f"synthetic_{i+1:03d}", synthetic_df))

            # Create ZIP
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for filename, df in synthetic_files:
                    if output_format == "json":
                        json_data = df.to_json(orient="records", indent=2)
                        zipf.writestr(f"{filename}.json", json_data)
                    elif output_format == "excel":
                        excel_buffer = io.BytesIO()
                        df.to_excel(excel_buffer, index=False)
                        excel_buffer.seek(0)
                        zipf.writestr(f"{filename}.xlsx", excel_buffer.getvalue())
                    else:  # CSV
                        csv_data = df.to_csv(index=False)
                        zipf.writestr(f"{filename}.csv", csv_data)

            zip_buffer.seek(0)
            return StreamingResponse(
                zip_buffer,
                media_type="application/zip",
                headers=_download_headers("dictionary_generated.zip", zip_info)
            )
        else:
            # Single file
            synthetic_df, generation_info = _generate(0)
            generation_info["dictionary_trimming"] = dictionary_trimming

            if output_format == "json" and preview_id:
                # A download: the file holds the rows themselves, not a status wrapper
                rows = synthetic_df.to_json(orient="records", date_format="iso", indent=2)
                return StreamingResponse(
                    io.BytesIO(rows.encode()),
                    media_type="application/json",
                    headers=_download_headers("dictionary_generated.json", generation_info)
                )
            if output_format == "json":
                output_data = synthetic_df.to_json(orient="records")
                return JSONResponse(content={
                    "status": "success",
                    "data": json.loads(output_data),
                    "dictionary_trimming": dictionary_trimming,
                    "generation_info": generation_info
                })
            elif output_format == "excel":
                output = io.BytesIO()
                synthetic_df.to_excel(output, index=False)
                output.seek(0)
                return StreamingResponse(
                    output,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers=_download_headers("dictionary_generated.xlsx", generation_info)
                )
            else:  # CSV
                output = io.StringIO()
                synthetic_df.to_csv(output, index=False)
                output.seek(0)
                return StreamingResponse(
                    io.BytesIO(output.getvalue().encode()),
                    media_type="text/csv",
                    headers=_download_headers("dictionary_generated.csv", generation_info)
                )

    except (HTTPException, AIGenerationError, DictionaryError):
        raise
    except Exception as e:
        logger.error(f"Error generating with dictionary: {e}")
        raise HTTPException(status_code=500, detail=_public_error(e))

@app.post("/generate/batch")
async def generate_batch():
    """Batch generation is not part of this release: always 501, nothing is read or written."""
    raise HTTPException(status_code=501, detail=BATCH_NOT_AVAILABLE)


@app.get("/batch/{batch_id}")
async def get_batch_status(batch_id: str):
    """Batch generation is not part of this release: always 501, nothing is read."""
    raise HTTPException(status_code=501, detail=BATCH_NOT_AVAILABLE)

@app.delete("/cache")
async def clear_cache(older_than_days: Optional[int] = None):
    """
    Clear cache entries.

    Args:
        older_than_days: Clear entries older than specified days
    """
    try:
        cache_manager.clear_cache(older_than_days)
        return JSONResponse(content={
            "status": "success",
            "message": f"Cache cleared (older_than_days={older_than_days})"
        })
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=_public_error(e))


# ---------------------------------------------------------------------------
# A2A endpoints (additive — do not remove or reorder routes above)
# ---------------------------------------------------------------------------

@app.get("/.well-known/agent.json", include_in_schema=False)
async def agent_card():
    """Serve the AgentCard so external systems can discover this agent."""
    from src.a2a_agent import build_card
    from a2a_runtime import serve_agent_card
    from fastapi.responses import Response

    card = build_card(internal_only=False)
    body, headers, content_type = serve_agent_card(card)
    return Response(content=body, media_type=content_type, headers=headers)


@app.post("/a2a/{agent_id}")
async def a2a_dispatch(agent_id: str, raw_request: Dict[str, Any]):
    """Receive an A2A Message envelope and dispatch to the registered agent.

    Args:
        agent_id:    Must be ``"mock-data-generator"``.
        raw_request: A2A Message envelope (JSON body with ``payload`` and
                     ``metadata`` keys as produced by
                     :func:`a2a_runtime.encode_message`).

    Returns:
        A2A Message envelope wrapping the agent's response payload.
    """
    from a2a_runtime import decode_message, encode_message, default_registry

    if agent_id != "mock-data-generator":
        raise HTTPException(
            status_code=404,
            detail=f"No A2A agent registered for agent_id {agent_id!r}.",
        )

    agent = default_registry.get(agent_id)
    if agent is None:
        raise HTTPException(
            status_code=503,
            detail=f"Agent {agent_id!r} is registered but not yet available.",
        )

    try:
        payload, meta = decode_message(raw_request)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Malformed A2A envelope: {exc}") from exc

    result = await agent.run(payload)

    # Echo the request cycle back: cycle advancement is owned by the
    # orchestrator (e.g. the dcri-ct-graph runner), and A2AClient ignores the
    # response cycle. Echoing keeps both DCRI services behaving identically.
    response_message = encode_message(
        result,
        correlation_id=meta["correlation_id"],
        cycle=meta["cycle"],
        agent_id=agent_id,
    )
    return JSONResponse(content=response_message)


# ---------------------------------------------------------------------------
# JSON API for other programs (/api/v1): routes and uniform error shape
# ---------------------------------------------------------------------------
api_v1.install(app)


# Main entry point
if __name__ == "__main__":
    import os
    # Cloud Run (and most PaaS) inject the bind port via $PORT; fall back to
    # APP_PORT, then the configured default.
    port = int(os.environ.get("PORT", os.environ.get("APP_PORT", settings.app_port)))
    
    # Run the application
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=port,
        reload=False,  # Disable reload to avoid port conflicts
        log_level=settings.log_level.lower()
    )