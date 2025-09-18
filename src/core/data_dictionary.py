"""Data Dictionary Handler for constraint-based data generation."""

import json
import pandas as pd
import yaml
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
import re

from src.utils.logger import logger


class DataDictionary:
    """Handles data dictionary parsing, validation, and constraint application."""

    def __init__(self):
        """Initialize the data dictionary handler."""
        self.logger = logger
        self.dictionary = {}
        self.constraints = {}

    def parse_dictionary(self, content: Union[str, bytes, dict], format: str = 'auto') -> Dict[str, Any]:
        """
        Parse data dictionary from various formats.

        Args:
            content: Dictionary content (string, bytes, or dict)
            format: Format type ('json', 'yaml', 'csv', 'excel', 'auto')

        Returns:
            Parsed dictionary structure
        """
        if format == 'auto':
            format = self._detect_format(content)

        self.logger.info(f"Parsing data dictionary in {format} format")

        if format == 'json':
            return self._parse_json(content)
        elif format == 'yaml':
            return self._parse_yaml(content)
        elif format == 'csv':
            return self._parse_csv(content)
        elif format == 'excel':
            return self._parse_excel(content)
        elif format == 'text':
            return self._parse_text_with_llm(content)
        else:
            # Try to parse as text with LLM
            return self._parse_text_with_llm(str(content))

    def _detect_format(self, content: Union[str, bytes, dict]) -> str:
        """Detect the format of the data dictionary."""
        if isinstance(content, dict):
            return 'json'

        # Convert bytes to string if needed
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='ignore')

        content_str = str(content).strip()

        # Check for JSON
        if content_str.startswith('{') or content_str.startswith('['):
            try:
                json.loads(content_str)
                return 'json'
            except:
                pass

        # Check for YAML
        if ':' in content_str and (
            content_str.startswith('---') or
            any(line.strip().endswith(':') for line in content_str.split('\n')[:10])
        ):
            return 'yaml'

        # Check for CSV-like structure
        lines = content_str.split('\n')
        if len(lines) > 1 and ',' in lines[0]:
            headers = lines[0].lower()
            if any(keyword in headers for keyword in ['column', 'field', 'type', 'constraint']):
                return 'csv'

        # Default to text for LLM parsing
        return 'text'

    def _parse_json(self, content: Union[str, dict]) -> Dict[str, Any]:
        """Parse JSON format dictionary."""
        if isinstance(content, dict):
            data = content
        else:
            if isinstance(content, bytes):
                content = content.decode('utf-8')
            data = json.loads(content)

        return self._standardize_dictionary(data)

    def _parse_yaml(self, content: Union[str, bytes]) -> Dict[str, Any]:
        """Parse YAML format dictionary."""
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        data = yaml.safe_load(content)
        return self._standardize_dictionary(data)

    def _parse_csv(self, content: Union[str, bytes]) -> Dict[str, Any]:
        """Parse CSV format dictionary."""
        if isinstance(content, bytes):
            content = content.decode('utf-8')

        import io
        df = pd.read_csv(io.StringIO(content))

        dictionary = {"columns": {}}

        # Common column name mappings
        col_mappings = {
            'column': 'name',
            'field': 'name',
            'column_name': 'name',
            'field_name': 'name',
            'data_type': 'type',
            'datatype': 'type',
            'constraint': 'constraints',
            'validation': 'constraints',
            'description': 'description',
            'values': 'allowed_values',
            'allowed_values': 'allowed_values',
            'min': 'min_value',
            'max': 'max_value',
            'required': 'required',
            'nullable': 'nullable'
        }

        # Normalize column names
        df.columns = [col.lower().strip() for col in df.columns]

        for _, row in df.iterrows():
            col_name = None
            col_def = {}

            for csv_col, dict_key in col_mappings.items():
                if csv_col in df.columns and pd.notna(row[csv_col]):
                    if dict_key == 'name':
                        col_name = str(row[csv_col])
                    else:
                        col_def[dict_key] = row[csv_col]

            if col_name:
                dictionary["columns"][col_name] = col_def

        return dictionary

    def _parse_excel(self, content: bytes) -> Dict[str, Any]:
        """Parse Excel format dictionary."""
        import io
        df = pd.read_excel(io.BytesIO(content))
        # Convert to CSV-like format and parse
        csv_content = df.to_csv(index=False)
        return self._parse_csv(csv_content)

    def _parse_text_with_llm(self, content: str) -> Dict[str, Any]:
        """
        Parse unstructured text using LLM to extract data dictionary.
        This is a fallback for non-standard formats.
        """
        # For now, use pattern matching as fallback
        # In production, this would call the LLM to interpret the text

        dictionary = {"columns": {}}

        # Try to extract column definitions using patterns
        lines = content.split('\n')
        current_column = None

        for line in lines:
            line = line.strip()

            # Look for column definitions
            if re.match(r'^[A-Za-z_][A-Za-z0-9_]*\s*[:=]', line):
                parts = re.split(r'[:=]', line, 1)
                if len(parts) == 2:
                    col_name = parts[0].strip()
                    col_info = parts[1].strip()

                    dictionary["columns"][col_name] = {
                        "description": col_info,
                        "type": self._infer_type_from_description(col_info)
                    }
                    current_column = col_name

            # Look for constraints on current column
            elif current_column and any(keyword in line.lower() for keyword in ['min', 'max', 'values', 'required']):
                if 'min' in line.lower():
                    match = re.search(r'min[:\s]+(\d+)', line, re.IGNORECASE)
                    if match:
                        dictionary["columns"][current_column]["min_value"] = int(match.group(1))

                if 'max' in line.lower():
                    match = re.search(r'max[:\s]+(\d+)', line, re.IGNORECASE)
                    if match:
                        dictionary["columns"][current_column]["max_value"] = int(match.group(1))

        return dictionary

    def _infer_type_from_description(self, description: str) -> str:
        """Infer data type from description text."""
        desc_lower = description.lower()

        if any(word in desc_lower for word in ['date', 'time', 'timestamp']):
            return 'datetime'
        elif any(word in desc_lower for word in ['int', 'number', 'count', 'age', 'quantity']):
            return 'integer'
        elif any(word in desc_lower for word in ['float', 'decimal', 'amount', 'price', 'rate']):
            return 'float'
        elif any(word in desc_lower for word in ['bool', 'flag', 'yes/no', 'true/false']):
            return 'boolean'
        else:
            return 'string'

    def _standardize_dictionary(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Standardize dictionary to common format.

        Expected format:
        {
            "columns": {
                "column_name": {
                    "type": "string|integer|float|datetime|boolean",
                    "description": "Column description",
                    "constraints": {
                        "required": true|false,
                        "unique": true|false,
                        "min_value": number,
                        "max_value": number,
                        "min_length": number,
                        "max_length": number,
                        "pattern": "regex pattern",
                        "allowed_values": ["value1", "value2"],
                        "format": "date format or other format spec"
                    }
                }
            }
        }
        """
        if "columns" in data:
            return data

        # Try to convert various formats
        standardized = {"columns": {}}

        # Handle list of column definitions
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and 'name' in item:
                    col_name = item.pop('name')
                    standardized["columns"][col_name] = item

        # Handle direct column mapping
        elif isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict):
                    standardized["columns"][key] = value
                else:
                    # Simple type mapping
                    standardized["columns"][key] = {"type": str(value)}

        return standardized

    def validate_data(self, df: pd.DataFrame, dictionary: Optional[Dict[str, Any]] = None) -> Dict[str, List[str]]:
        """
        Validate DataFrame against data dictionary.

        Args:
            df: DataFrame to validate
            dictionary: Data dictionary (uses stored if not provided)

        Returns:
            Dictionary of column names to list of validation errors
        """
        if dictionary is None:
            dictionary = self.dictionary

        errors = {}

        for col_name, col_def in dictionary.get("columns", {}).items():
            if col_name not in df.columns:
                if col_def.get("constraints", {}).get("required", False):
                    errors[col_name] = [f"Required column '{col_name}' is missing"]
                continue

            col_errors = self._validate_column(df[col_name], col_def)
            if col_errors:
                errors[col_name] = col_errors

        return errors

    def _validate_column(self, series: pd.Series, definition: Dict[str, Any]) -> List[str]:
        """Validate a single column against its definition."""
        errors = []
        constraints = definition.get("constraints", {})

        # Check data type
        expected_type = definition.get("type", "string").lower()
        if not self._check_type_compatibility(series, expected_type):
            errors.append(f"Type mismatch: expected {expected_type}")

        # Check constraints
        if constraints.get("required") and series.isna().any():
            errors.append("Contains null values but marked as required")

        if constraints.get("unique") and series.duplicated().any():
            errors.append("Contains duplicate values but marked as unique")

        # Numeric constraints
        if expected_type in ['integer', 'float', 'numeric']:
            if 'min_value' in constraints:
                if (series.dropna() < constraints['min_value']).any():
                    errors.append(f"Values below minimum {constraints['min_value']}")

            if 'max_value' in constraints:
                if (series.dropna() > constraints['max_value']).any():
                    errors.append(f"Values above maximum {constraints['max_value']}")

        # String constraints
        if expected_type == 'string':
            if 'min_length' in constraints:
                if (series.dropna().str.len() < constraints['min_length']).any():
                    errors.append(f"Strings shorter than minimum length {constraints['min_length']}")

            if 'max_length' in constraints:
                if (series.dropna().str.len() > constraints['max_length']).any():
                    errors.append(f"Strings longer than maximum length {constraints['max_length']}")

            if 'pattern' in constraints:
                pattern = constraints['pattern']
                if not series.dropna().str.match(pattern).all():
                    errors.append(f"Values don't match pattern: {pattern}")

        # Allowed values
        if 'allowed_values' in constraints:
            allowed = set(constraints['allowed_values'])
            actual = set(series.dropna().unique())
            if not actual.issubset(allowed):
                invalid = actual - allowed
                errors.append(f"Invalid values found: {list(invalid)[:5]}")

        return errors

    def _check_type_compatibility(self, series: pd.Series, expected_type: str) -> bool:
        """Check if series type is compatible with expected type."""
        if expected_type in ['integer', 'int']:
            return pd.api.types.is_integer_dtype(series) or series.dropna().apply(lambda x: isinstance(x, int)).all()
        elif expected_type in ['float', 'numeric', 'decimal']:
            return pd.api.types.is_numeric_dtype(series)
        elif expected_type in ['string', 'text', 'varchar']:
            return pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series)
        elif expected_type in ['datetime', 'date', 'timestamp']:
            return pd.api.types.is_datetime64_any_dtype(series)
        elif expected_type in ['boolean', 'bool']:
            return pd.api.types.is_bool_dtype(series)
        else:
            return True  # Unknown type, assume compatible

    def apply_to_metadata(self, metadata: Dict[str, Any], dictionary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Apply data dictionary constraints to metadata for generation.

        Args:
            metadata: Metadata from MetadataExtractor
            dictionary: Data dictionary (uses stored if not provided)

        Returns:
            Enhanced metadata with dictionary constraints
        """
        if dictionary is None:
            dictionary = self.dictionary

        enhanced_metadata = metadata.copy()

        for col_name, col_def in dictionary.get("columns", {}).items():
            # Add or update column in metadata
            if col_name not in enhanced_metadata.get("statistics", {}):
                enhanced_metadata["statistics"][col_name] = {}

            col_stats = enhanced_metadata["statistics"][col_name]

            # Apply type
            col_stats["type"] = col_def.get("type", "string")

            # Apply constraints
            constraints = col_def.get("constraints", {})

            if "allowed_values" in constraints:
                col_stats["allowed_values"] = constraints["allowed_values"]
                col_stats["is_categorical"] = True

            if "min_value" in constraints:
                col_stats["min"] = constraints["min_value"]

            if "max_value" in constraints:
                col_stats["max"] = constraints["max_value"]

            if "pattern" in constraints:
                col_stats["pattern"] = constraints["pattern"]

            if "format" in constraints:
                col_stats["format"] = constraints["format"]

            # Add description for better generation
            if "description" in col_def:
                col_stats["description"] = col_def["description"]

            # Mark as dictionary-defined
            col_stats["from_dictionary"] = True

        return enhanced_metadata

    def to_generation_constraints(self, dictionary: Optional[Dict[str, Any]] = None) -> str:
        """
        Convert dictionary to generation constraints text for LLM.

        Args:
            dictionary: Data dictionary (uses stored if not provided)

        Returns:
            Text description of constraints for LLM prompt
        """
        if dictionary is None:
            dictionary = self.dictionary

        constraints_text = []

        for col_name, col_def in dictionary.get("columns", {}).items():
            constraint_parts = [f"{col_name}: {col_def.get('type', 'string')} type"]

            if "description" in col_def:
                constraint_parts.append(f"({col_def['description']})")

            constraints = col_def.get("constraints", {})

            if "allowed_values" in constraints:
                values = constraints["allowed_values"][:10]  # Limit to first 10
                constraint_parts.append(f"must be one of: {values}")

            if "min_value" in constraints:
                constraint_parts.append(f"min={constraints['min_value']}")

            if "max_value" in constraints:
                constraint_parts.append(f"max={constraints['max_value']}")

            if "pattern" in constraints:
                constraint_parts.append(f"pattern={constraints['pattern']}")

            if constraints.get("required"):
                constraint_parts.append("REQUIRED")

            if constraints.get("unique"):
                constraint_parts.append("UNIQUE")

            constraints_text.append(" - ".join(constraint_parts))

        return "\n".join(constraints_text)

    def save(self, filepath: Union[str, Path]):
        """Save dictionary to file."""
        filepath = Path(filepath)
        with open(filepath, 'w') as f:
            json.dump(self.dictionary, f, indent=2)

    def load(self, filepath: Union[str, Path]):
        """Load dictionary from file."""
        filepath = Path(filepath)
        with open(filepath, 'r') as f:
            self.dictionary = json.load(f)