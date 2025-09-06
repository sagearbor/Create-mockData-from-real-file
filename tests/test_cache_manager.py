"""Unit tests for the CacheManager module."""

import pytest
import json
import numpy as np
import tempfile
from pathlib import Path
import shutil
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.cache_manager import CacheManager


class TestCacheManager:
    """Test suite for CacheManager class."""
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary directory for cache testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def cache_manager(self, temp_cache_dir):
        """Create a CacheManager instance with temp directory."""
        return CacheManager(cache_dir=temp_cache_dir)
    
    @pytest.fixture
    def sample_metadata(self):
        """Create sample metadata for testing."""
        return {
            "structure": {
                "shape": {"rows": 100, "columns": 5},
                "columns": [
                    {"name": "id", "dtype": "int64", "python_type": "int"},
                    {"name": "name", "dtype": "object", "python_type": "str"},
                    {"name": "value", "dtype": "float64", "python_type": "float"}
                ]
            },
            "statistics": {
                "id": {"type": "numeric", "mean": 50, "std": 10},
                "name": {"type": "string", "unique_values": 100},
                "value": {"type": "numeric", "mean": 100, "std": 20}
            }
        }
    
    def test_cache_manager_initialization(self, cache_manager, temp_cache_dir):
        """Test CacheManager initialization."""
        assert cache_manager.cache_dir == Path(temp_cache_dir)
        assert cache_manager.index_file.exists()
        assert isinstance(cache_manager.cache_index, dict)
    
    def test_generate_format_hash(self, cache_manager, sample_metadata):
        """Test format hash generation."""
        hash1 = cache_manager.generate_format_hash(sample_metadata)
        hash2 = cache_manager.generate_format_hash(sample_metadata)
        
        # Same metadata should produce same hash
        assert hash1 == hash2
        assert hash1.startswith("format_")
        assert len(hash1) > 10
        
        # Different structure should produce different hash
        modified_metadata = sample_metadata.copy()
        modified_metadata["structure"]["columns"].append(
            {"name": "extra", "dtype": "int64", "python_type": "int"}
        )
        hash3 = cache_manager.generate_format_hash(modified_metadata)
        assert hash1 != hash3
    
    def test_generate_full_hash(self, cache_manager, sample_metadata):
        """Test full hash generation."""
        hash1 = cache_manager.generate_full_hash(sample_metadata)
        hash2 = cache_manager.generate_full_hash(sample_metadata)
        
        # Same metadata should produce same hash
        assert hash1 == hash2
        assert hash1.startswith("full_")
        
        # Different statistics should produce different hash
        modified_metadata = sample_metadata.copy()
        modified_metadata["statistics"]["id"]["mean"] = 60
        hash3 = cache_manager.generate_full_hash(modified_metadata)
        assert hash1 != hash3
    
    def test_generate_metadata_embedding(self, cache_manager, sample_metadata):
        """Test metadata embedding generation."""
        embedding = cache_manager.generate_metadata_embedding(sample_metadata)
        
        assert isinstance(embedding, np.ndarray)
        assert embedding.dtype == np.float32
        assert len(embedding) == 128  # Fixed size
        
        # Same metadata should produce same embedding
        embedding2 = cache_manager.generate_metadata_embedding(sample_metadata)
        np.testing.assert_array_equal(embedding, embedding2)
    
    def test_calculate_similarity(self, cache_manager):
        """Test similarity calculation between embeddings."""
        # Identical vectors
        vec1 = np.array([1, 0, 0, 0])
        similarity = cache_manager._calculate_similarity(vec1, vec1)
        assert similarity == 1.0
        
        # Orthogonal vectors
        vec2 = np.array([0, 1, 0, 0])
        similarity = cache_manager._calculate_similarity(vec1, vec2)
        assert 0.4 < similarity < 0.6  # Should be around 0.5
        
        # Zero vectors
        vec3 = np.array([0, 0, 0, 0])
        similarity = cache_manager._calculate_similarity(vec3, vec1)
        assert similarity == 0.0
    
    def test_cache_generation(self, cache_manager, sample_metadata):
        """Test caching a generation script."""
        generation_code = "def generate_synthetic_data():\n    return pd.DataFrame()"
        
        cache_key = cache_manager.cache_generation(
            metadata=sample_metadata,
            generation_code=generation_code
        )
        
        assert cache_key is not None
        assert len(cache_key) > 0
        
        # Check that files were created
        format_hash = cache_manager.generate_format_hash(sample_metadata)
        assert format_hash in cache_manager.cache_index
        
        # Check cache entry
        entries = cache_manager.cache_index[format_hash]
        assert len(entries) == 1
        assert entries[0]["cache_key"] == cache_key
        
        # Check that files exist
        code_file = Path(entries[0]["cache_file"])
        assert code_file.exists()
        
        metadata_file = Path(entries[0]["metadata_file"])
        assert metadata_file.exists()
        
        embedding_file = Path(entries[0]["embedding_file"])
        assert embedding_file.exists()
    
    def test_find_similar_cached_exact_match(self, cache_manager, sample_metadata):
        """Test finding exact cache match."""
        generation_code = "def generate(): pass"
        
        # Cache the generation
        cache_manager.cache_generation(sample_metadata, generation_code)
        
        # Find with high threshold (exact match)
        result = cache_manager.find_similar_cached(sample_metadata, match_threshold=0.95)
        
        assert result is not None
        assert result["generation_code"] == generation_code
    
    def test_find_similar_cached_no_match(self, cache_manager, sample_metadata):
        """Test when no cache match exists."""
        result = cache_manager.find_similar_cached(sample_metadata)
        assert result is None
    
    def test_find_similar_cached_similar_match(self, cache_manager, sample_metadata):
        """Test finding similar (not exact) cache match."""
        generation_code = "def generate(): pass"
        
        # Cache the generation
        cache_manager.cache_generation(sample_metadata, generation_code)
        
        # Modify metadata slightly
        modified_metadata = sample_metadata.copy()
        modified_metadata["statistics"]["id"]["mean"] = 51  # Small change
        
        # Find with lower threshold
        result = cache_manager.find_similar_cached(modified_metadata, match_threshold=0.7)
        
        # Should find similar match if format is same
        if cache_manager.generate_format_hash(sample_metadata) == cache_manager.generate_format_hash(modified_metadata):
            assert result is not None
    
    def test_load_cached_entry(self, cache_manager, sample_metadata):
        """Test loading a cached entry."""
        generation_code = "def generate(): return 'test'"
        
        # Cache the generation
        cache_manager.cache_generation(sample_metadata, generation_code)
        
        # Get the cache file path
        format_hash = cache_manager.generate_format_hash(sample_metadata)
        entry = cache_manager.cache_index[format_hash][0]
        
        # Load the cached entry
        loaded = cache_manager._load_cached_entry(entry["cache_file"])
        
        assert loaded["generation_code"] == generation_code
        assert loaded["metadata"] is not None
    
    def test_clear_cache_all(self, cache_manager, sample_metadata):
        """Test clearing all cache."""
        # Add some cache entries
        cache_manager.cache_generation(sample_metadata, "code1")
        cache_manager.cache_generation(sample_metadata, "code2")
        
        assert len(cache_manager.cache_index) > 0
        
        # Clear all cache
        cache_manager.clear_cache()
        
        assert len(cache_manager.cache_index) == 0
        assert cache_manager.index_file.exists()
        
        # Check that cache files are deleted
        cache_files = list(cache_manager.cache_dir.glob("*.py"))
        assert len(cache_files) == 0
    
    def test_clear_cache_old_entries(self, cache_manager, sample_metadata):
        """Test clearing old cache entries."""
        from datetime import datetime, timedelta
        
        # Cache an entry
        cache_manager.cache_generation(sample_metadata, "recent_code")
        
        # Manually modify timestamp of first entry to be old
        format_hash = cache_manager.generate_format_hash(sample_metadata)
        old_timestamp = (datetime.now() - timedelta(days=10)).isoformat()
        cache_manager.cache_index[format_hash][0]["timestamp"] = old_timestamp
        cache_manager._save_cache_index()
        
        # Add another recent entry
        modified_metadata = sample_metadata.copy()
        modified_metadata["structure"]["shape"]["rows"] = 200
        cache_manager.cache_generation(modified_metadata, "new_code")
        
        initial_count = sum(len(entries) for entries in cache_manager.cache_index.values())
        
        # Clear entries older than 5 days
        cache_manager.clear_cache(older_than_days=5)
        
        final_count = sum(len(entries) for entries in cache_manager.cache_index.values())
        assert final_count < initial_count
    
    def test_cache_index_persistence(self, temp_cache_dir):
        """Test that cache index persists between instances."""
        metadata = {
            "structure": {
                "shape": {"rows": 10, "columns": 2},
                "columns": [
                    {"name": "a", "dtype": "int64", "python_type": "int"}
                ]
            },
            "statistics": {}
        }
        
        # Create first instance and cache something
        cm1 = CacheManager(cache_dir=temp_cache_dir)
        cache_key = cm1.cache_generation(metadata, "test_code")
        
        # Create second instance and check index is loaded
        cm2 = CacheManager(cache_dir=temp_cache_dir)
        format_hash = cm2.generate_format_hash(metadata)
        
        assert format_hash in cm2.cache_index
        assert cm2.cache_index[format_hash][0]["cache_key"] == cache_key