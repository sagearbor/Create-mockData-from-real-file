"""Unit tests for the DataLoader module."""

import pytest
import pandas as pd
import json
import tempfile
from pathlib import Path
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.data_loader import DataLoader


class TestDataLoader:
    """Test suite for DataLoader class."""
    
    @pytest.fixture
    def data_loader(self):
        """Create a DataLoader instance."""
        return DataLoader()
    
    # NOTE: these fixtures must fully write and CLOSE the file before yielding.
    # Yielding from inside `open(...)` leaves the writes sitting in the buffer,
    # so the loader sees an empty file ("No columns to parse from file").

    @pytest.fixture
    def sample_csv_file(self, tmp_path):
        """Create a temporary CSV file for testing."""
        path = tmp_path / "sample.csv"
        path.write_text(
            "id,name,age,salary\n"
            "1,John Doe,30,50000\n"
            "2,Jane Smith,25,45000\n"
            "3,Bob Johnson,35,60000\n"
        )
        return str(path)

    @pytest.fixture
    def sample_json_file(self, tmp_path):
        """Create a temporary JSON file for testing."""
        data = [
            {"id": 1, "name": "John Doe", "age": 30, "salary": 50000},
            {"id": 2, "name": "Jane Smith", "age": 25, "salary": 45000},
            {"id": 3, "name": "Bob Johnson", "age": 35, "salary": 60000}
        ]
        path = tmp_path / "sample.json"
        path.write_text(json.dumps(data))
        return str(path)

    @pytest.fixture
    def sample_nested_json_file(self, tmp_path):
        """Create a temporary nested JSON file for testing."""
        data = {
            "users": [
                {"id": 1, "info": {"name": "John", "age": 30}},
                {"id": 2, "info": {"name": "Jane", "age": 25}}
            ]
        }
        path = tmp_path / "nested.json"
        path.write_text(json.dumps(data))
        return str(path)
    
    def test_detect_file_type_csv(self, data_loader):
        """Test file type detection for CSV files."""
        assert data_loader.detect_file_type("test.csv") == "csv"
        assert data_loader.detect_file_type("data.CSV") == "csv"
    
    def test_detect_file_type_json(self, data_loader):
        """Test file type detection for JSON files."""
        assert data_loader.detect_file_type("test.json") == "json"
        assert data_loader.detect_file_type("data.JSON") == "json"
    
    def test_detect_file_type_excel(self, data_loader):
        """Test file type detection for Excel files."""
        assert data_loader.detect_file_type("test.xlsx") == "excel"
        assert data_loader.detect_file_type("test.xls") == "excel"
    
    def test_detect_file_type_unsupported(self, data_loader):
        """Test error handling for unsupported file types."""
        with pytest.raises(ValueError, match="Unsupported file format"):
            data_loader.detect_file_type("test.pdf")
    
    def test_load_csv(self, data_loader, sample_csv_file):
        """Test loading CSV files."""
        df = data_loader.load_csv(sample_csv_file)
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert list(df.columns) == ["id", "name", "age", "salary"]
        assert df["age"].dtype == "int64"
    
    def test_load_json_array(self, data_loader, sample_json_file):
        """Test loading JSON files with array structure."""
        df = data_loader.load_json(sample_json_file)
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert "name" in df.columns
        assert df["id"].tolist() == [1, 2, 3]
    
    def test_load_json_nested(self, data_loader, sample_nested_json_file):
        """Test loading nested JSON files."""
        df = data_loader.load_json(sample_nested_json_file)
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
    
    def test_load_main_entry(self, data_loader, sample_csv_file):
        """Test the main load method."""
        df = data_loader.load(sample_csv_file)
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        # Check standardization
        assert df.index.tolist() == [0, 1, 2]
    
    def test_load_nonexistent_file(self, data_loader):
        """Test error handling for non-existent files."""
        with pytest.raises(FileNotFoundError):
            data_loader.load("nonexistent.csv")
    
    def test_standardize_dataframe(self, data_loader):
        """Test DataFrame standardization."""
        # Create a DataFrame with issues
        df = pd.DataFrame({
            "col1": [1, 2, 3],
            "col2": [None, None, None],  # All null column
            "col3": ["a", "b", "c"]
        })
        df.index = [5, 10, 15]  # Non-standard index
        
        standardized = data_loader._standardize_dataframe(df)
        
        # Check that empty column is removed
        assert "col2" not in standardized.columns
        # Check that index is reset
        assert standardized.index.tolist() == [0, 1, 2]
        # Check that column names are strings
        assert all(isinstance(col, str) for col in standardized.columns)
    
    def test_load_from_bytes_csv(self, data_loader):
        """Test loading CSV data from bytes."""
        csv_content = b"id,name,value\n1,test,100\n2,sample,200"
        df = data_loader.load_from_bytes(csv_content, "test.csv")
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert list(df.columns) == ["id", "name", "value"]
    
    def test_load_from_bytes_json(self, data_loader):
        """Test loading JSON data from bytes."""
        json_content = json.dumps([
            {"id": 1, "name": "test"},
            {"id": 2, "name": "sample"}
        ]).encode()
        
        df = data_loader.load_from_bytes(json_content, "test.json")
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert "name" in df.columns