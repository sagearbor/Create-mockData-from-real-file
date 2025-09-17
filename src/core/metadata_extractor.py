"""Extract comprehensive metadata from DataFrames for synthetic data generation."""

import pandas as pd
import numpy as np
import re
import json
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from src.utils.logger import logger
from src.core.clinical_reference import ClinicalReferenceLibrary


class MetadataExtractor:
    """Extract statistical and structural metadata from pandas DataFrames."""
    
    def __init__(self, use_clinical_reference: bool = True):
        """
        Initialize the MetadataExtractor.

        Args:
            use_clinical_reference: Whether to use clinical reference library for medical data
        """
        self.logger = logger
        self.clinical_reference = ClinicalReferenceLibrary() if use_clinical_reference else None
        
    def extract(self, df: pd.DataFrame, sample_size: int = 1000) -> Dict[str, Any]:
        """
        Extract comprehensive metadata from a DataFrame.
        
        Args:
            df: Input DataFrame
            sample_size: Number of rows to sample for pattern analysis
            
        Returns:
            Dictionary containing all metadata
        """
        self.logger.info(f"Extracting metadata from DataFrame with shape {df.shape}")
        
        metadata = {
            "structure": self._extract_structural_metadata(df),
            "statistics": self._extract_statistical_metadata(df),
            "patterns": self._extract_patterns(df, sample_size),
            "correlations": self._extract_correlations(df),
            "data_quality": self._extract_data_quality(df),
            "metadata_version": "1.0",
            "extraction_timestamp": datetime.now().isoformat()
        }

        # Enhance with clinical context if available
        if self.clinical_reference:
            metadata = self.clinical_reference.enhance_metadata_with_clinical_context(metadata)

        self.logger.info("Metadata extraction complete")
        return metadata
    
    def _extract_structural_metadata(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Extract structural information about the DataFrame."""
        return {
            "shape": {
                "rows": len(df),
                "columns": len(df.columns)
            },
            "columns": [
                {
                    "name": col,
                    "dtype": str(df[col].dtype),
                    "python_type": self._get_python_type(df[col]),
                    "nullable": bool(df[col].isna().any()),
                    "unique_count": int(df[col].nunique()),
                    "null_count": int(df[col].isna().sum())
                }
                for col in df.columns
            ],
            "memory_usage": int(df.memory_usage(deep=True).sum()),
            "index_dtype": str(df.index.dtype)
        }
    
    def _extract_statistical_metadata(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Extract statistical properties for each column."""
        stats = {}
        
        for col in df.columns:
            col_stats = {
                "name": col,
                "non_null_count": int(df[col].count()),
                "null_percentage": float(df[col].isna().mean() * 100)
            }
            
            # Numeric columns
            if pd.api.types.is_numeric_dtype(df[col]):
                col_stats.update(self._extract_numeric_stats(df[col]))
            
            # DateTime columns
            elif pd.api.types.is_datetime64_any_dtype(df[col]):
                col_stats.update(self._extract_datetime_stats(df[col]))
            
            # String/Object columns
            else:
                col_stats.update(self._extract_string_stats(df[col]))
            
            stats[col] = col_stats
        
        return stats
    
    def _extract_numeric_stats(self, series: pd.Series) -> Dict[str, Any]:
        """Extract statistics for numeric columns."""
        # Remove NaN values for calculation
        clean_series = series.dropna()
        
        if len(clean_series) == 0:
            return {"type": "numeric", "all_null": True}
        
        # Calculate stats with proper handling for small samples
        try:
            std_val = float(clean_series.std()) if len(clean_series) > 1 else 0.0
        except:
            std_val = 0.0
            
        try:
            skew_val = float(clean_series.skew()) if len(clean_series) > 2 else 0.0
        except:
            skew_val = 0.0
            
        try:
            kurt_val = float(clean_series.kurtosis()) if len(clean_series) > 3 else 0.0
        except:
            kurt_val = 0.0
        
        stats = {
            "type": "numeric",
            "mean": float(clean_series.mean()),
            "median": float(clean_series.median()),
            "std": std_val,
            "min": float(clean_series.min()),
            "max": float(clean_series.max()),
            "q25": float(clean_series.quantile(0.25)),
            "q75": float(clean_series.quantile(0.75)),
            "skewness": skew_val,
            "kurtosis": kurt_val,
            "is_integer": bool(pd.api.types.is_integer_dtype(series) or 
                              (clean_series == clean_series.astype(int)).all()),
            "has_negative": bool((clean_series < 0).any()),
            "has_zero": bool((clean_series == 0).any())
        }
        
        # Check if it might be a percentage (values between 0 and 1 or 0 and 100)
        if stats["min"] >= 0:
            if stats["max"] <= 1:
                stats["might_be_percentage"] = "decimal"
            elif stats["max"] <= 100:
                stats["might_be_percentage"] = "whole"
        
        return stats
    
    def _extract_datetime_stats(self, series: pd.Series) -> Dict[str, Any]:
        """Extract statistics for datetime columns."""
        clean_series = series.dropna()
        
        if len(clean_series) == 0:
            return {"type": "datetime", "all_null": True}
        
        return {
            "type": "datetime",
            "min": clean_series.min().isoformat() if pd.notna(clean_series.min()) else None,
            "max": clean_series.max().isoformat() if pd.notna(clean_series.max()) else None,
            "range_days": (clean_series.max() - clean_series.min()).days if len(clean_series) > 0 else 0,
            "most_common_hour": int(pd.to_datetime(clean_series).dt.hour.mode()[0]) if len(clean_series) > 0 else None,
            "most_common_dayofweek": int(pd.to_datetime(clean_series).dt.dayofweek.mode()[0]) if len(clean_series) > 0 else None,
            "has_time_component": bool(not (pd.to_datetime(clean_series).dt.time == pd.Timestamp("00:00:00").time()).all())
        }
    
    def _extract_string_stats(self, series: pd.Series) -> Dict[str, Any]:
        """Extract statistics for string/object columns."""
        clean_series = series.dropna()
        
        if len(clean_series) == 0:
            return {"type": "string", "all_null": True}
        
        # Convert to string for analysis
        str_series = clean_series.astype(str)
        
        value_counts = str_series.value_counts()
        unique_ratio = len(value_counts) / len(clean_series)
        
        stats = {
            "type": "string",
            "unique_values": int(len(value_counts)),
            "unique_ratio": float(unique_ratio),
            "most_common_values": value_counts.head(10).to_dict(),
            "avg_length": float(str_series.str.len().mean()),
            "min_length": int(str_series.str.len().min()),
            "max_length": int(str_series.str.len().max()),
            "is_categorical": unique_ratio < 0.5 and len(value_counts) < 100,
            "has_numbers": bool(str_series.str.contains(r'\d', regex=True).any()),
            "has_special_chars": bool(str_series.str.contains(r'[^a-zA-Z0-9\s]', regex=True).any()),
            "is_email_like": bool(str_series.str.contains(r'@.*\.', regex=True).any()),
            "is_url_like": bool(str_series.str.contains(r'^https?://', regex=True).any()),
            "is_phone_like": bool(str_series.str.contains(r'^\+?\d{10,}$|^\d{3}-\d{3}-\d{4}$', regex=True).any())
        }
        
        # Check if it might be a boolean column disguised as string
        unique_lower = {v.lower() for v in value_counts.index[:10]}
        if unique_lower.issubset({'true', 'false', 'yes', 'no', '1', '0', 't', 'f', 'y', 'n'}):
            stats["might_be_boolean"] = True
        
        return stats
    
    def _extract_patterns(self, df: pd.DataFrame, sample_size: int) -> Dict[str, Any]:
        """Extract data patterns and regularities."""
        patterns = {}
        
        # Sample the dataframe if it's too large
        if len(df) > sample_size:
            sample_df = df.sample(n=sample_size, random_state=42)
        else:
            sample_df = df
        
        for col in df.columns:
            if pd.api.types.is_object_dtype(df[col]):
                patterns[col] = self._extract_string_patterns(sample_df[col])
        
        return patterns
    
    def _extract_string_patterns(self, series: pd.Series) -> Dict[str, Any]:
        """Extract common patterns from string columns."""
        clean_series = series.dropna().astype(str)
        
        if len(clean_series) == 0:
            return {}
        
        # Sample if too large
        if len(clean_series) > 100:
            clean_series = clean_series.sample(n=100, random_state=42)
        
        patterns = {
            "common_patterns": [],
            "detected_format": None
        }
        
        # Common regex patterns to check
        pattern_checks = {
            "email": r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
            "phone_us": r'^\+?1?\d{10}$|^\d{3}-\d{3}-\d{4}$',
            "ssn": r'^\d{3}-\d{2}-\d{4}$',
            "zip_code": r'^\d{5}(-\d{4})?$',
            "ipv4": r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$',
            "uuid": r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            "date_iso": r'^\d{4}-\d{2}-\d{2}$',
            "time_24h": r'^([01]?[0-9]|2[0-3]):[0-5][0-9](:[0-5][0-9])?$',
            "alphanumeric_id": r'^[A-Z0-9]{6,}$',
            "numeric_id": r'^\d+$'
        }
        
        for pattern_name, pattern_regex in pattern_checks.items():
            matches = clean_series.str.match(pattern_regex, na=False).sum()
            if matches > len(clean_series) * 0.8:  # 80% threshold
                patterns["detected_format"] = pattern_name
                patterns["format_confidence"] = float(matches / len(clean_series))
                break
        
        # Extract common prefixes/suffixes
        if len(clean_series) > 10:
            # Common prefixes
            prefixes = [s[:3] for s in clean_series if len(s) >= 3]
            if prefixes:
                prefix_counts = pd.Series(prefixes).value_counts()
                if prefix_counts.iloc[0] > len(prefixes) * 0.3:
                    patterns["common_prefix"] = prefix_counts.index[0]
            
            # Common suffixes
            suffixes = [s[-3:] for s in clean_series if len(s) >= 3]
            if suffixes:
                suffix_counts = pd.Series(suffixes).value_counts()
                if suffix_counts.iloc[0] > len(suffixes) * 0.3:
                    patterns["common_suffix"] = suffix_counts.index[0]
        
        return patterns
    
    def _extract_correlations(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Extract correlation information between columns."""
        correlations = {
            "numeric_correlations": {},
            "categorical_associations": {},
            "temporal_relationships": []
        }
        
        # Numeric correlations
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if len(numeric_cols) > 1 and len(df) > 2:  # Need at least 3 rows for meaningful correlation
            try:
                corr_matrix = df[numeric_cols].corr()
            except Exception as e:
                self.logger.warning(f"Could not calculate correlations: {e}")
                corr_matrix = pd.DataFrame()
            
            # Find strong correlations (> 0.5 or < -0.5)
            strong_corr = []
            if not corr_matrix.empty:
                for i in range(len(numeric_cols)):
                    for j in range(i+1, len(numeric_cols)):
                        corr_value = corr_matrix.iloc[i, j]
                        if pd.notna(corr_value) and abs(corr_value) > 0.5:
                            strong_corr.append({
                                "column1": numeric_cols[i],
                                "column2": numeric_cols[j],
                                "correlation": float(corr_value)
                            })
                
                correlations["numeric_correlations"]["strong_correlations"] = strong_corr
                correlations["numeric_correlations"]["correlation_matrix"] = corr_matrix.to_dict()
            else:
                correlations["numeric_correlations"]["strong_correlations"] = []
                correlations["numeric_correlations"]["correlation_matrix"] = {}
        
        # Categorical associations (using Cramér's V for categorical variables)
        categorical_cols = df.select_dtypes(include=['object']).columns.tolist()
        if len(categorical_cols) > 1:
            associations = []
            for i in range(min(len(categorical_cols), 10)):  # Limit to first 10 to avoid explosion
                for j in range(i+1, min(len(categorical_cols), 10)):
                    col1, col2 = categorical_cols[i], categorical_cols[j]
                    # Simple association metric based on unique value overlap
                    unique1 = df[col1].nunique()
                    unique2 = df[col2].nunique()
                    combined_unique = df.groupby([col1, col2]).size().shape[0]
                    association = 1 - (combined_unique / (unique1 * unique2))
                    if association > 0.3:  # Threshold for meaningful association
                        associations.append({
                            "column1": col1,
                            "column2": col2,
                            "association_strength": float(association)
                        })
            
            correlations["categorical_associations"] = associations
        
        return correlations
    
    def _extract_data_quality(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Extract data quality metrics."""
        return {
            "completeness": float(1 - df.isna().mean().mean()),
            "duplicate_rows": int(df.duplicated().sum()),
            "duplicate_percentage": float(df.duplicated().mean() * 100),
            "columns_with_nulls": [col for col in df.columns if df[col].isna().any()],
            "columns_all_null": [col for col in df.columns if df[col].isna().all()],
            "columns_single_value": [col for col in df.columns if df[col].nunique() == 1],
            "memory_usage_mb": float(df.memory_usage(deep=True).sum() / 1024 / 1024)
        }
    
    def _get_python_type(self, series: pd.Series) -> str:
        """Get the Python type of a pandas Series."""
        if pd.api.types.is_integer_dtype(series):
            return "int"
        elif pd.api.types.is_float_dtype(series):
            return "float"
        elif pd.api.types.is_bool_dtype(series):
            return "bool"
        elif pd.api.types.is_datetime64_any_dtype(series):
            return "datetime"
        elif pd.api.types.is_timedelta64_dtype(series):
            return "timedelta"
        elif pd.api.types.is_categorical_dtype(series):
            return "category"
        else:
            return "str"
    
    def to_secure_json(self, metadata: Dict[str, Any]) -> str:
        """
        Convert metadata to secure JSON format.
        This ensures no actual data values are included, only statistical properties.
        
        Args:
            metadata: Metadata dictionary
            
        Returns:
            JSON string of secure metadata
        """
        # Create a copy to avoid modifying original
        secure_metadata = json.loads(json.dumps(metadata, default=str))
        
        # Remove any potentially sensitive information
        if "statistics" in secure_metadata:
            for col_stats in secure_metadata["statistics"].values():
                if "most_common_values" in col_stats:
                    # Only keep the counts, not the actual values
                    col_stats["most_common_values"] = {
                        f"value_{i}": count 
                        for i, count in enumerate(col_stats["most_common_values"].values())
                    }
        
        return json.dumps(secure_metadata, indent=2, default=str)