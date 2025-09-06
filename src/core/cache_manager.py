"""Caching and hashing functionality for synthetic data generation."""

import hashlib
import json
import pickle
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
from datetime import datetime

from src.utils.logger import logger
from src.utils.config import settings


class CacheManager:
    """Manage caching of generation scripts and metadata."""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize the CacheManager.
        
        Args:
            cache_dir: Directory for cache storage
        """
        self.logger = logger
        self.cache_dir = Path(cache_dir or settings.local_cache_path)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize cache index
        self.index_file = self.cache_dir / "cache_index.json"
        self.cache_index = self._load_cache_index()
        
    def _load_cache_index(self) -> Dict[str, Any]:
        """Load or create cache index."""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"Error loading cache index: {e}")
                return {}
        return {}
    
    def _save_cache_index(self):
        """Save cache index to disk."""
        try:
            with open(self.index_file, 'w') as f:
                json.dump(self.cache_index, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Error saving cache index: {e}")
    
    def generate_format_hash(self, metadata: Dict[str, Any]) -> str:
        """
        Generate hash based on structural metadata only.
        
        Args:
            metadata: Metadata dictionary
            
        Returns:
            Format hash string
        """
        # Extract only structural information
        format_data = {
            "columns": [
                {
                    "name": col["name"],
                    "dtype": col["dtype"],
                    "python_type": col.get("python_type", "unknown")
                }
                for col in metadata["structure"]["columns"]
            ],
            "shape": metadata["structure"]["shape"]["columns"],
            "version": settings.generator_version
        }
        
        # Create deterministic JSON string
        format_json = json.dumps(format_data, sort_keys=True)
        
        # Generate SHA256 hash
        hash_obj = hashlib.sha256(format_json.encode())
        return f"format_{hash_obj.hexdigest()[:16]}"
    
    def generate_full_hash(self, metadata: Dict[str, Any]) -> str:
        """
        Generate hash based on complete metadata.
        
        Args:
            metadata: Metadata dictionary
            
        Returns:
            Full hash string
        """
        # Remove timestamp for consistent hashing
        metadata_copy = json.loads(json.dumps(metadata, default=str))
        metadata_copy.pop("extraction_timestamp", None)
        
        # Add version
        metadata_copy["version"] = settings.generator_version
        
        # Create deterministic JSON string
        full_json = json.dumps(metadata_copy, sort_keys=True)
        
        # Generate SHA256 hash
        hash_obj = hashlib.sha256(full_json.encode())
        return f"full_{hash_obj.hexdigest()[:16]}"
    
    def generate_metadata_embedding(self, metadata: Dict[str, Any]) -> np.ndarray:
        """
        Generate embedding vector for metadata (placeholder for actual embedding).
        
        Args:
            metadata: Metadata dictionary
            
        Returns:
            Embedding vector
        """
        # This is a simplified version - in production, use actual embedding model
        # For now, create a simple vector based on metadata characteristics
        
        features = []
        
        # Structure features
        features.append(metadata["structure"]["shape"]["rows"])
        features.append(metadata["structure"]["shape"]["columns"])
        
        # Statistical features for each column
        for col_stats in metadata["statistics"].values():
            if col_stats.get("type") == "numeric":
                features.extend([
                    col_stats.get("mean", 0),
                    col_stats.get("std", 0),
                    col_stats.get("min", 0),
                    col_stats.get("max", 0)
                ])
            elif col_stats.get("type") == "string":
                features.extend([
                    col_stats.get("unique_values", 0),
                    col_stats.get("avg_length", 0),
                    1 if col_stats.get("is_categorical", False) else 0
                ])
            else:
                features.extend([0, 0, 0])
        
        # Pad or truncate to fixed size
        embedding_size = 128
        if len(features) < embedding_size:
            features.extend([0] * (embedding_size - len(features)))
        else:
            features = features[:embedding_size]
        
        return np.array(features, dtype=np.float32)
    
    def find_similar_cached(
        self, 
        metadata: Dict[str, Any], 
        match_threshold: float = 0.8
    ) -> Optional[Dict[str, Any]]:
        """
        Find similar cached generation script based on metadata.
        
        Args:
            metadata: Metadata dictionary
            match_threshold: Similarity threshold (0-1)
            
        Returns:
            Cached entry if found, None otherwise
        """
        # First, try exact format match
        format_hash = self.generate_format_hash(metadata)
        if format_hash in self.cache_index:
            exact_matches = self.cache_index[format_hash]
            
            if match_threshold >= 0.95:
                # Try full hash for exact match
                full_hash = self.generate_full_hash(metadata)
                for entry in exact_matches:
                    if entry.get("full_hash") == full_hash:
                        self.logger.info(f"Found exact cache match: {full_hash}")
                        return self._load_cached_entry(entry["cache_file"])
            
            # Calculate similarity for format matches
            current_embedding = self.generate_metadata_embedding(metadata)
            
            best_match = None
            best_similarity = 0
            
            for entry in exact_matches:
                if "embedding_file" in entry:
                    cached_embedding = self._load_embedding(entry["embedding_file"])
                    similarity = self._calculate_similarity(current_embedding, cached_embedding)
                    
                    if similarity >= match_threshold and similarity > best_similarity:
                        best_similarity = similarity
                        best_match = entry
            
            if best_match:
                self.logger.info(f"Found similar cache match with similarity: {best_similarity:.2f}")
                return self._load_cached_entry(best_match["cache_file"])
        
        self.logger.info("No suitable cache match found")
        return None
    
    def cache_generation(
        self, 
        metadata: Dict[str, Any], 
        generation_code: str,
        synthetic_data: Any = None
    ) -> str:
        """
        Cache a generation script with its metadata.
        
        Args:
            metadata: Metadata dictionary
            generation_code: Python code for generation
            synthetic_data: Optional synthetic data to cache
            
        Returns:
            Cache key
        """
        format_hash = self.generate_format_hash(metadata)
        full_hash = self.generate_full_hash(metadata)
        embedding = self.generate_metadata_embedding(metadata)
        
        # Create cache entry
        timestamp = datetime.now().isoformat()
        cache_key = f"{format_hash}_{full_hash}_{timestamp.replace(':', '-')}"
        
        # Save generation code
        code_file = self.cache_dir / f"{cache_key}_code.py"
        with open(code_file, 'w') as f:
            f.write(generation_code)
        
        # Save metadata
        metadata_file = self.cache_dir / f"{cache_key}_metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2, default=str)
        
        # Save embedding
        embedding_file = self.cache_dir / f"{cache_key}_embedding.npy"
        np.save(embedding_file, embedding)
        
        # Save synthetic data if provided
        data_file = None
        if synthetic_data is not None:
            data_file = self.cache_dir / f"{cache_key}_data.pkl"
            with open(data_file, 'wb') as f:
                pickle.dump(synthetic_data, f)
        
        # Update cache index
        if format_hash not in self.cache_index:
            self.cache_index[format_hash] = []
        
        self.cache_index[format_hash].append({
            "cache_key": cache_key,
            "full_hash": full_hash,
            "cache_file": str(code_file),
            "metadata_file": str(metadata_file),
            "embedding_file": str(embedding_file),
            "data_file": str(data_file) if data_file else None,
            "timestamp": timestamp,
            "version": settings.generator_version
        })
        
        self._save_cache_index()
        
        self.logger.info(f"Cached generation with key: {cache_key}")
        return cache_key
    
    def _load_cached_entry(self, cache_file: str) -> Dict[str, Any]:
        """Load a cached entry."""
        cache_file = Path(cache_file)
        
        # Load generation code
        with open(cache_file, 'r') as f:
            generation_code = f.read()
        
        # Load metadata if exists
        metadata_file = cache_file.with_suffix('').parent / f"{cache_file.stem.replace('_code', '_metadata')}.json"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
        else:
            metadata = None
        
        return {
            "generation_code": generation_code,
            "metadata": metadata,
            "cache_file": str(cache_file)
        }
    
    def _load_embedding(self, embedding_file: str) -> np.ndarray:
        """Load an embedding from file."""
        return np.load(embedding_file)
    
    def _calculate_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Calculate cosine similarity between two embeddings.
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Similarity score (0-1)
        """
        # Normalize vectors
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        embedding1_norm = embedding1 / norm1
        embedding2_norm = embedding2 / norm2
        
        # Calculate cosine similarity
        similarity = np.dot(embedding1_norm, embedding2_norm)
        
        # Ensure it's in [0, 1] range
        return (similarity + 1) / 2
    
    def clear_cache(self, older_than_days: Optional[int] = None):
        """
        Clear cache entries.
        
        Args:
            older_than_days: Clear entries older than specified days
        """
        if older_than_days is None:
            # Clear all cache
            for file in self.cache_dir.glob("*"):
                if file.name != "cache_index.json":
                    file.unlink()
            self.cache_index = {}
            self._save_cache_index()
            self.logger.info("Cleared all cache")
        else:
            # Clear old entries
            from datetime import datetime, timedelta
            cutoff_date = datetime.now() - timedelta(days=older_than_days)
            
            updated_index = {}
            for format_hash, entries in self.cache_index.items():
                filtered_entries = []
                for entry in entries:
                    entry_date = datetime.fromisoformat(entry["timestamp"])
                    if entry_date > cutoff_date:
                        filtered_entries.append(entry)
                    else:
                        # Delete associated files
                        for key in ["cache_file", "metadata_file", "embedding_file", "data_file"]:
                            if entry.get(key):
                                file_path = Path(entry[key])
                                if file_path.exists():
                                    file_path.unlink()
                
                if filtered_entries:
                    updated_index[format_hash] = filtered_entries
            
            self.cache_index = updated_index
            self._save_cache_index()
            self.logger.info(f"Cleared cache entries older than {older_than_days} days")