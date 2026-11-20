"""Caching and hashing functionality for synthetic data generation."""

import hashlib
import hmac
import json
import pickle
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
from datetime import datetime

from src.utils.logger import logger
from src.utils.config import settings


# Variant used for a description that carries no privacy mode of the server's own
# (client-supplied metadata, dictionary-only requests): it never shares entries with
# descriptions the server extracted from a file.
UNSTAMPED_PRIVACY_MODE = "client"


def cache_variant(metadata: Dict[str, Any], model: Optional[str]) -> str:
    """What a cached script was written by and from: the model and the privacy mode
    of the description (``MetadataExtractor.extract`` stamps ``privacy_mode``).

    A script is only reused for a request with the same variant: another model may
    write different code, and a script written from a "permissive" description can
    embed real category labels that a "strict" request must not receive.
    """
    mode = metadata.get("privacy_mode") if isinstance(metadata, dict) else None
    if not isinstance(mode, str) or not mode:
        return f"{model or ''}|{UNSTAMPED_PRIVACY_MODE}"
    # The stamped text exactly as the extractor used it (it compares modes exactly, so
    # "Strict" is not "strict"), prefixed so no stamped value can equal the unstamped one.
    return f"{model or ''}|server:{mode}"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class CacheManager:
    """Manage caching of generation scripts and metadata."""
    
    def __init__(self, cache_dir: Optional[Path] = None, persist_removals: bool = True):
        """
        Initialize the CacheManager.
        
        Args:
            cache_dir: Directory for cache storage
            persist_removals: When a lookup drops an entry (script altered or missing),
                also delete its files and save the index. False for a second object
                on the same folder, whose older index copy must not be written back.
        """
        self.logger = logger
        self.persist_removals = persist_removals
        self.cache_dir = Path(cache_dir or settings.local_cache_path)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize cache index
        self.index_file = self.cache_dir / "cache_index.json"
        self.cache_index = self._load_cache_index()
        
    def _load_cache_index(self) -> Dict[str, Any]:
        """Load the cache index, creating an empty one if it does not exist.

        Entries read here (their variant and script hash included) are only as
        trustworthy as the index file itself: the hash check in find_similar_cached
        catches a script altered after it was cached, not an altered index file.
        """
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"Error loading cache index: {e}")
                return {}

        # Write the empty index now so the cache directory is self-describing
        # and a later crash cannot leave a cache with no index at all.
        try:
            with open(self.index_file, 'w') as f:
                json.dump({}, f)
        except Exception as e:
            self.logger.error(f"Error creating cache index: {e}")
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
        match_threshold: float = 0.8,
        num_rows: Optional[int] = None,
        variant: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Find similar cached generation script based on metadata.
        
        Args:
            metadata: Metadata dictionary
            match_threshold: Similarity threshold (0-1)
            num_rows: Rows wanted. A script writes a fixed number of rows, so entries
                recorded for a different count are skipped (entries with no recorded
                count are still offered; the caller checks the result's length)
            variant: ``cache_variant(metadata, model)`` of this request. Only entries
                recorded with the same variant are offered. An entry with no variant
                recorded never matches, and a lookup with no variant matches nothing.
            
        Returns:
            Cached entry if found (with the ``model`` that wrote it), None otherwise
        """
        format_hash = self.generate_format_hash(metadata)
        candidates = [
            e for e in self.cache_index.get(format_hash, [])
            if variant and e.get("variant") == variant
            and (num_rows is None or e.get("num_rows") in (None, num_rows))
        ]

        if candidates:
            ordered: List[Tuple[str, Dict[str, Any]]] = []

            if match_threshold >= 0.95:
                # Try full hash for exact match
                full_hash = self.generate_full_hash(metadata)
                ordered.extend(
                    (f"exact cache match: {full_hash}", e)
                    for e in candidates if e.get("full_hash") == full_hash)

            # Calculate similarity for format matches, best first
            current_embedding = self.generate_metadata_embedding(metadata)
            similar = []
            for entry in candidates:
                if entry.get("embedding_file"):
                    try:
                        cached_embedding = self._load_embedding(entry["embedding_file"])
                    except (OSError, ValueError):
                        continue
                    similarity = self._calculate_similarity(current_embedding, cached_embedding)
                    if similarity >= match_threshold:
                        similar.append((similarity, entry))
            similar.sort(key=lambda pair: pair[0], reverse=True)
            ordered.extend((f"similar cache match with similarity: {sim:.2f}", e) for sim, e in similar)

            for description, entry in ordered:
                loaded = self._load_verified(entry)
                if loaded is not None:
                    self.logger.info(f"Found {description}")
                    return loaded

        self.logger.info("No suitable cache match found")
        return None

    def _load_verified(self, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Load an entry's script only if it is still the text that was cached.

        The cache folder is writable by the service user, so a script file could be
        altered after it was cached. The SHA-256 recorded in the index entry is checked
        here; a missing hash, a missing or unreadable file, or a mismatch drops the
        entry and counts as a miss.
        """
        cache_file = entry.get("cache_file") or ""
        try:
            loaded = self._load_cached_entry(cache_file)
            intact = bool(entry.get("code_sha256")) and hmac.compare_digest(
                _sha256(loaded["generation_code"]), str(entry["code_sha256"]))
        except (OSError, ValueError):
            loaded, intact = None, False
        if not intact:
            self.logger.warning("Cached script is missing or was changed after it was cached; dropping it")
            self.remove_entry(cache_file, save=self.persist_removals)
            return None
        loaded["model"] = entry.get("model")
        loaded["variant"] = entry.get("variant")
        return loaded
    
    def cache_generation(
        self, 
        metadata: Dict[str, Any], 
        generation_code: str,
        synthetic_data: Any = None,
        num_rows: Optional[int] = None,
        variant: Optional[str] = None,
        model: Optional[str] = None
    ) -> str:
        """
        Cache a generation script with its metadata.
        
        Args:
            metadata: Metadata dictionary
            generation_code: Python code for generation
            synthetic_data: Optional synthetic data to cache
            num_rows: Row count the script writes
            variant: ``cache_variant(metadata, model)``; an entry cached without one
                is never served
            model: The model that wrote the script (reported on a cache hit)
            
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
        # newline='' on write and read: the text read back is exactly the text hashed.
        with open(code_file, 'w', newline='') as f:
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
            "num_rows": num_rows,
            "variant": variant,
            "model": model,
            # Checked when the script is loaded for reuse (see _load_verified).
            "code_sha256": _sha256(generation_code),
            "version": settings.generator_version
        })
        
        self._save_cache_index()
        
        self.logger.info(f"Cached generation with key: {cache_key}")
        return cache_key
    
    def remove_entry(self, cache_file: str, save: bool = True) -> bool:
        """Remove one cached script (index entry and its files), e.g. code that failed to run.

        Returns True if an entry was removed. ``save=False`` only updates this
        instance's in-memory index.
        """
        removed = False
        for format_hash in list(self.cache_index):
            kept = []
            for entry in self.cache_index[format_hash]:
                if entry.get("cache_file") != str(cache_file):
                    kept.append(entry)
                    continue
                removed = True
                if save:
                    for key in ("cache_file", "metadata_file", "embedding_file", "data_file"):
                        if entry.get(key):
                            Path(entry[key]).unlink(missing_ok=True)
            if kept:
                self.cache_index[format_hash] = kept
            else:
                del self.cache_index[format_hash]
        if removed and save:
            self._save_cache_index()
        return removed

    def _load_cached_entry(self, cache_file: str) -> Dict[str, Any]:
        """Load a cached entry."""
        cache_file = Path(cache_file)
        
        # Load generation code
        with open(cache_file, 'r', newline='') as f:
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