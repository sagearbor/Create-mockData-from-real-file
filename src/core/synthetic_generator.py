"""Synthetic data generation using LLM and metadata."""

import json
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Union
import tempfile
import subprocess
import sys
from pathlib import Path
import ast
import io

from src.utils.logger import logger
from src.utils.config import settings


class SyntheticDataGenerator:
    """Generate synthetic data based on metadata using LLM."""
    
    def __init__(self, openai_client=None):
        """
        Initialize the generator.
        
        Args:
            openai_client: Optional OpenAI client instance
        """
        self.logger = logger
        self.openai_client = openai_client
        
    def generate(
        self, 
        metadata: Dict[str, Any], 
        num_rows: Optional[int] = None,
        match_threshold: float = 0.8,
        use_cached: bool = True
    ) -> pd.DataFrame:
        """
        Generate synthetic data based on metadata.
        
        Args:
            metadata: Metadata dictionary from MetadataExtractor
            num_rows: Number of rows to generate (defaults to original)
            match_threshold: How closely to match statistical properties (0-1)
            use_cached: Whether to use cached generation scripts
            
        Returns:
            Generated synthetic DataFrame
        """
        self.logger.info(f"Starting synthetic data generation with match_threshold={match_threshold}")
        
        # Determine number of rows
        if num_rows is None:
            num_rows = metadata["structure"]["shape"]["rows"]
        
        # Generate the Python code using LLM
        generation_code = self._generate_code_with_llm(metadata, num_rows, match_threshold)
        
        # Execute the code safely
        synthetic_df = self._execute_generation_code(generation_code)
        
        # Validate the generated data
        if self._validate_synthetic_data(synthetic_df, metadata):
            self.logger.info(f"Successfully generated synthetic data with shape {synthetic_df.shape}")
            return synthetic_df
        else:
            self.logger.warning("Validation failed, regenerating with stricter parameters")
            # Try again with stricter threshold
            generation_code = self._generate_code_with_llm(metadata, num_rows, min(match_threshold + 0.1, 1.0))
            synthetic_df = self._execute_generation_code(generation_code)
            return synthetic_df
    
    def _generate_code_with_llm(self, metadata: Dict[str, Any], num_rows: int, match_threshold: float) -> str:
        """
        Generate Python code using LLM based on metadata.
        
        Args:
            metadata: Metadata dictionary
            num_rows: Number of rows to generate
            match_threshold: Statistical matching threshold
            
        Returns:
            Python code string for generating synthetic data
        """
        # Construct the prompt
        prompt = self._construct_generation_prompt(metadata, num_rows, match_threshold)
        
        if self.openai_client:
            # Use actual OpenAI API
            try:
                response = self.openai_client.chat.completions.create(
                    model=settings.azure_openai_chat_deployment,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=4000
                )

                code = response.choices[0].message.content
            except Exception as e:
                self.logger.warning(f"Azure OpenAI call failed: {e}. Using fallback generation.")
                return self._generate_fallback_code(metadata, num_rows)
            
            # Extract code from markdown if present
            if "```python" in code:
                code = code.split("```python")[1].split("```")[0]
            elif "```" in code:
                code = code.split("```")[1].split("```")[0]
            
            return code.strip()
        else:
            # Fallback to template-based generation when no LLM available
            return self._generate_fallback_code(metadata, num_rows)
    
    def _get_system_prompt(self) -> str:
        """Get the system prompt for code generation."""
        return """You are a Python code generator specialized in creating synthetic data.
        Generate complete, executable Python code that creates a pandas DataFrame with synthetic data.
        The code should:
        1. Import necessary libraries (pandas, numpy, random, datetime, etc.)
        2. Define a function called generate_synthetic_data() that returns a pandas DataFrame
        3. Match the statistical properties and patterns described in the metadata
        4. Use appropriate distributions for numeric data
        5. Maintain correlations between columns where specified
        6. Generate realistic patterns for string data
        7. When clinical_context or suggested_values are provided, use those specific values
        8. For medical columns (medications, lab tests, etc.), use the suggested clinical values
        9. CRITICAL: For categorical columns where 'preserve_values' is True and 'most_common_values' contains actual values (not 'value_0', 'value_1'), you MUST use those exact values with their distributions
        10. CRITICAL: For columns with type='datetime', you MUST generate datetime objects like: pd.date_range('2024-01-01', periods=num_rows, freq='D')
        11. For any column with 'date' or 'time' in the name, generate dates not random strings
        12. When you see actual categorical values like 'M', 'F' or 'Male', 'Female' in most_common_values, use those exact values
        13. Return ONLY the Python code, no explanations or markdown formatting
        """
    
    def _construct_generation_prompt(self, metadata: Dict[str, Any], num_rows: int, match_threshold: float) -> str:
        """Construct the prompt for LLM code generation."""

        # Check if there are dictionary constraints
        constraints_text = ""
        if "generation_constraints" in metadata:
            constraints_text = f"""
        DATA DICTIONARY CONSTRAINTS (MUST BE FOLLOWED):
        {metadata['generation_constraints']}
        """

        prompt = f"""Generate Python code to create a synthetic dataset with {num_rows} rows.

        The dataset should have the following structure and properties:

        COLUMNS:
        {json.dumps(metadata['structure']['columns'], indent=2)}

        STATISTICAL PROPERTIES:
        {json.dumps(metadata['statistics'], indent=2)}

        PATTERNS:
        {json.dumps(metadata.get('patterns', {}), indent=2)}

        CORRELATIONS:
        {json.dumps(metadata.get('correlations', {}), indent=2)}
        {constraints_text}

        Match threshold: {match_threshold} (0=loose match, 1=exact match)

        Generate complete Python code that:
        1. Creates a function generate_synthetic_data() that returns a pandas DataFrame
        2. Matches the statistical properties within {(1-match_threshold)*20}% margin
        3. Preserves data types and patterns
        4. Maintains correlations between columns
        5. Generates realistic synthetic values
        6. CRITICAL: When 'preserve_values' is True for a column, use the EXACT values from 'most_common_values' with their distributions
        7. IMPORTANT: For columns with type='datetime', generate proper datetime objects using datetime.now() or pd.date_range()
        8. For date columns with names containing 'date', 'time', 'created', 'updated', generate datetime values
        9. CRITICAL: If DATA DICTIONARY CONSTRAINTS are provided above, they MUST override any statistical properties
        10. For categorical columns with actual values (not 'value_0', 'value_1'), maintain the exact distribution

        Return only the Python code."""

        return prompt
    
    def _generate_fallback_code(self, metadata: Dict[str, Any], num_rows: int) -> str:
        """Generate synthetic data using template-based approach (fallback when no LLM)."""

        code_lines = [
            "import pandas as pd",
            "import numpy as np",
            "import random",
            "from datetime import datetime, timedelta",
            "import string",
            "",
            "def generate_synthetic_data():",
            f"    num_rows = {num_rows}",
            "    data = {}",
            "",
            "    # Helper functions for realistic data",
            "    def generate_email(name):",
            "        domains = ['gmail.com', 'yahoo.com', 'outlook.com', 'email.com', 'company.com']",
            "        username = name.lower().replace(' ', '.') + str(random.randint(0, 99))",
            "        return f'{username}@{random.choice(domains)}'",
            "",
            "    def generate_phone(format_type='dash'):",
            "        if format_type == 'dash':",
            "            return f'{random.randint(200, 999)}-{random.randint(200, 999)}-{random.randint(1000, 9999)}'",
            "        elif format_type == 'simple':",
            "            return f'{random.randint(555, 999)}-{random.randint(1000, 9999)}'",
            "        elif format_type == 'dot':",
            "            return f'{random.randint(200, 999)}.{random.randint(200, 999)}.{random.randint(1000, 9999)}'",
            "        else:",
            "            return f'({random.randint(200, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}'",
            ""
        ]
        
        # Generate code for each column
        for col_info in metadata['structure']['columns']:
            col_name = col_info['name']
            col_stats = metadata['statistics'].get(col_name, {})
            
            if col_stats.get('type') == 'numeric':
                # Check if this is currency/money
                if col_stats.get('is_likely_currency', False):
                    decimal_places = col_stats.get('decimal_places', 2) or 2  # Default to 2 if None
                    min_val = col_stats.get('min', 0)
                    max_val = col_stats.get('max', 10000)
                    code_lines.append(f"    # Generating currency values for '{col_name}'")
                    code_lines.append(f"    data['{col_name}'] = np.round(np.random.uniform({min_val}, {max_val}, size=num_rows), {decimal_places})")
                # Regular numeric column generation
                elif col_stats.get('is_integer', False):
                    min_val = int(col_stats.get('min', 0))
                    max_val = int(col_stats.get('max', 100))
                    code_lines.append(f"    data['{col_name}'] = np.random.randint({min_val}, {max_val + 1}, size=num_rows)")
                else:
                    mean = col_stats.get('mean', 0)
                    std = col_stats.get('std', 1)
                    code_lines.append(f"    data['{col_name}'] = np.random.normal({mean}, {std}, size=num_rows)")

                    # Clip to min/max if specified
                    if 'min' in col_stats and 'max' in col_stats:
                        code_lines.append(f"    data['{col_name}'] = np.clip(data['{col_name}'], {col_stats['min']}, {col_stats['max']})")
            
            elif col_stats.get('type') == 'string':
                # First check if this is a datetime stored as string (detected from data)
                if col_stats.get('is_datetime_string', False):
                    datetime_format = col_stats.get('datetime_format', '%Y-%m-%d %H:%M:%S')
                    code_lines.append(f"    # Detected datetime string format: {datetime_format}")
                    code_lines.append(f"    base_date = datetime.now()")
                    code_lines.append(f"    date_list = [base_date - timedelta(days=random.randint(0, 365), hours=random.randint(0, 23), minutes=random.randint(0, 59)) for _ in range(num_rows)]")
                    if '%H' in datetime_format:  # Has time component
                        code_lines.append(f"    data['{col_name}'] = [d.strftime('{datetime_format}') for d in date_list]")
                    else:
                        code_lines.append(f"    data['{col_name}'] = [d.strftime('%Y-%m-%d') for d in date_list]")
                # Fallback: Check if column name suggests date
                elif any(keyword in col_name.lower() for keyword in ['date', 'time', 'created', 'updated', 'modified', 'dob', 'timestamp']):
                    # Generate dates even if stored as string
                    code_lines.append(f"    # Detected '{col_name}' as likely date column")
                    code_lines.append(f"    base_date = datetime.now()")
                    code_lines.append(f"    date_list = [base_date - timedelta(days=random.randint(0, 365)) for _ in range(num_rows)]")
                    code_lines.append(f"    data['{col_name}'] = [d.strftime('%Y-%m-%d') for d in date_list]")
                # Check for categorical values
                elif col_stats.get('is_categorical', False) or col_stats.get('unique_values', 100) <= 10:
                    # Check if we have preserved actual categorical values
                    if col_stats.get('preserve_values', False) and 'most_common_values' in col_stats:
                        most_common = col_stats['most_common_values']
                        # Check if these are actual values (not anonymized)
                        if not any(k.startswith('value_') for k in most_common.keys()):
                            # Use actual values with their distributions
                            values = list(most_common.keys())
                            counts = list(most_common.values())
                            # Normalize to probabilities
                            total = sum(counts)
                            probabilities = [c/total for c in counts]
                            code_lines.append(f"    # Using preserved categorical values for '{col_name}'")
                            code_lines.append(f"    categories_{col_name} = {values}")
                            code_lines.append(f"    probabilities_{col_name} = {probabilities}")
                            code_lines.append(f"    data['{col_name}'] = np.random.choice(categories_{col_name}, size=num_rows, p=probabilities_{col_name})")
                        else:
                            # Fallback to generic categories if anonymized
                            unique_count = min(col_stats.get('unique_values', 10), 20)
                            code_lines.append(f"    categories_{col_name} = [f'Category_{{i}}' for i in range({unique_count})]")
                            code_lines.append(f"    data['{col_name}'] = np.random.choice(categories_{col_name}, size=num_rows)")
                    else:
                        # No preserved values, use generic categories
                        unique_count = min(col_stats.get('unique_values', 10), 20)
                        code_lines.append(f"    categories_{col_name} = [f'Category_{{i}}' for i in range({unique_count})]")
                        code_lines.append(f"    data['{col_name}'] = np.random.choice(categories_{col_name}, size=num_rows)")
                else:
                    # Check for specific detected types and patterns
                    patterns = metadata.get('patterns', {}).get(col_name, {})

                    # Check for email detection
                    if col_stats.get('detected_type') == 'email' or col_stats.get('is_email_like'):
                        code_lines.append(f"    # Generating emails for '{col_name}'")
                        code_lines.append(f"    data['{col_name}'] = [generate_email(f'user{{i}}') for i in range(num_rows)]")

                    # Check for phone detection
                    elif col_stats.get('detected_type') == 'phone' or col_stats.get('is_phone_like'):
                        phone_format = col_stats.get('phone_format', 'dash')
                        code_lines.append(f"    # Generating phone numbers for '{col_name}'")
                        code_lines.append(f"    data['{col_name}'] = [generate_phone('{phone_format}') for _ in range(num_rows)]")

                    # Check for ID pattern with prefix
                    elif patterns.get('id_pattern', {}).get('type') == 'prefix_sequential':
                        prefix = patterns['id_pattern']['prefix']
                        code_lines.append(f"    # Generating IDs with prefix '{prefix}' for '{col_name}'")
                        code_lines.append(f"    data['{col_name}'] = [f'{prefix}{{str(i+1).zfill(3)}}' for i in range(num_rows)]")

                    # Check for suggested values from clinical/reference context
                    elif 'clinical_context' in col_stats or 'suggested_values' in col_stats:
                        suggested = col_stats.get('suggested_values', col_stats.get('clinical_context', {}).get('suggested_values', []))
                        if suggested:
                            code_lines.append(f"    # Using suggested values for '{col_name}'")
                            code_lines.append(f"    suggested_{col_name} = {suggested}")
                            code_lines.append(f"    data['{col_name}'] = [random.choice(suggested_{col_name}) for _ in range(num_rows)]")
                        else:
                            # Fallback to random strings
                            avg_length = int(col_stats.get('avg_length', 10))
                            code_lines.append(f"    data['{col_name}'] = [''.join(random.choices(string.ascii_letters + string.digits, k={avg_length})) for _ in range(num_rows)]")

                    # Check if column name suggests specific data type
                    elif 'city' in col_name.lower():
                        code_lines.append(f"    # Generating city names for '{col_name}'")
                        cities = ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose"]
                        code_lines.append(f"    cities = {cities}")
                        code_lines.append(f"    data['{col_name}'] = [random.choice(cities) for _ in range(num_rows)]")

                    elif 'name' in col_name.lower() and 'first' not in col_name.lower() and 'last' not in col_name.lower():
                        code_lines.append(f"    # Generating full names for '{col_name}'")
                        first_names = ["John", "Jane", "Bob", "Alice", "Charlie", "Mary", "Michael", "Sarah", "David", "Emily"]
                        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]
                        code_lines.append(f"    first_names = {first_names}")
                        code_lines.append(f"    last_names = {last_names}")
                        code_lines.append(f"    data['{col_name}'] = [f'{{random.choice(first_names)}} {{random.choice(last_names)}}' for _ in range(num_rows)]")

                    else:
                        # Default random strings
                        avg_length = int(col_stats.get('avg_length', 10))
                        code_lines.append(f"    data['{col_name}'] = [''.join(random.choices(string.ascii_letters + string.digits, k={avg_length})) for _ in range(num_rows)]")
            
            elif col_stats.get('type') == 'datetime':
                # DateTime column generation
                code_lines.append(f"    base_date = datetime.now()")
                code_lines.append(f"    data['{col_name}'] = [base_date - timedelta(days=random.randint(0, 365)) for _ in range(num_rows)]")
            
            else:
                # Default to None
                code_lines.append(f"    data['{col_name}'] = [None] * num_rows")
            
            # Add null values if needed
            if col_info.get('nullable', False) and col_info.get('null_count', 0) > 0:
                null_percentage = col_info['null_count'] / metadata['structure']['shape']['rows']
                code_lines.append(f"    # Add null values")
                code_lines.append(f"    null_mask = np.random.random(num_rows) < {null_percentage}")
                code_lines.append(f"    data['{col_name}'] = pd.Series(data['{col_name}'])")
                code_lines.append(f"    data['{col_name}'][null_mask] = None")
            
            code_lines.append("")
        
        code_lines.extend([
            "    df = pd.DataFrame(data)",
            "    return df",
            "",
            "# Generate the data",
            "result = generate_synthetic_data()"
        ])
        
        return "\n".join(code_lines)
    
    def _execute_generation_code(self, code: str) -> pd.DataFrame:
        """
        Safely execute the generated Python code.
        
        Args:
            code: Python code string
            
        Returns:
            Generated DataFrame
        """
        self.logger.info("Executing generated code in sandbox")
        
        # Create a temporary file for the code
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            f.write("\n\n# Save result\nresult.to_pickle('synthetic_data.pkl')")
            temp_file = f.name
        
        try:
            # Execute in subprocess for safety
            with tempfile.TemporaryDirectory() as temp_dir:
                pickle_path = Path(temp_dir) / "synthetic_data.pkl"
                
                # Modify code to save to specific path
                modified_code = code.replace(
                    "result.to_pickle('synthetic_data.pkl')",
                    f"result.to_pickle('{pickle_path}')"
                )
                
                # Write modified code
                code_path = Path(temp_dir) / "generator.py"
                code_path.write_text(modified_code + f"\nresult.to_pickle('{pickle_path}')")
                
                # Execute the code
                result = subprocess.run(
                    [sys.executable, str(code_path)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=temp_dir
                )
                
                if result.returncode != 0:
                    self.logger.error(f"Code execution failed: {result.stderr}")
                    # Try to execute directly as fallback
                    return self._execute_code_directly(code)
                
                # Load the generated data
                if pickle_path.exists():
                    df = pd.read_pickle(pickle_path)
                    return df
                else:
                    # Fallback to direct execution
                    return self._execute_code_directly(code)
                    
        except subprocess.TimeoutExpired:
            self.logger.error("Code execution timeout")
            raise ValueError("Code execution took too long")
        except Exception as e:
            self.logger.error(f"Code execution error: {e}")
            # Try direct execution as last resort
            return self._execute_code_directly(code)
        finally:
            # Clean up temp file
            if Path(temp_file).exists():
                Path(temp_file).unlink()
    
    def _execute_code_directly(self, code: str) -> pd.DataFrame:
        """Execute code directly in current process (less safe but works as fallback)."""
        self.logger.warning("Executing code directly (fallback mode)")
        
        # Create a restricted namespace
        namespace = {
            'pd': pd,
            'np': np,
            'random': __import__('random'),
            'datetime': __import__('datetime').datetime,
            'timedelta': __import__('datetime').timedelta,
            'string': __import__('string'),
            '__builtins__': {
                'range': range,
                'len': len,
                'int': int,
                'float': float,
                'str': str,
                'list': list,
                'dict': dict,
                'min': min,
                'max': max,
                'sum': sum,
                'zip': zip,
                'enumerate': enumerate
            }
        }
        
        try:
            # Execute the code
            exec(code, namespace)
            
            # Get the result
            if 'result' in namespace:
                return namespace['result']
            elif 'generate_synthetic_data' in namespace:
                return namespace['generate_synthetic_data']()
            else:
                raise ValueError("No result found in generated code")
                
        except Exception as e:
            self.logger.error(f"Direct execution failed: {e}")
            raise
    
    def _validate_synthetic_data(self, df: pd.DataFrame, metadata: Dict[str, Any]) -> bool:
        """
        Validate that synthetic data matches expected structure.
        
        Args:
            df: Generated DataFrame
            metadata: Original metadata
            
        Returns:
            True if validation passes
        """
        try:
            # Check column count
            expected_cols = len(metadata['structure']['columns'])
            if len(df.columns) != expected_cols:
                self.logger.warning(f"Column count mismatch: expected {expected_cols}, got {len(df.columns)}")
                return False
            
            # Check column names
            expected_names = [col['name'] for col in metadata['structure']['columns']]
            missing_cols = set(expected_names) - set(df.columns)
            if missing_cols:
                self.logger.warning(f"Missing columns: {missing_cols}")
                return False
            
            # Basic validation passed
            return True
            
        except Exception as e:
            self.logger.error(f"Validation error: {e}")
            return False