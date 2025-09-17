"""Format-agnostic data loader for various file types."""

import json
import pandas as pd
from pathlib import Path
from typing import Union, Dict, Any, Optional
import io
from src.utils.logger import logger


class DataLoader:
    """Load and parse various data file formats into standardized pandas DataFrames."""
    
    SUPPORTED_FORMATS = {
        '.csv': 'csv',
        '.json': 'json',
        '.xlsx': 'excel',
        '.xls': 'excel',
        '.parquet': 'parquet',
        '.tsv': 'tsv',
        '.txt': 'text'
    }
    
    def __init__(self):
        """Initialize the DataLoader."""
        self.logger = logger
        
    def detect_file_type(self, file_path: Union[str, Path]) -> str:
        """
        Detect file type based on extension.
        
        Args:
            file_path: Path to the file
            
        Returns:
            File type string
            
        Raises:
            ValueError: If file type is not supported
        """
        file_path = Path(file_path)
        extension = file_path.suffix.lower()
        
        if extension not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported file format: {extension}. Supported formats: {list(self.SUPPORTED_FORMATS.keys())}")
        
        return self.SUPPORTED_FORMATS[extension]
    
    def load_csv(self, file_path: Union[str, Path], **kwargs) -> pd.DataFrame:
        """Load CSV file into DataFrame."""
        self.logger.info(f"Loading CSV file: {file_path}")
        try:
            df = pd.read_csv(file_path, **kwargs)
            self.logger.info(f"Successfully loaded CSV with shape: {df.shape}")
            return df
        except Exception as e:
            self.logger.error(f"Error loading CSV file: {e}")
            raise
    
    def load_tsv(self, file_path: Union[str, Path], **kwargs) -> pd.DataFrame:
        """Load TSV file into DataFrame."""
        self.logger.info(f"Loading TSV file: {file_path}")
        try:
            df = pd.read_csv(file_path, sep='\t', **kwargs)
            self.logger.info(f"Successfully loaded TSV with shape: {df.shape}")
            return df
        except Exception as e:
            self.logger.error(f"Error loading TSV file: {e}")
            raise
    
    def load_json(self, file_path: Union[str, Path], **kwargs) -> pd.DataFrame:
        """
        Load JSON file into DataFrame.
        Handles both normalized and nested JSON structures.
        """
        self.logger.info(f"Loading JSON file: {file_path}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Handle different JSON structures
            if isinstance(data, list):
                # Array of objects
                df = pd.json_normalize(data, **kwargs)
            elif isinstance(data, dict):
                # Single object or nested structure
                if all(isinstance(v, (list, dict)) for v in data.values()):
                    # Nested structure - try to normalize
                    df = pd.json_normalize(data, **kwargs)
                else:
                    # Single record
                    df = pd.DataFrame([data])
            else:
                raise ValueError(f"Unexpected JSON structure: {type(data)}")
            
            self.logger.info(f"Successfully loaded JSON with shape: {df.shape}")
            return df
        except Exception as e:
            self.logger.error(f"Error loading JSON file: {e}")
            raise
    
    def load_excel(self, file_path: Union[str, Path], sheet_name: Union[str, int] = 0, **kwargs) -> pd.DataFrame:
        """Load Excel file into DataFrame."""
        self.logger.info(f"Loading Excel file: {file_path}")
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, **kwargs)
            self.logger.info(f"Successfully loaded Excel with shape: {df.shape}")
            return df
        except Exception as e:
            self.logger.error(f"Error loading Excel file: {e}")
            raise
    
    def load_parquet(self, file_path: Union[str, Path], **kwargs) -> pd.DataFrame:
        """Load Parquet file into DataFrame."""
        self.logger.info(f"Loading Parquet file: {file_path}")
        try:
            df = pd.read_parquet(file_path, **kwargs)
            self.logger.info(f"Successfully loaded Parquet with shape: {df.shape}")
            return df
        except Exception as e:
            self.logger.error(f"Error loading Parquet file: {e}")
            raise
    
    def load_text(self, file_path: Union[str, Path], delimiter: Optional[str] = None, **kwargs) -> pd.DataFrame:
        """
        Load text file into DataFrame.
        Attempts to auto-detect delimiter if not provided.
        """
        self.logger.info(f"Loading text file: {file_path}")
        try:
            if delimiter is None:
                # Try to auto-detect delimiter
                with open(file_path, 'r', encoding='utf-8') as f:
                    first_line = f.readline()
                    if '\t' in first_line:
                        delimiter = '\t'
                    elif ',' in first_line:
                        delimiter = ','
                    elif '|' in first_line:
                        delimiter = '|'
                    else:
                        delimiter = ' '
            
            df = pd.read_csv(file_path, delimiter=delimiter, **kwargs)
            self.logger.info(f"Successfully loaded text file with shape: {df.shape}")
            return df
        except Exception as e:
            self.logger.error(f"Error loading text file: {e}")
            raise
    
    def load_from_bytes(self, file_bytes: bytes, file_name: str, **kwargs) -> pd.DataFrame:
        """
        Load data from bytes (useful for uploaded files).
        
        Args:
            file_bytes: File content as bytes
            file_name: Original file name (used to detect format)
            **kwargs: Additional arguments for specific loaders
            
        Returns:
            Loaded DataFrame
        """
        file_path = Path(file_name)
        file_type = self.detect_file_type(file_path)
        
        # Create BytesIO object
        file_io = io.BytesIO(file_bytes)
        
        # Route to appropriate loader
        if file_type == 'csv':
            return pd.read_csv(file_io, **kwargs)
        elif file_type == 'tsv':
            return pd.read_csv(file_io, sep='\t', **kwargs)
        elif file_type == 'json':
            data = json.load(file_io)
            if isinstance(data, list):
                return pd.json_normalize(data, **kwargs)
            elif isinstance(data, dict):
                return pd.json_normalize(data, **kwargs)
            else:
                return pd.DataFrame([data])
        elif file_type == 'excel':
            return pd.read_excel(file_io, **kwargs)
        elif file_type == 'parquet':
            return pd.read_parquet(file_io, **kwargs)
        else:
            raise ValueError(f"Unsupported file type for bytes loading: {file_type}")
    
    def load(self, file_path: Union[str, Path], **kwargs) -> pd.DataFrame:
        """
        Main entry point to load any supported file format.
        
        Args:
            file_path: Path to the file
            **kwargs: Additional arguments passed to specific loaders
            
        Returns:
            Standardized pandas DataFrame
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        file_type = self.detect_file_type(file_path)
        
        # Route to appropriate loader
        loaders = {
            'csv': self.load_csv,
            'tsv': self.load_tsv,
            'json': self.load_json,
            'excel': self.load_excel,
            'parquet': self.load_parquet,
            'text': self.load_text
        }
        
        loader = loaders.get(file_type)
        if not loader:
            raise ValueError(f"No loader available for file type: {file_type}")
        
        df = loader(file_path, **kwargs)
        
        # Standardize DataFrame
        df = self._standardize_dataframe(df)
        
        return df
    
    def _standardize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardize DataFrame format and detect date columns.

        Args:
            df: Input DataFrame

        Returns:
            Standardized DataFrame with proper dtypes
        """
        # Remove completely empty columns
        df = df.dropna(axis=1, how='all')

        # Reset index to ensure consistent indexing
        df = df.reset_index(drop=True)

        # Convert column names to strings
        df.columns = df.columns.astype(str)

        # Attempt to detect and convert date columns
        df = self._detect_and_convert_dates(df)

        # Log basic statistics
        self.logger.info(f"DataFrame standardized - Shape: {df.shape}, Columns: {list(df.columns)[:5]}{'...' if len(df.columns) > 5 else ''}")

        return df

    def _detect_and_convert_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect and convert potential date columns to datetime dtype.

        Args:
            df: Input DataFrame

        Returns:
            DataFrame with detected date columns converted to datetime
        """
        date_patterns = [
            r'^\d{4}-\d{2}-\d{2}$',  # YYYY-MM-DD
            r'^\d{2}/\d{2}/\d{4}$',  # MM/DD/YYYY or DD/MM/YYYY
            r'^\d{2}-\d{2}-\d{4}$',  # MM-DD-YYYY or DD-MM-YYYY
            r'^\d{4}/\d{2}/\d{2}$',  # YYYY/MM/DD
            r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$',  # YYYY-MM-DD HH:MM:SS
            r'^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$',  # MM/DD/YYYY HH:MM:SS
        ]

        date_keywords = ['date', 'time', 'datetime', 'timestamp', 'created', 'updated',
                        'modified', 'dob', 'birth', 'start', 'end', 'when', 'day']

        for col in df.columns:
            # Skip if already datetime
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                continue

            # Skip numeric columns
            if pd.api.types.is_numeric_dtype(df[col]):
                continue

            # Check if column name suggests date/time
            col_lower = col.lower()
            name_suggests_date = any(keyword in col_lower for keyword in date_keywords)

            # For string columns, check if values match date patterns
            if pd.api.types.is_object_dtype(df[col]):
                # Sample non-null values
                sample = df[col].dropna().head(10).astype(str)
                if len(sample) > 0:
                    # Check if values match date patterns
                    matches_pattern = False
                    for pattern in date_patterns:
                        if sample.str.match(pattern).mean() > 0.8:  # 80% of sample matches
                            matches_pattern = True
                            break

                    # Try to convert if name suggests date or pattern matches
                    if name_suggests_date or matches_pattern:
                        try:
                            # Try multiple date formats
                            converted = pd.to_datetime(df[col], errors='coerce', infer_datetime_format=True)

                            # Check if conversion was successful for majority of non-null values
                            non_null_original = df[col].notna().sum()
                            non_null_converted = converted.notna().sum()

                            if non_null_converted >= non_null_original * 0.8:  # 80% successful conversion
                                df[col] = converted
                                self.logger.info(f"Converted column '{col}' to datetime")
                        except Exception as e:
                            self.logger.debug(f"Could not convert column '{col}' to datetime: {e}")

        return df