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

    def parse_dictionary(self, content: Union[str, bytes, dict], format: str = 'auto', filename: str = '') -> Dict[str, Any]:
        """
        Parse data dictionary from various formats.

        Args:
            content: Dictionary content (string, bytes, or dict)
            format: Format type ('json', 'yaml', 'csv', 'excel', 'pdf', 'auto')
            filename: Original filename for format detection

        Returns:
            Parsed dictionary structure
        """
        if format == 'auto':
            format = self._detect_format(content, filename)

        self.logger.info(f"Parsing data dictionary in {format} format")

        if format == 'json':
            return self._parse_json(content)
        elif format == 'yaml':
            return self._parse_yaml(content)
        elif format == 'csv':
            return self._parse_csv(content)
        elif format in ['excel', 'xls', 'xlsx']:
            return self._parse_excel(content)
        elif format == 'pdf':
            return self._parse_pdf(content)
        elif format == 'text':
            return self._parse_text_with_llm(content)
        else:
            # Try to parse as text with LLM
            return self._parse_text_with_llm(str(content))

    def _detect_format(self, content: Union[str, bytes, dict], filename: str = '') -> str:
        """Detect the format of the data dictionary."""
        if isinstance(content, dict):
            return 'json'

        # Check file extension first
        if filename:
            ext = filename.lower().split('.')[-1] if '.' in filename else ''
            if ext in ['json']:
                return 'json'
            elif ext in ['yaml', 'yml']:
                return 'yaml'
            elif ext in ['csv']:
                return 'csv'
            elif ext in ['xls', 'xlsx']:
                return 'excel'
            elif ext in ['pdf']:
                return 'pdf'

        # Convert bytes to string if needed for content detection
        if isinstance(content, bytes):
            # Check for PDF magic bytes
            if content.startswith(b'%PDF'):
                return 'pdf'
            # Check for Excel magic bytes
            if content.startswith(b'PK') or content.startswith(b'\xd0\xcf'):
                return 'excel'

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

    def _parse_excel_dictionary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Generic parser for Excel data dictionaries."""
        dictionary = {"columns": {}}

        # Map common column patterns to their semantic meaning
        column_patterns = {
            'name': ['variable', 'field', 'column', 'name', 'attribute', 'parameter', 'element'],
            'type': ['type', 'datatype', 'data_type', 'dtype', 'format', 'class'],
            'description': ['description', 'label', 'definition', 'comment', 'notes', 'meaning', 'prompt', 'question'],
            'choices': ['choices', 'values', 'options', 'allowed', 'valid', 'enum', 'list', 'responses', 'response'],
            'min': ['min', 'minimum', 'lower', 'low', 'floor'],
            'max': ['max', 'maximum', 'upper', 'high', 'ceiling'],
            'required': ['required', 'mandatory', 'nullable', 'optional'],
            'validation': ['validation', 'constraint', 'rule', 'check', 'format'],
            'length': ['length', 'size', 'width', 'max_length', 'maxlength'],
            'default': ['default', 'initial', 'preset'],
            'unique': ['unique', 'distinct', 'key', 'identifier'],
            'pattern': ['pattern', 'regex', 'regexp', 'expression', 'mask']
        }

        # Identify which columns map to what semantic meaning
        column_mapping = {}
        for col in df.columns:
            col_lower = col.lower().strip()
            for semantic_key, patterns in column_patterns.items():
                if any(pattern in col_lower for pattern in patterns):
                    # Prioritize more specific matches
                    if semantic_key not in column_mapping or len(col_lower) < len(column_mapping[semantic_key].lower()):
                        column_mapping[semantic_key] = col
                    break

        self.logger.info(f"Column mapping detected: {column_mapping}")

        # If no name column found, try to use the first column
        if 'name' not in column_mapping and len(df.columns) > 0:
            column_mapping['name'] = df.columns[0]
            self.logger.info(f"Using first column '{df.columns[0]}' as field name")

        # Parse each row as a field definition
        for _, row in df.iterrows():
            # Get field name
            field_name = None
            if 'name' in column_mapping:
                field_name_val = row.get(column_mapping['name'])
                if pd.notna(field_name_val):
                    field_name = str(field_name_val).strip()

            if not field_name:
                continue

            col_def = {}

            # Get type
            if 'type' in column_mapping:
                type_val = row.get(column_mapping['type'])
                if pd.notna(type_val):
                    col_def['type'] = self._normalize_type(str(type_val))

            # Get description
            if 'description' in column_mapping:
                desc_val = row.get(column_mapping['description'])
                if pd.notna(desc_val):
                    col_def['description'] = str(desc_val).strip()

            # Get allowed values/choices
            if 'choices' in column_mapping:
                choices_val = row.get(column_mapping['choices'])
                if pd.notna(choices_val):
                    parsed_choices = self._parse_choices(str(choices_val))
                    if parsed_choices:
                        col_def['allowed_values'] = parsed_choices
                        # If we have allowed values, it's likely categorical
                        if not col_def.get('type') or col_def.get('type') == 'string':
                            # Check if values are numeric codes
                            if all(c[0].isdigit() or c.startswith('-') for c in str(choices_val).split(';') if c.strip()):
                                col_def['type'] = 'categorical_numeric'
                            else:
                                col_def['type'] = 'categorical'

            # Get validation/constraints
            constraints = {}

            # Min value
            if 'min' in column_mapping:
                min_val = row.get(column_mapping['min'])
                if pd.notna(min_val):
                    try:
                        constraints['min_value'] = float(min_val)
                    except:
                        pass

            # Max value
            if 'max' in column_mapping:
                max_val = row.get(column_mapping['max'])
                if pd.notna(max_val):
                    try:
                        constraints['max_value'] = float(max_val)
                    except:
                        pass

            # Required field
            if 'required' in column_mapping:
                req_val = row.get(column_mapping['required'])
                if pd.notna(req_val):
                    req_str = str(req_val).lower().strip()
                    if req_str in ['y', 'yes', 'true', '1', 'required', 'mandatory']:
                        constraints['required'] = True
                    elif req_str in ['n', 'no', 'false', '0', 'optional']:
                        constraints['required'] = False

            # Length constraint
            if 'length' in column_mapping:
                length_val = row.get(column_mapping['length'])
                if pd.notna(length_val):
                    try:
                        constraints['max_length'] = int(length_val)
                    except:
                        pass

            # Pattern
            if 'pattern' in column_mapping:
                pattern_val = row.get(column_mapping['pattern'])
                if pd.notna(pattern_val):
                    constraints['pattern'] = str(pattern_val).strip()

            # Validation rules
            if 'validation' in column_mapping:
                val_val = row.get(column_mapping['validation'])
                if pd.notna(val_val):
                    validation = str(val_val).lower().strip()
                    # Try to infer type from validation
                    if not col_def.get('type'):
                        if 'int' in validation:
                            col_def['type'] = 'integer'
                        elif 'float' in validation or 'decimal' in validation or 'number' in validation:
                            col_def['type'] = 'float'
                        elif 'date' in validation:
                            col_def['type'] = 'datetime'
                        elif 'email' in validation:
                            constraints['pattern'] = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                        elif 'phone' in validation:
                            constraints['pattern'] = r'^[\d\s\-\(\)\+]+$'
                        elif 'url' in validation or 'website' in validation:
                            constraints['pattern'] = r'^https?://'

            # Unique constraint
            if 'unique' in column_mapping:
                unique_val = row.get(column_mapping['unique'])
                if pd.notna(unique_val):
                    unique_str = str(unique_val).lower().strip()
                    if unique_str in ['y', 'yes', 'true', '1', 'unique']:
                        constraints['unique'] = True

            # Default value
            if 'default' in column_mapping:
                default_val = row.get(column_mapping['default'])
                if pd.notna(default_val):
                    col_def['default'] = str(default_val)

            # Add constraints if any were found
            if constraints:
                col_def['constraints'] = constraints

            # If no type was determined, default to string
            if 'type' not in col_def:
                col_def['type'] = 'string'

            dictionary["columns"][field_name] = col_def

        return dictionary

    def _normalize_type(self, type_str: str) -> str:
        """Normalize various type representations to standard types."""
        type_lower = type_str.lower().strip()

        # Integer types
        if any(t in type_lower for t in ['int', 'integer', 'bigint', 'smallint', 'tinyint', 'long', 'number']):
            if 'float' not in type_lower and 'decimal' not in type_lower and 'double' not in type_lower:
                return 'integer'

        # Float/decimal types
        if any(t in type_lower for t in ['float', 'decimal', 'double', 'real', 'numeric', 'money', 'currency']):
            return 'float'

        # Boolean types
        if any(t in type_lower for t in ['bool', 'boolean', 'bit', 'yesno', 'truefalse', 'logical']):
            return 'boolean'

        # Date/time types
        if any(t in type_lower for t in ['date', 'time', 'timestamp', 'datetime', 'year', 'month']):
            return 'datetime'

        # String types
        if any(t in type_lower for t in ['str', 'string', 'text', 'char', 'varchar', 'nvarchar', 'clob', 'memo']):
            return 'string'

        # Categorical
        if any(t in type_lower for t in ['category', 'categorical', 'enum', 'choice', 'option', 'select', 'radio', 'dropdown', 'checkbox']):
            return 'categorical'

        # Default to string for unknown types
        return 'string'

    def _parse_choices(self, choices_str: str) -> list:
        """Parse various formats of choices/allowed values."""
        choices_str = choices_str.strip()

        # Special case: if it's just "text", return None (not a categorical field)
        if choices_str.lower() == 'text':
            return None

        choices = []

        # First check for semicolon-separated format (e.g., "0, Description;1, Another;...")
        if ';' in choices_str:
            parts = choices_str.split(';')
            for part in parts:
                part = part.strip()
                if not part:
                    continue

                # Check if it's "code, description" format
                if ',' in part:
                    # Split only on first comma to preserve descriptions with commas
                    subparts = part.split(',', 1)
                    if len(subparts) == 2:
                        code = subparts[0].strip()
                        desc = subparts[1].strip()
                        # Store both code and description as a tuple or just description
                        # For now, storing the full "code: description" for clarity
                        choices.append(f"{code}: {desc}")
                    else:
                        choices.append(part)
                else:
                    choices.append(part)

        # Try pipe-separated format
        elif '|' in choices_str:
            parts = choices_str.split('|')
            for part in parts:
                part = part.strip()
                if not part:
                    continue

                # Handle "key: value" format
                if ':' in part:
                    choices.append(part)
                elif ',' in part:
                    # Might be "1, Option 1" format
                    subparts = part.split(',', 1)
                    if len(subparts) > 1:
                        choices.append(f"{subparts[0].strip()}: {subparts[1].strip()}")
                    else:
                        choices.append(part)
                else:
                    choices.append(part)

        # Try comma-separated only if no semicolons or pipes
        elif ',' in choices_str and '\n' not in choices_str:
            # This might be a simple comma-separated list
            parts = choices_str.split(',')
            # Only treat as comma-separated if we have multiple items
            if len(parts) > 2:
                choices = [p.strip() for p in parts if p.strip()]
            else:
                # Might be a single "code, description" pair
                choices = [choices_str.strip()]

        # Try newline-separated
        elif '\n' in choices_str:
            lines = choices_str.split('\n')
            for line in lines:
                line = line.strip()
                if line:
                    choices.append(line)

        # If no separator found, treat as single choice (unless it's empty)
        elif choices_str and choices_str.lower() not in ['na', 'n/a', 'none']:
            choices = [choices_str]

        return choices if choices else None


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
        """Parse Excel format dictionary with multi-sheet support."""
        import io

        # Read all sheets
        excel_file = pd.ExcelFile(io.BytesIO(content))
        sheet_names = excel_file.sheet_names

        self.logger.info(f"Excel file contains {len(sheet_names)} sheets: {sheet_names}")

        # Try to find the data dictionary sheet
        dict_sheet = None
        dict_df = None

        # Common data dictionary sheet names (case-insensitive)
        common_dict_names = ['dictionary', 'data dictionary', 'data_dictionary', 'dict',
                            'metadata', 'schema', 'codebook', 'variables', 'fields',
                            'field_definitions', 'column_definitions', 'columns',
                            'data_model', 'datamodel', 'spec', 'specification']

        # First, try to find by sheet name
        for sheet_name in sheet_names:
            sheet_lower = sheet_name.lower().strip()
            if any(dict_name in sheet_lower for dict_name in common_dict_names):
                dict_sheet = sheet_name
                self.logger.info(f"Found dictionary sheet by name: {sheet_name}")
                break

        # If no obvious dictionary sheet, check each sheet's content
        if dict_sheet is None:
            for sheet_name in sheet_names:
                df = pd.read_excel(excel_file, sheet_name=sheet_name)

                if df.empty or len(df) == 0:
                    continue

                # Check if this looks like a data dictionary
                # Look for common dictionary column headers
                common_headers = ['field', 'variable', 'column', 'field_name', 'variable_name',
                                'type', 'data_type', 'datatype', 'field_type',
                                'description', 'label', 'field_label',
                                'choices', 'values', 'allowed_values', 'validation']

                df_columns_lower = [col.lower().strip() for col in df.columns]
                matches = sum(1 for header in common_headers if any(header in col for col in df_columns_lower))

                # If we have at least 2 matching headers, likely a dictionary
                if matches >= 2:
                    dict_sheet = sheet_name
                    dict_df = df
                    self.logger.info(f"Found dictionary sheet by content analysis: {sheet_name}")
                    break

        # If still no dictionary found, use the first non-empty sheet
        if dict_sheet is None:
            for sheet_name in sheet_names:
                df = pd.read_excel(excel_file, sheet_name=sheet_name)
                if not df.empty and len(df) > 0:
                    dict_sheet = sheet_name
                    dict_df = df
                    self.logger.warning(f"No clear dictionary sheet found, using first non-empty sheet: {sheet_name}")
                    break

        # Load the identified sheet if not already loaded
        if dict_df is None and dict_sheet:
            dict_df = pd.read_excel(excel_file, sheet_name=dict_sheet)

        if dict_df is None or dict_df.empty:
            raise ValueError("Could not find valid data dictionary in Excel file")

        # Use generic Excel dictionary parser
        return self._parse_excel_dictionary(dict_df)

    def _parse_pdf(self, content: bytes) -> Dict[str, Any]:
        """Parse PDF format dictionary using text extraction."""
        try:
            import PyPDF2
            import io

            pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text()

            # Parse extracted text
            return self._parse_text_with_llm(text)
        except ImportError:
            # If PyPDF2 not available, try basic text extraction
            self.logger.warning("PyPDF2 not available, using basic text extraction")
            text = content.decode('utf-8', errors='ignore')
            return self._parse_text_with_llm(text)
        except Exception as e:
            self.logger.error(f"Error parsing PDF: {e}")
            # Fallback to text parsing
            return self._parse_text_with_llm(str(content))

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