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
from src.utils.config import settings
from src.utils.logger import logger

# Initialize components
data_loader = DataLoader()
metadata_extractor = MetadataExtractor()
cache_manager = CacheManager()

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

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    """Serve the about page."""
    html_file = Path(__file__).parent / "src" / "web" / "about.html"
    if html_file.exists():
        with open(html_file, 'r') as f:
            content = f.read()
        return HTMLResponse(content=content)
    else:
        return HTMLResponse(content="<h1>About page not found</h1>")

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
    file_count: int = Form(1)
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