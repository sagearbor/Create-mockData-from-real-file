#!/usr/bin/env python3
"""Quick test script to verify the application starts correctly."""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")
    try:
        from src.utils.config import settings
        print("✓ Config module loaded")
        
        from src.utils.logger import logger
        print("✓ Logger module loaded")
        
        from src.core.data_loader import DataLoader
        print("✓ DataLoader module loaded")
        
        from src.core.metadata_extractor import MetadataExtractor
        print("✓ MetadataExtractor module loaded")
        
        from src.core.synthetic_generator import SyntheticDataGenerator
        print("✓ SyntheticGenerator module loaded")
        
        from src.core.cache_manager import CacheManager
        print("✓ CacheManager module loaded")
        
        print("\n✅ All modules imported successfully!\n")
        return True
    except Exception as e:
        print(f"\n❌ Import error: {e}\n")
        return False

def start_server():
    """Start the FastAPI server."""
    print("Starting FastAPI server...")
    print("-" * 50)
    print("Web Interface: http://localhost:8201")
    print("API Docs:      http://localhost:8201/docs")
    print("Health Check:  http://localhost:8201/health")
    print("-" * 50)
    print("\nPress Ctrl+C to stop the server\n")
    
    # Import and run the main app
    from main import app
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8201,
        log_level="info"
    )

if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("BYOD Synthetic Data Generator - Test Run")
    print("=" * 50 + "\n")
    
    if test_imports():
        start_server()
    else:
        print("Please fix import errors before starting the server.")
        sys.exit(1)