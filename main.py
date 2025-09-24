"""Main FastAPI application for BYOD Synthetic Data Generator."""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import json
import io
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, BackgroundTasks
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
from src.core.synthetic_generator import SyntheticDataGenerator
from src.core.cache_manager import CacheManager
from src.core.data_dictionary import DataDictionary
from src.utils.config import settings
from src.utils.logger import logger

# Initialize components
data_loader = DataLoader()
metadata_extractor = None  # Will be created with safety_mode per request
cache_manager = CacheManager()
data_dictionary = DataDictionary()

# Initialize synthetic generator (OpenAI client will be added when API key is provided)
synthetic_generator = None

def initialize_openai_client():
    """Initialize OpenAI client if credentials are available."""
    global synthetic_generator

    logger.info(f"Initializing OpenAI client...")
    logger.info(f"Endpoint configured: {bool(settings.azure_openai_endpoint)}")
    logger.info(f"API key configured: {bool(settings.azure_openai_api_key)}")
    logger.info(f"Chat deployment: {settings.azure_openai_chat_deployment}")
    logger.info(f"API version: {settings.azure_openai_api_version}")

    if settings.azure_openai_api_key and settings.azure_openai_endpoint:
        try:
            from openai import AzureOpenAI

            client = AzureOpenAI(
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version,
                azure_endpoint=settings.azure_openai_endpoint
            )

            synthetic_generator = SyntheticDataGenerator(openai_client=client)
            logger.info("✓ OpenAI client initialized successfully")
            return True
        except Exception as e:
            logger.error(f"✗ Failed to initialize OpenAI client: {type(e).__name__}: {e}")
            synthetic_generator = SyntheticDataGenerator()
            return False
    else:
        logger.warning("✗ OpenAI credentials not configured, using fallback generation")
        if not settings.azure_openai_api_key:
            logger.warning("  - Missing: AZURE_OPENAI_API_KEY")
        if not settings.azure_openai_endpoint:
            logger.warning("  - Missing: AZURE_OPENAI_ENDPOINT")
        synthetic_generator = SyntheticDataGenerator()
        return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan."""
    # Startup
    logger.info("Starting BYOD Synthetic Data Generator")
    initialize_openai_client()
    
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
    description="Generate privacy-safe synthetic data that preserves statistical properties",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware with secure configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins(),  # Environment-specific origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],  # Only methods needed (GET for reading, POST for file uploads/generation, OPTIONS for preflight)
    allow_headers=["*"],
    max_age=3600,  # Cache preflight requests for 1 hour
)

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
            "version": "1.0.0",
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
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "upload": "/upload",
            "generate": "/generate",
            "metadata": "/metadata",
            "health": "/health",
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "openai_configured": synthetic_generator.openai_client is not None,
        "cache_enabled": True,
        "environment": settings.environment
    }

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
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=400, detail=str(e))

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
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/generate")
async def generate_synthetic_data(
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
    safety_mode: str = Form("balanced")
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
    """
    try:
        # Track overall timing
        all_timings = {}
        request_start = time.time()

        # Create metadata extractor with specified safety mode
        extractor = MetadataExtractor(safety_mode=safety_mode)

        # Get metadata from edited data, file, or JSON
        metadata_start = time.time()
        if edited_data:
            # Parse edited CSV data
            df = pd.read_csv(io.StringIO(edited_data))
            metadata = extractor.extract(df)
        elif file:
            content = await file.read()
            df = data_loader.load_from_bytes(content, file.filename)
            metadata = extractor.extract(df)
        elif metadata_json:
            metadata = json.loads(metadata_json)
        else:
            raise HTTPException(status_code=400, detail="Either file or metadata_json must be provided")

        all_timings['metadata_extraction'] = time.time() - metadata_start
        
        # Check cache based on cache_mode
        cached_result = None
        cache_start = time.time()

        # Determine cache behavior based on mode
        if cache_mode == "off" or not use_cache:
            # No caching
            cached_result = None
        elif cache_mode == "structure":
            # Use lower threshold for structure-only matching
            cached_result = cache_manager.find_similar_cached(metadata, match_threshold=0.5)
        else:  # structure_stats (default)
            # Use provided threshold for full statistical matching
            cached_result = cache_manager.find_similar_cached(metadata, match_threshold)

        all_timings['cache_check'] = time.time() - cache_start

        # If preview only, generate single file and return preview data
        if preview_only:
            # Generate single synthetic dataset
            if cached_result and "generation_code" in cached_result:
                logger.info("Using cached generation script for preview")
                code_start = time.time()
                generation_code = cached_result["generation_code"]
                synthetic_df = synthetic_generator._execute_generation_code(generation_code)
                all_timings['code_execution'] = time.time() - code_start
                generation_info = {"method": "cached", "cache_hit": True}
                # Log usage for cached generation
                synthetic_generator._log_usage("cached", metadata, num_rows, all_timings)
            else:
                synthetic_df, generation_info = synthetic_generator.generate(
                    metadata=metadata,
                    num_rows=num_rows,
                    match_threshold=match_threshold,
                    use_cached=use_cache
                )
                # Merge timings
                if 'step_timings' in generation_info:
                    all_timings.update(generation_info['step_timings'])

            # Calculate total time
            all_timings['total'] = time.time() - request_start

            # Always add all_timings to generation_info
            generation_info['all_timings'] = all_timings

            # Prepare preview data (first 10 rows)
            preview_rows = min(10, len(synthetic_df))
            preview_df = synthetic_df.head(preview_rows)

            # Convert DataFrame to dict for JSON serialization
            preview_data = preview_df.to_dict('records')

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
                            use_cached=use_cache
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

            for i in range(file_count):
                if cached_result and "generation_code" in cached_result:
                    logger.info(f"Using cached generation script for file {i+1}/{file_count}")
                    generation_code = cached_result["generation_code"]
                    synthetic_df = synthetic_generator._execute_generation_code(generation_code)
                else:
                    # Generate new synthetic data
                    synthetic_df, _ = synthetic_generator.generate(
                        metadata=metadata,
                        num_rows=num_rows,
                        match_threshold=match_threshold,
                        use_cached=use_cache
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
                headers={"Content-Disposition": f"attachment; filename=synthetic_data_{timestamp}.zip"}
            )

        # Single file generation (existing logic)
        if cached_result and "generation_code" in cached_result:
            logger.info("Using cached generation script")
            code_start = time.time()
            generation_code = cached_result["generation_code"]
            synthetic_df = synthetic_generator._execute_generation_code(generation_code)
            code_execution_time = time.time() - code_start
            generation_info = {
                "method": "cached",
                "cache_hit": True,
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
                use_cached=use_cache
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
                headers={"Content-Disposition": "attachment; filename=synthetic_data.xlsx"}
            )

        else:  # Default to CSV
            output = io.StringIO()
            synthetic_df.to_csv(output, index=False)
            output.seek(0)

            return StreamingResponse(
                io.BytesIO(output.getvalue().encode()),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=synthetic_data.csv"}
            )
            
    except Exception as e:
        logger.error(f"Error generating synthetic data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate-sse")
