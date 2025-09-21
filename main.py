"""Main FastAPI application for BYOD Synthetic Data Generator."""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import json
import io

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
metadata_extractor = MetadataExtractor()
cache_manager = CacheManager()
data_dictionary = DataDictionary()

# Initialize synthetic generator (OpenAI client will be added when API key is provided)
synthetic_generator = None

def initialize_openai_client():
    """Initialize OpenAI client if credentials are available."""
    global synthetic_generator
    
    if settings.azure_openai_api_key and settings.azure_openai_endpoint:
        try:
            from openai import AzureOpenAI
            
            client = AzureOpenAI(
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version,
                azure_endpoint=settings.azure_openai_endpoint
            )
            
            synthetic_generator = SyntheticDataGenerator(openai_client=client)
            logger.info("OpenAI client initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            synthetic_generator = SyntheticDataGenerator()
            return False
    else:
        logger.warning("OpenAI credentials not configured, using fallback generation")
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
        
        # Extract metadata
        metadata = metadata_extractor.extract(df)
        
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
        metadata = metadata_extractor.extract(df)
        
        # Convert to secure JSON
        secure_metadata = metadata_extractor.to_secure_json(metadata)
        
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
    file_count: int = Form(1),
    preview_only: bool = Form(False)
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
        # Get metadata from edited data, file, or JSON
        if edited_data:
            # Parse edited CSV data
            df = pd.read_csv(io.StringIO(edited_data))
            metadata = metadata_extractor.extract(df)
        elif file:
            content = await file.read()
            df = data_loader.load_from_bytes(content, file.filename)
            metadata = metadata_extractor.extract(df)
        elif metadata_json:
            metadata = json.loads(metadata_json)
        else:
            raise HTTPException(status_code=400, detail="Either file or metadata_json must be provided")
        
        # Check cache if enabled
        cached_result = None
        if use_cache:
            cached_result = cache_manager.find_similar_cached(metadata, match_threshold)
        
        # If preview only, generate single file and return preview data
        if preview_only:
            # Generate single synthetic dataset
            if cached_result and "generation_code" in cached_result:
                logger.info("Using cached generation script for preview")
                generation_code = cached_result["generation_code"]
                synthetic_df = synthetic_generator._execute_generation_code(generation_code)
            else:
                synthetic_df = synthetic_generator.generate(
                    metadata=metadata,
                    num_rows=num_rows,
                    match_threshold=match_threshold,
                    use_cached=use_cache
                )

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
                        additional_df = synthetic_generator.generate(
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
                "download_info": download_data
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
                    synthetic_df = synthetic_generator.generate(
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
            generation_code = cached_result["generation_code"]
            synthetic_df = synthetic_generator._execute_generation_code(generation_code)
        else:
            # Generate new synthetic data
            synthetic_df = synthetic_generator.generate(
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
                "columns": list(synthetic_df.columns)
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
            synthetic_df = synthetic_generator.generate(
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
                "dictionary_applied": True
            })

        # Generate actual files
        if file_count > 1:
            synthetic_files = []
            for i in range(file_count):
                synthetic_df = synthetic_generator.generate(
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
            synthetic_df = synthetic_generator.generate(
                metadata=metadata,
                num_rows=num_rows,
                match_threshold=0.9
            )

            if output_format == "json":
                output_data = synthetic_df.to_json(orient="records")
                return JSONResponse(content={
                    "status": "success",
                    "data": json.loads(output_data)
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
            
            synthetic_df = synthetic_generator.generate(
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