"""Unit tests for the MetadataExtractor module."""

import pytest
import pandas as pd
import numpy as np
import json
import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.metadata_extractor import MetadataExtractor


class TestMetadataExtractor:
    """Test suite for MetadataExtractor class."""
    
    @pytest.fixture
    def metadata_extractor(self):
        """Create a MetadataExtractor instance."""
        return MetadataExtractor()
    
    @pytest.fixture
    def sample_dataframe(self):
        """Create a sample DataFrame for testing."""
        np.random.seed(42)
        return pd.DataFrame({
            "id": range(1, 101),
            "name": [f"Person_{i}" for i in range(1, 101)],
            "age": np.random.randint(18, 80, 100),
            "salary": np.random.normal(50000, 15000, 100),
            "department": np.random.choice(["Sales", "Engineering", "HR", "Marketing"], 100),
            "hire_date": pd.date_range(start="2020-01-01", periods=100, freq="W"),
            "is_active": np.random.choice([True, False], 100),
            "email": [f"person{i}@company.com" for i in range(1, 101)],
            "phone": [f"555-{i:04d}" for i in range(1, 101)]
        })
    
    @pytest.fixture
    def dataframe_with_nulls(self):
        """Create a DataFrame with null values."""
        df = pd.DataFrame({
            "col1": [1, 2, None, 4, 5],
            "col2": ["a", None, "c", "d", None],
            "col3": [1.1, 2.2, 3.3, None, 5.5],
            "col4": [None, None, None, None, None]
        })
        return df
    
    def test_extract_metadata_structure(self, metadata_extractor, sample_dataframe):
        """Test extraction of structural metadata."""
        metadata = metadata_extractor.extract(sample_dataframe)
        
        assert "structure" in metadata
        assert metadata["structure"]["shape"]["rows"] == 100
        assert metadata["structure"]["shape"]["columns"] == 9
        assert len(metadata["structure"]["columns"]) == 9
        
        # Check column information
        id_col = next(c for c in metadata["structure"]["columns"] if c["name"] == "id")
        assert id_col["dtype"] == "int64"
        assert id_col["python_type"] == "int"
        assert id_col["unique_count"] == 100
    
    def test_extract_statistical_metadata(self, metadata_extractor, sample_dataframe):
        """Test extraction of statistical metadata."""
        metadata = metadata_extractor.extract(sample_dataframe)
        
        assert "statistics" in metadata
        assert "age" in metadata["statistics"]
        
        age_stats = metadata["statistics"]["age"]
        assert age_stats["type"] == "numeric"
        assert "mean" in age_stats
        assert "std" in age_stats
        assert "min" in age_stats
        assert "max" in age_stats
        assert age_stats["is_integer"] == True
    
    def test_extract_string_statistics(self, metadata_extractor, sample_dataframe):
        """Test extraction of string column statistics."""
        metadata = metadata_extractor.extract(sample_dataframe)
        
        dept_stats = metadata["statistics"]["department"]
        assert dept_stats["type"] == "string"
        assert dept_stats["is_categorical"] == True
        assert dept_stats["unique_values"] == 4
        assert "most_common_values" in dept_stats
    
    def test_extract_datetime_statistics(self, metadata_extractor, sample_dataframe):
        """Test extraction of datetime column statistics."""
        metadata = metadata_extractor.extract(sample_dataframe)
        
        hire_stats = metadata["statistics"]["hire_date"]
        assert hire_stats["type"] == "datetime"
        assert "min" in hire_stats
        assert "max" in hire_stats
        assert "range_days" in hire_stats
    
    def test_extract_patterns(self, metadata_extractor, sample_dataframe):
        """Test pattern extraction from string columns."""
        metadata = metadata_extractor.extract(sample_dataframe)
        
        assert "patterns" in metadata
        assert "email" in metadata["patterns"]
        
        email_patterns = metadata["patterns"]["email"]
        assert email_patterns["detected_format"] == "email"
        assert email_patterns["format_confidence"] > 0.8
    
    def test_extract_correlations(self, metadata_extractor):
        """Test correlation extraction."""
        # Create DataFrame with correlated columns
        np.random.seed(42)
        df = pd.DataFrame({
            "x": np.random.randn(100),
            "y": np.random.randn(100)
        })
        df["z"] = df["x"] * 2 + np.random.randn(100) * 0.1  # Strong correlation with x
        
        extractor = MetadataExtractor()
        metadata = extractor.extract(df)
        
        assert "correlations" in metadata
        assert "numeric_correlations" in metadata["correlations"]
        
        strong_corr = metadata["correlations"]["numeric_correlations"]["strong_correlations"]
        assert len(strong_corr) > 0
        
        # Find correlation between x and z
        xz_corr = next((c for c in strong_corr if 
                       (c["column1"] == "x" and c["column2"] == "z") or
                       (c["column1"] == "z" and c["column2"] == "x")), None)
        assert xz_corr is not None
        assert abs(xz_corr["correlation"]) > 0.9
    
    def test_extract_data_quality(self, metadata_extractor, dataframe_with_nulls):
        """Test data quality metrics extraction."""
        metadata = metadata_extractor.extract(dataframe_with_nulls)
        
        quality = metadata["data_quality"]
        assert "completeness" in quality
        assert "duplicate_rows" in quality
        assert "columns_with_nulls" in quality
        assert "columns_all_null" in quality
        
        assert "col4" in quality["columns_all_null"]
        assert set(quality["columns_with_nulls"]) == {"col1", "col2", "col3", "col4"}
    
    def test_get_python_type(self, metadata_extractor):
        """Test Python type detection."""
        assert metadata_extractor._get_python_type(pd.Series([1, 2, 3])) == "int"
        assert metadata_extractor._get_python_type(pd.Series([1.1, 2.2])) == "float"
        assert metadata_extractor._get_python_type(pd.Series([True, False])) == "bool"
        assert metadata_extractor._get_python_type(pd.Series(["a", "b"])) == "str"
        assert metadata_extractor._get_python_type(pd.Series(pd.date_range("2020-01-01", periods=3))) == "datetime"
    
    def test_extract_numeric_stats_edge_cases(self, metadata_extractor):
        """Test numeric statistics with edge cases."""
        # All nulls
        all_null = pd.Series([None, None, None], dtype=float)
        stats = metadata_extractor._extract_numeric_stats(all_null)
        assert stats["all_null"] == True
        
        # Single value
        single = pd.Series([5.0])
        stats = metadata_extractor._extract_numeric_stats(single)
        assert stats["mean"] == 5.0
        assert stats["std"] == 0.0
        
        # Percentage detection
        percentage = pd.Series([0.1, 0.5, 0.9, 0.3])
        stats = metadata_extractor._extract_numeric_stats(percentage)
        assert stats.get("might_be_percentage") == "decimal"
    
    def test_extract_string_patterns_phone(self, metadata_extractor):
        """Test phone number pattern detection."""
        phone_series = pd.Series(["555-123-4567", "555-987-6543", "555-555-5555"])
        patterns = metadata_extractor._extract_string_patterns(phone_series)
        
        assert patterns["detected_format"] == "phone_us"
        assert patterns["format_confidence"] > 0.8
    
    def test_to_secure_json(self, metadata_extractor, sample_dataframe):
        """Test secure JSON conversion."""
        metadata = metadata_extractor.extract(sample_dataframe)
        secure_json = metadata_extractor.to_secure_json(metadata)
        
        # Parse JSON to verify it's valid
        parsed = json.loads(secure_json)
        assert parsed is not None
        
        # Check that sensitive values are anonymized
        for col_stats in parsed["statistics"].values():
            if "most_common_values" in col_stats:
                # Values should be anonymized
                for key in col_stats["most_common_values"]:
                    assert key.startswith("value_")
    
    def test_metadata_version(self, metadata_extractor, sample_dataframe):
        """Test that metadata includes version information."""
        metadata = metadata_extractor.extract(sample_dataframe)
        
        assert "metadata_version" in metadata
        assert metadata["metadata_version"] == "1.0"
        assert "extraction_timestamp" in metadata