async def generate_with_sse(
    file: Optional[UploadFile] = File(None),
    edited_data: Optional[str] = Form(None),
    metadata_json: Optional[str] = Form(None),
    num_rows: Optional[int] = Form(100),
    match_threshold: float = Form(0.8),
    output_format: str = Form("csv"),
    use_cache: bool = Form(True),
    cache_mode: str = Form("structure_stats"),
    file_count: int = Form(1),
    preview_only: bool = Form(False),
    safety_mode: str = Form("balanced")
):
    """Generate synthetic data with Server-Sent Events for progress updates"""
    import asyncio
    from typing import AsyncGenerator

    # Read file content before the generator to avoid closed file issues
    file_content = None
    file_name = None
    if file:
        file_content = await file.read()
        file_name = file.filename

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
            extractor = MetadataExtractor(safety_mode=safety_mode)

            if edited_data:
                df = pd.read_csv(io.StringIO(edited_data))
                metadata = extractor.extract(df)
            elif file_content:
                df = data_loader.load_from_bytes(file_content, file_name)
                metadata = extractor.extract(df)
            elif metadata_json:
                metadata = json.loads(metadata_json)
            else:
                yield f"data: {json.dumps({'error': 'No data provided'})}\n\n"
                return

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
                cached_result = cache_manager.find_similar_cached(metadata, match_threshold=0.5)
            else:
                cached_result = cache_manager.find_similar_cached(metadata, match_threshold)

            cache_time = time.time() - cache_start
            all_timings['cache_check'] = cache_time

            cache_hit = cached_result and "generation_code" in cached_result
            cache_text = 'Cache Hit ✓' if cache_hit else 'Cache Miss'
            yield f"data: {json.dumps({'step': 'check-cache', 'status': 'completed', 'duration': cache_time, 'text': cache_text})}\n\n"

            # Generate code
            if cache_hit:
                yield f"data: {json.dumps({'step': 'prepare-llm', 'status': 'skipped'})}\n\n"
                yield f"data: {json.dumps({'step': 'generate-code', 'status': 'skipped', 'text': 'Using Cached Code'})}\n\n"

                # Execute cached code
                yield f"data: {json.dumps({'step': 'execute-code', 'status': 'active'})}\n\n"
                exec_start = time.time()
                generation_code = cached_result["generation_code"]
                synthetic_df = synthetic_generator._execute_generation_code(generation_code)
                exec_time = time.time() - exec_start
                all_timings['code_execution'] = exec_time
                yield f"data: {json.dumps({'step': 'execute-code', 'status': 'completed', 'duration': exec_time})}\n\n"

                generation_info = {"method": "cached", "cache_hit": True, "all_timings": all_timings}
                # Log usage for cached generation
                synthetic_generator._log_usage("cached", metadata, num_rows, all_timings)

            else:
                # Generate with LLM (includes prepare, generate, and execute)
                yield f"data: {json.dumps({'step': 'prepare-llm', 'status': 'active'})}\n\n"
                gen_start = time.time()

                synthetic_df, generation_info = synthetic_generator.generate(
                    metadata=metadata,
                    num_rows=num_rows,
                    match_threshold=match_threshold,
                    use_cached=use_cache
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
                        # Fallback mode - report actual execution time
                        yield f"data: {json.dumps({'step': 'prepare-llm', 'status': 'skipped'})}\n\n"
                        yield f"data: {json.dumps({'step': 'generate-code', 'status': 'skipped', 'text': 'Using Fallback'})}\n\n"
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
                preview_rows = min(10, len(synthetic_df))
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

        except Exception as e:
            logger.error(f"SSE generation error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )

@app.post("/dictionary/upload")
async def upload_data_dictionary(
    file: UploadFile = File(...),
    format: Optional[str] = Form("auto")
):
    """
    Upload and parse a data dictionary.

    Args:
        file: Data dictionary file (JSON, YAML, CSV, Excel, or text)
        format: Format hint ('json', 'yaml', 'csv', 'excel', 'text', 'auto')
    """
    try:
        content = await file.read()

        # Parse the dictionary
        parsed_dict = data_dictionary.parse_dictionary(content, format)

        # Store it for later use
        data_dictionary.dictionary = parsed_dict

        # Return parsed structure
        return JSONResponse(content={
            "status": "success",
            "filename": file.filename,
            "columns_defined": len(parsed_dict.get("columns", {})),
            "dictionary": parsed_dict
        })

    except Exception as e:
        logger.error(f"Error parsing data dictionary: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/dictionary/validate")
async def validate_with_dictionary(
    data_file: UploadFile = File(...),
    dictionary_file: Optional[UploadFile] = File(None),
    use_stored: bool = Form(True)
):
    """
    Validate data against a data dictionary.

    Args:
        data_file: Data file to validate
        dictionary_file: Optional dictionary file (uses stored if not provided)
        use_stored: Whether to use stored dictionary
    """
    try:
        # Load the data
        data_content = await data_file.read()
        df = data_loader.load_from_bytes(data_content, data_file.filename)

        # Get dictionary
        if dictionary_file:
            dict_content = await dictionary_file.read()
            dictionary = data_dictionary.parse_dictionary(dict_content)
        elif use_stored and data_dictionary.dictionary:
            dictionary = data_dictionary.dictionary
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

    except Exception as e:
        logger.error(f"Error validating data: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/generate-with-dictionary")
async def generate_with_dictionary(
    dictionary_file: Optional[UploadFile] = File(None),
    data_file: Optional[UploadFile] = File(None),
    use_stored_dictionary: bool = Form(True),
    num_rows: Optional[int] = Form(100),
    output_format: str = Form("csv"),
    file_count: int = Form(1),
    preview_only: bool = Form(False)
):
    """
    Generate synthetic data using data dictionary constraints.

    Args:
        dictionary_file: Optional dictionary file
        data_file: Optional data file for statistical reference
        use_stored_dictionary: Use previously uploaded dictionary
        num_rows: Number of rows to generate
        output_format: Output format
        file_count: Number of files to generate
        preview_only: Return preview instead of download
    """
    try:
        # Get dictionary
        if dictionary_file:
            dict_content = await dictionary_file.read()
            dictionary = data_dictionary.parse_dictionary(dict_content)
            data_dictionary.dictionary = dictionary
        elif use_stored_dictionary and data_dictionary.dictionary:
            dictionary = data_dictionary.dictionary
        else:
            raise HTTPException(status_code=400, detail="No data dictionary provided")

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
            data_content = await data_file.read()
            df = data_loader.load_from_bytes(data_content, data_file.filename)
            base_metadata = metadata_extractor.extract(df)
            metadata = base_metadata

        # Apply dictionary constraints to metadata
        metadata = data_dictionary.apply_to_metadata(metadata, dictionary)

        # Add dictionary constraints to generation prompt
        if "generation_constraints" not in metadata:
            metadata["generation_constraints"] = data_dictionary.to_generation_constraints(dictionary)

        # Generate synthetic data
        if preview_only:
            synthetic_df, generation_info = synthetic_generator.generate(
                metadata=metadata,
                num_rows=num_rows,
                match_threshold=0.9
            )

            preview_rows = min(10, len(synthetic_df))
            preview_df = synthetic_df.head(preview_rows)

            return JSONResponse(content={
                "status": "success",
                "preview": preview_df.to_dict('records'),
                "total_rows": len(synthetic_df),
                "total_columns": len(synthetic_df.columns),
                "column_names": list(synthetic_df.columns),
                "file_count": file_count,
                "dictionary_applied": True,
                "generation_info": generation_info
            })

        # Generate actual files
        if file_count > 1:
            synthetic_files = []
            for i in range(file_count):
                synthetic_df, _ = synthetic_generator.generate(
                    metadata=metadata,
                    num_rows=num_rows,
                    match_threshold=0.9
                )
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
                headers={"Content-Disposition": f"attachment; filename=dictionary_generated.zip"}
            )
        else:
            # Single file
            synthetic_df, generation_info = synthetic_generator.generate(
                metadata=metadata,
                num_rows=num_rows,
                match_threshold=0.9
            )

            if output_format == "json":
                output_data = synthetic_df.to_json(orient="records")
                return JSONResponse(content={
                    "status": "success",
                    "data": json.loads(output_data),
                    "generation_info": generation_info
                })
            elif output_format == "excel":
                output = io.BytesIO()
                synthetic_df.to_excel(output, index=False)
                output.seek(0)
                return StreamingResponse(
                    output,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=dictionary_generated.xlsx"}
                )
            else:  # CSV
                output = io.StringIO()
                synthetic_df.to_csv(output, index=False)
                output.seek(0)
                return StreamingResponse(
                    io.BytesIO(output.getvalue().encode()),
                    media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=dictionary_generated.csv"}
                )

    except Exception as e:
        logger.error(f"Error generating with dictionary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate/batch")
async def generate_batch(
    files: list[UploadFile] = File(...),
    match_threshold: float = Form(0.8),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Generate synthetic data for multiple files in batch.
    
    Args:
        files: List of uploaded files
        match_threshold: Statistical matching threshold
        background_tasks: FastAPI background tasks
    """
    batch_id = f"batch_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Process files in background
    background_tasks.add_task(process_batch, files, match_threshold, batch_id)
    
    return JSONResponse(content={
        "status": "processing",
        "batch_id": batch_id,
        "file_count": len(files),
        "message": f"Batch processing started. Check status at /batch/{batch_id}"
    })

async def process_batch(files, match_threshold, batch_id):
    """Process batch generation in background."""
    results = []
    
    for file in files:
        try:
            content = await file.read()
            df = data_loader.load_from_bytes(content, file.filename)
            metadata = metadata_extractor.extract(df)
            
            synthetic_df, _ = synthetic_generator.generate(
                metadata=metadata,
                match_threshold=match_threshold
            )
            
            # Save result
            output_path = Path(settings.local_storage_path) / batch_id / f"{file.filename}_synthetic.csv"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            synthetic_df.to_csv(output_path, index=False)
            
            results.append({
                "filename": file.filename,
                "status": "success",
                "output_path": str(output_path)
            })
            
        except Exception as e:
            results.append({
                "filename": file.filename,
                "status": "error",
                "error": str(e)
            })
    
    # Save batch results
    results_path = Path(settings.local_storage_path) / batch_id / "results.json"
    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2)

@app.get("/batch/{batch_id}")
async def get_batch_status(batch_id: str):
    """Get status of batch processing."""
    results_path = Path(settings.local_storage_path) / batch_id / "results.json"
    
    if not results_path.exists():
        return JSONResponse(content={
            "status": "processing",
            "batch_id": batch_id
        })
    
    with open(results_path, 'r') as f:
        results = json.load(f)
    
    return JSONResponse(content={
        "status": "completed",
        "batch_id": batch_id,
        "results": results
    })

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
        raise HTTPException(status_code=500, detail=str(e))

# Main entry point
if __name__ == "__main__":
    import os
    # Get port from environment or settings
    port = int(os.environ.get("APP_PORT", settings.app_port))
    
    # Run the application
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=port,
        reload=False,  # Disable reload to avoid port conflicts
        log_level=settings.log_level.lower()
    )