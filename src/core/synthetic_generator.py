"""Synthetic data generation using LLM and metadata."""

import json
import math
import os
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Union, Tuple
import re
import tempfile
import subprocess
import sys
from pathlib import Path
import ast
import io
import time
from datetime import datetime

from src.utils.logger import logger
from src.utils.config import settings
from src.core.cache_manager import CacheManager

# HARD RULE: reasoning models (gpt-5.x, o-series) spend thinking tokens out of the
# completion budget; never cap them below 32000. 40000 is the DCRI default.
LLM_MAX_COMPLETION_TOKENS = 40000
_REASONING_MODEL_RE = re.compile(r"^(gpt-5|o\d)", re.I)


class LLMOutputError(RuntimeError):
    """The LLM call returned but its output is unusable (truncated or empty)."""


# Characters allowed to survive into a generated comment. Anything else (most
# importantly newlines, which would end the comment and start a new statement)
# is replaced, so an untrusted column name can never break out of a comment.
_COMMENT_SAFE_PATTERN = re.compile(r"[^\w .,:;/@+-]", re.UNICODE)


def _to_plain_python(value: Any) -> Any:
    """Coerce a metadata value to plain built-in types.

    numpy scalars repr() as expressions such as ``np.str_('x')`` that are not
    valid on their own, so they are unwrapped before a literal is emitted.
    """
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, (str, bool, int, type(None))):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, (list, tuple, set, np.ndarray)):
        return [_to_plain_python(item) for item in value]
    if isinstance(value, dict):
        return {_to_plain_python(k): _to_plain_python(v) for k, v in value.items()}
    return str(value)


def py_literal(value: Any) -> str:
    """Render an untrusted metadata value as a self-contained Python literal.

    Every value that reaches the generated source (column names, cell values,
    detected formats, statistics) originates in a user-supplied file. Emitting
    them with repr() instead of interpolating them as raw text is what keeps a
    CSV header from becoming executable code.
    """
    plain = _to_plain_python(value)

    # repr(float('nan')) is 'nan', which is not a valid expression on its own.
    if isinstance(plain, float) and not math.isfinite(plain):
        return f"float({repr(str(plain))})"

    return repr(plain)


def safe_comment(value: Any, max_length: int = 60) -> str:
    """Render an untrusted value as text that is safe inside a ``#`` comment."""
    text = _COMMENT_SAFE_PATTERN.sub("?", str(value))
    if len(text) > max_length:
        text = text[:max_length] + "..."
    return text


class SyntheticDataGenerator:
    """Generate synthetic data based on metadata using LLM."""

    def __init__(self, openai_client=None):
        """
        Initialize the generator.

        Args:
            openai_client: Optional OpenAI client instance
        """
        self.logger = logger
        self.cache_manager = CacheManager()
        self.openai_client = openai_client
        
    def generate(
        self,
        metadata: Dict[str, Any],
        num_rows: Optional[int] = None,
        match_threshold: float = 0.8,
        use_cached: bool = True
    ) -> tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Generate synthetic data based on metadata.

        Args:
            metadata: Metadata dictionary from MetadataExtractor
            num_rows: Number of rows to generate (defaults to original)
            match_threshold: How closely to match statistical properties (0-1)
            use_cached: Whether to use cached generation scripts

        Returns:
            Tuple of (Generated synthetic DataFrame, generation_info dict)
        """
        self.logger.info(f"Starting synthetic data generation with match_threshold={match_threshold}")

        # Track timing for each step
        step_timings = {}
        total_start = time.time()

        # Determine number of rows
        if num_rows is None:
            num_rows = metadata["structure"]["shape"]["rows"]

        # Check cache first if enabled
        cache_check_time = 0
        if use_cached:
            cache_start = time.time()
            try:
                cached_entry = self.cache_manager.find_similar_cached(metadata, match_threshold=0.95)
                cache_check_time = time.time() - cache_start
                step_timings['cache_check'] = cache_check_time

                if cached_entry:
                    self.logger.info(f"Cache hit! Using cached code (check took {cache_check_time:.3f}s)")
                    generation_code = cached_entry['generation_code']
                    generation_method = 'cached'
                    step_timings['llm_response'] = 0  # No LLM call needed
                else:
                    self.logger.info(f"No cache hit (check took {cache_check_time:.3f}s)")
                    generation_code = None
            except Exception as e:
                self.logger.warning(f"Cache check failed: {e}")
                generation_code = None
        else:
            step_timings['cache_check'] = 0
            generation_code = None

        # Generate code if not cached
        llm_error = None
        if generation_code is None:
            code_gen_start = time.time()
            generation_code, generation_method, llm_response_time, llm_error = self._generate_code_with_llm(
                metadata, num_rows, match_threshold, operation="generate_code")
            # Only track llm_response time (code_generation is redundant as it's the same)
            if llm_response_time:
                step_timings['llm_response'] = llm_response_time
            else:
                # Track time even if no LLM was called
                if generation_method != 'cached':
                    step_timings['llm_response'] = time.time() - code_gen_start
        else:
            # Cache hit - already set llm_response to 0 above
            pass
        
        # Execute the code safely
        exec_start = time.time()
        synthetic_df = self._execute_generation_code(generation_code)
        step_timings['code_execution'] = time.time() - exec_start
        
        # Validate the generated data
        validation_start = time.time()
        validation_passed = self._validate_synthetic_data(synthetic_df, metadata)
        step_timings['validation'] = time.time() - validation_start

        # Total time
        step_timings['total'] = time.time() - total_start

        # Create generation info with timing
        generation_info = {
            "method": generation_method,
            "num_rows": num_rows,
            "match_threshold": match_threshold,
            "use_cached": use_cached,
            "step_timings": step_timings
        }
        if llm_error:
            # Surface AI failures (auth, truncation, empty output) instead of
            # passing the template fallback off as a normal LLM result.
            generation_info["llm_error"] = llm_error

        # Log usage for analytics
        self._log_usage(generation_method, metadata, num_rows, step_timings)

        if validation_passed:
            self.logger.info(f"Successfully generated synthetic data with shape {synthetic_df.shape}")
            return synthetic_df, generation_info
        else:
            self.logger.warning("Validation failed, regenerating with stricter parameters")
            # Try again with stricter threshold
            generation_code, generation_method, _, llm_error = self._generate_code_with_llm(
                metadata, num_rows, min(match_threshold + 0.1, 1.0), operation="regenerate_code")
            synthetic_df = self._execute_generation_code(generation_code)
            generation_info["method"] = generation_method
            generation_info["regenerated"] = True
            if llm_error:
                generation_info["llm_error"] = llm_error
            return synthetic_df, generation_info
    
    def _generate_code_with_llm(
        self,
        metadata: Dict[str, Any],
        num_rows: int,
        match_threshold: float,
        operation: str = "generate_code",
    ) -> Tuple[str, str, Optional[float], Optional[str]]:
        """
        Generate Python code using LLM based on metadata.

        Args:
            metadata: Metadata dictionary
            num_rows: Number of rows to generate
            match_threshold: Statistical matching threshold
            operation: Stable telemetry name for this call (dcri_llm ``operation``)

        Returns:
            Tuple of (code, generation method, LLM seconds or None, llm_error or None).
            ``llm_error`` is a short, content-free reason when an AI call was
            attempted but the template fallback was used instead.
        """
        # Construct the prompt
        prompt = self._construct_generation_prompt(metadata, num_rows, match_threshold)

        if not self.openai_client:
            # Fallback to template-based generation when no LLM available
            self.logger.warning("No OpenAI client available, using fallback template-based generation")
            code, generation_method = self._generate_fallback_code(metadata, num_rows)
            return code, generation_method, None, None

        from src.dcri_llm import llm_action  # lazy: keeps module import light

        model = settings.azure_openai_chat_deployment
        request: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": prompt},
            ],
            "max_completion_tokens": LLM_MAX_COMPLETION_TOKENS,
        }
        if not _REASONING_MODEL_RE.match(model or ""):
            # Reasoning models only accept the default temperature.
            request["temperature"] = 0.3

        try:
            self.logger.info(f"Calling Azure OpenAI with model: {model}")
            self.logger.debug(f"Prompt length: {len(prompt)} characters")

            llm_start = time.time()
            with llm_action(operation):
                response = self.openai_client.chat.completions.create(**request)
            llm_response_time = time.time() - llm_start

            choice = response.choices[0] if response.choices else None
            finish_reason = getattr(choice, "finish_reason", None)
            code = (choice.message.content if choice and choice.message else None) or ""
            if finish_reason == "length":
                raise LLMOutputError("finish_reason=length (output truncated at token budget)")
            if not code.strip():
                raise LLMOutputError(f"empty output (finish_reason={finish_reason})")

            generation_method = "llm"
            self.logger.info(f"Successfully received LLM response ({len(code)} characters) in {llm_response_time:.2f}s")
        except Exception as e:
            # Log the error type/status only: provider messages can echo request content.
            status = getattr(e, "status_code", None)
            reason = str(e) if isinstance(e, LLMOutputError) else type(e).__name__
            if status:
                reason = f"{reason} (HTTP {status})"
            self.logger.error(f"Azure OpenAI call failed: {reason}")
            self.logger.warning("Falling back to template-based generation")
            code, generation_method = self._generate_fallback_code(metadata, num_rows)
            return code, generation_method, None, f"AI generation failed, used template fallback: {reason}"

        # Cache the generated code (only usable LLM output reaches here)
        try:
            self.cache_manager.cache_generation(metadata, code)
            self.logger.info("Cached generation code for future use")
        except Exception as e:
            self.logger.warning(f"Failed to cache: {type(e).__name__}")

        # Extract code from markdown if present
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0]
        elif "```" in code:
            code = code.split("```")[1].split("```")[0]

        return code.strip(), generation_method, llm_response_time, None

    def _get_system_prompt(self) -> str:
        """Get the system prompt for code generation."""
        return """You are a Python code generator specialized in creating synthetic data.
        Generate complete, executable Python code that creates a pandas DataFrame with synthetic data.
        The code should:
        1. Import necessary libraries (pandas, numpy, random, datetime, etc.)
        2. Define a function called generate_synthetic_data() that returns a pandas DataFrame
        3. IMPORTANT: After defining the function, call it and assign to 'result' variable: result = generate_synthetic_data()
        4. Match the statistical properties and patterns described in the metadata
        5. Use appropriate distributions for numeric data
        6. Maintain correlations between columns where specified
        7. Generate realistic patterns for string data
        8. When clinical_context or suggested_values are provided, use those specific values
        9. For medical columns (medications, lab tests, etc.), use the suggested clinical values
        10. CRITICAL: For categorical columns where 'preserve_values' is True and 'most_common_values' contains actual values (not 'value_0', 'value_1'), you MUST use those exact values with their distributions
        11. CRITICAL: For columns with type='datetime', you MUST generate datetime objects like: pd.date_range('2024-01-01', periods=num_rows, freq='D')
        12. For any column with 'date' or 'time' in the name, generate dates not random strings
        13. When you see actual categorical values like 'M', 'F' or 'Male', 'Female' in most_common_values, use those exact values
        14. Return ONLY the Python code, no explanations or markdown formatting
        15. The code must end with: result = generate_synthetic_data()
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
    
    def _generate_fallback_code(self, metadata: Dict[str, Any], num_rows: int) -> tuple[str, str]:
        """Generate synthetic data using template-based approach (fallback when no LLM).

        Returns:
            Tuple of (Python code string, generation method 'fallback')
        """

        code_lines = [
            "import pandas as pd",
            "import numpy as np",
            "import random",
            "from datetime import datetime, timedelta",
            "import string",
            "",
            "def generate_synthetic_data():",
            f"    num_rows = {py_literal(int(num_rows))}",
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
        
        # Generate code for each column.
        #
        # SECURITY: column names, cell values and detected formats all come from
        # the user-supplied file. They are emitted with py_literal() (never
        # interpolated as raw source) and helper variables are named by column
        # index (never derived from the column name), so no part of the input
        # can reach executable position. See
        # tests/test_synthetic_generator_injection.py.
        for col_index, col_info in enumerate(metadata['structure']['columns']):
            col_name = col_info['name']
            col_stats = metadata['statistics'].get(col_name, {})

            col_lit = py_literal(col_name)
            col_label = safe_comment(col_name)
            target = f"data[{col_lit}]"

            if col_stats.get('type') == 'numeric':
                # Check if this is currency/money
                if col_stats.get('is_likely_currency', False):
                    decimal_places = col_stats.get('decimal_places', 2)
                    if decimal_places is None:
                        decimal_places = 2  # Default to 2 if None
                    min_val = col_stats.get('min', 0)
                    max_val = col_stats.get('max', 10000)
                    code_lines.append(f"    # Generating currency values for '{col_label}'")
                    code_lines.append(f"    {target} = np.round(np.random.uniform({py_literal(min_val)}, {py_literal(max_val)}, size=num_rows), {py_literal(int(decimal_places))})")
                # Regular numeric column generation
                elif col_stats.get('is_integer', False):
                    min_val = int(col_stats.get('min', 0))
                    max_val = int(col_stats.get('max', 100))
                    code_lines.append(f"    {target} = np.random.randint({py_literal(min_val)}, {py_literal(max_val + 1)}, size=num_rows)")
                else:
                    mean = col_stats.get('mean', 0)
                    std = col_stats.get('std', 1)
                    code_lines.append(f"    {target} = np.random.normal({py_literal(mean)}, {py_literal(std)}, size=num_rows)")

                    # Clip to min/max if specified
                    if 'min' in col_stats and 'max' in col_stats:
                        code_lines.append(f"    {target} = np.clip({target}, {py_literal(col_stats['min'])}, {py_literal(col_stats['max'])})")

            elif col_stats.get('type') == 'string':
                # First check if this is a datetime stored as string (detected from data)
                if col_stats.get('is_datetime_string', False):
                    datetime_format = col_stats.get('datetime_format') or '%Y-%m-%d %H:%M:%S'
                    code_lines.append(f"    # Detected datetime string format: {safe_comment(datetime_format)}")
                    code_lines.append(f"    base_date = datetime.now()")
                    code_lines.append(f"    date_list = [base_date - timedelta(days=random.randint(0, 365), hours=random.randint(0, 23), minutes=random.randint(0, 59)) for _ in range(num_rows)]")
                    if '%H' in datetime_format:  # Has time component
                        code_lines.append(f"    {target} = [d.strftime({py_literal(datetime_format)}) for d in date_list]")
                    else:
                        code_lines.append(f"    {target} = [d.strftime('%Y-%m-%d') for d in date_list]")
                # Fallback: Check if column name suggests date
                elif any(keyword in col_name.lower() for keyword in ['date', 'time', 'created', 'updated', 'modified', 'dob', 'timestamp']):
                    # Generate dates even if stored as string
                    code_lines.append(f"    # Detected '{col_label}' as likely date column")
                    code_lines.append(f"    base_date = datetime.now()")
                    code_lines.append(f"    date_list = [base_date - timedelta(days=random.randint(0, 365)) for _ in range(num_rows)]")
                    code_lines.append(f"    {target} = [d.strftime('%Y-%m-%d') for d in date_list]")
                # Check for categorical values
                elif col_stats.get('is_categorical', False) or col_stats.get('unique_values', 100) <= 10:
                    # Check if we have preserved actual categorical values
                    if col_stats.get('preserve_values', False) and 'most_common_values' in col_stats:
                        most_common = col_stats['most_common_values']
                        # Check if these are actual values (not anonymized)
                        if not any(str(k).startswith('value_') for k in most_common.keys()):
                            # Use actual values with their distributions
                            values = list(most_common.keys())
                            counts = list(most_common.values())
                            # Normalize to probabilities
                            total = sum(counts)
                            probabilities = [c/total for c in counts]
                            code_lines.append(f"    # Using preserved categorical values for '{col_label}'")
                            code_lines.append(f"    categories_{col_index} = {py_literal(values)}")
                            code_lines.append(f"    probabilities_{col_index} = {py_literal(probabilities)}")
                            code_lines.append(f"    {target} = np.random.choice(categories_{col_index}, size=num_rows, p=probabilities_{col_index})")
                        else:
                            # Fallback to generic categories if anonymized
                            unique_count = min(col_stats.get('unique_values', 10), 20)
                            code_lines.append(f"    categories_{col_index} = [f'Category_{{i}}' for i in range({py_literal(int(unique_count))})]")
                            code_lines.append(f"    {target} = np.random.choice(categories_{col_index}, size=num_rows)")
                    else:
                        # No preserved values, use generic categories
                        unique_count = min(col_stats.get('unique_values', 10), 20)
                        code_lines.append(f"    categories_{col_index} = [f'Category_{{i}}' for i in range({py_literal(int(unique_count))})]")
                        code_lines.append(f"    {target} = np.random.choice(categories_{col_index}, size=num_rows)")
                else:
                    # Check for specific detected types and patterns
                    patterns = metadata.get('patterns', {}).get(col_name, {})

                    # Check for email detection
                    if col_stats.get('detected_type') == 'email' or col_stats.get('is_email_like'):
                        code_lines.append(f"    # Generating emails for '{col_label}'")
                        code_lines.append(f"    {target} = [generate_email(f'user{{i}}') for i in range(num_rows)]")

                    # Check for phone detection
                    elif col_stats.get('detected_type') == 'phone' or col_stats.get('is_phone_like'):
                        phone_format = col_stats.get('phone_format', 'dash')
                        code_lines.append(f"    # Generating phone numbers for '{col_label}'")
                        code_lines.append(f"    {target} = [generate_phone({py_literal(phone_format)}) for _ in range(num_rows)]")

                    # Check for ID pattern with prefix
                    elif patterns.get('id_pattern', {}).get('type') == 'prefix_sequential':
                        prefix = patterns['id_pattern']['prefix']
                        code_lines.append(f"    # Generating IDs with prefix '{safe_comment(prefix)}' for '{col_label}'")
                        code_lines.append(f"    {target} = [{py_literal(prefix)} + str(i+1).zfill(3) for i in range(num_rows)]")

                    # Check for suggested values from clinical/reference context
                    elif 'clinical_context' in col_stats or 'suggested_values' in col_stats:
                        suggested = col_stats.get('suggested_values', col_stats.get('clinical_context', {}).get('suggested_values', []))
                        if suggested:
                            code_lines.append(f"    # Using suggested values for '{col_label}'")
                            code_lines.append(f"    suggested_{col_index} = {py_literal(suggested)}")
                            code_lines.append(f"    {target} = [random.choice(suggested_{col_index}) for _ in range(num_rows)]")
                        else:
                            # Fallback to random strings
                            avg_length = int(col_stats.get('avg_length', 10))
                            code_lines.append(f"    {target} = [''.join(random.choices(string.ascii_letters + string.digits, k={py_literal(avg_length)})) for _ in range(num_rows)]")

                    # Check if column name suggests specific data type
                    elif 'city' in col_name.lower():
                        code_lines.append(f"    # Generating city names for '{col_label}'")
                        cities = ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose"]
                        code_lines.append(f"    cities = {py_literal(cities)}")
                        code_lines.append(f"    {target} = [random.choice(cities) for _ in range(num_rows)]")

                    elif 'name' in col_name.lower() and 'first' not in col_name.lower() and 'last' not in col_name.lower():
                        code_lines.append(f"    # Generating full names for '{col_label}'")
                        first_names = ["John", "Jane", "Bob", "Alice", "Charlie", "Mary", "Michael", "Sarah", "David", "Emily"]
                        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]
                        code_lines.append(f"    first_names = {py_literal(first_names)}")
                        code_lines.append(f"    last_names = {py_literal(last_names)}")
                        code_lines.append(f"    {target} = [f'{{random.choice(first_names)}} {{random.choice(last_names)}}' for _ in range(num_rows)]")

                    else:
                        # Default random strings
                        avg_length = int(col_stats.get('avg_length', 10))
                        code_lines.append(f"    {target} = [''.join(random.choices(string.ascii_letters + string.digits, k={py_literal(avg_length)})) for _ in range(num_rows)]")

            elif col_stats.get('type') == 'datetime':
                # DateTime column generation
                code_lines.append(f"    base_date = datetime.now()")
                code_lines.append(f"    {target} = [base_date - timedelta(days=random.randint(0, 365)) for _ in range(num_rows)]")

            else:
                # Default to None
                code_lines.append(f"    {target} = [None] * num_rows")

            # Add null values if needed
            if col_info.get('nullable', False) and col_info.get('null_count', 0) > 0:
                null_percentage = col_info['null_count'] / metadata['structure']['shape']['rows']
                code_lines.append(f"    # Add null values")
                code_lines.append(f"    null_mask = np.random.random(num_rows) < {py_literal(null_percentage)}")
                code_lines.append(f"    {target} = pd.Series({target})")
                code_lines.append(f"    {target}[null_mask] = None")

            code_lines.append("")

        code_lines.extend([
            "    df = pd.DataFrame(data)",
            "    return df",
            "",
            "# Generate the data",
            "result = generate_synthetic_data()"
        ])

        return "\n".join(code_lines), "fallback"

    def _inject_random_seed(self, code: str, seed: int) -> str:
        """
        Inject or replace random seed in the code to ensure variety.

        Args:
            code: Original code string
            seed: New seed value

        Returns:
            Modified code with new seed
        """
        import re

        # Pattern to find seed assignments
        seed_patterns = [
            (r'random\.seed\(\d+\)', f'random.seed({seed})'),
            (r'np\.random\.seed\(\d+\)', f'np.random.seed({seed})'),
            (r'fake = Faker\(\)', f'fake = Faker()\n    fake.seed_instance({seed})'),
            (r'Faker\(seed=\d+\)', f'Faker(seed={seed})')
        ]

        modified_code = code
        seed_found = False

        for pattern, replacement in seed_patterns:
            if re.search(pattern, modified_code):
                modified_code = re.sub(pattern, replacement, modified_code)
                seed_found = True

        # If no seed found, add one at the beginning of the function
        if not seed_found:
            # Find the function definition
            if 'def generate_synthetic_data' in modified_code:
                lines = modified_code.split('\n')
                for i, line in enumerate(lines):
                    if 'def generate_synthetic_data' in line and i + 1 < len(lines):
                        # Add seed after imports within the function
                        indent = '    '
                        seed_lines = [
                            f'{indent}import random',
                            f'{indent}import numpy as np',
                            f'{indent}random.seed({seed})',
                            f'{indent}np.random.seed({seed})',
                            ''
                        ]
                        # Insert after the function definition
                        lines = lines[:i+1] + seed_lines + lines[i+1:]
                        modified_code = '\n'.join(lines)
                        break

        return modified_code

    @staticmethod
    def _sandbox_environment(temp_dir: str) -> Dict[str, str]:
        """Build the minimal environment for the code-execution subprocess.

        Only what CPython needs to start and import its own site-packages is
        forwarded; everything else (API keys, cloud credentials, tokens) is
        withheld from the generated code.
        """
        env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": temp_dir,
            "TMPDIR": temp_dir,
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        }

        # Locale and Windows loader variables are needed for the interpreter to
        # start, but carry no secrets.
        for passthrough in ("LANG", "LC_ALL", "SYSTEMROOT", "COMSPEC", "PATHEXT"):
            if passthrough in os.environ:
                env[passthrough] = os.environ[passthrough]

        return env

    def _execute_generation_code(self, code: str, randomize_seed: bool = True) -> pd.DataFrame:
        """
        Safely execute the generated Python code.

        Args:
            code: Python code string
            randomize_seed: Whether to inject a random seed for variety

        Returns:
            Generated DataFrame
        """
        self.logger.info("Executing generated code in sandbox")

        # Inject random seed to ensure variety even with cached code
        if randomize_seed:
            import random
            new_seed = random.randint(1, 1000000)
            self.logger.info(f"Injecting random seed {new_seed} for variety")
            # Try to update any existing seed calls
            code = self._inject_random_seed(code, new_seed)
        
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
                
                # Execute the code with a minimal environment. The code being
                # run is generated (by an LLM, from cache, or from a template),
                # so it must not inherit credentials such as
                # AZURE_OPENAI_API_KEY or cloud instance-metadata tokens.
                result = subprocess.run(
                    [sys.executable, str(code_path)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=temp_dir,
                    env=self._sandbox_environment(temp_dir)
                )
                
                if result.returncode != 0:
                    # stderr can quote generated values/column names: log its size only.
                    self.logger.error(f"Code execution failed (exit {result.returncode}, stderr {len(result.stderr or '')} chars)")
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
            self.logger.error(f"Code execution error: {type(e).__name__}")
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
        import random
        import string
        from datetime import datetime, timedelta

        namespace = {
            'pd': pd,
            'np': np,
            'random': random,
            'datetime': datetime,
            'timedelta': timedelta,
            'string': string,
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
                'enumerate': enumerate,
                'print': print,
                'abs': abs,
                'round': round,
                'sorted': sorted,
                'reversed': reversed,
                '__import__': __import__,
                'set': set,
                'tuple': tuple,
                'bool': bool,
                'type': type,
                'isinstance': isinstance,
                'any': any,
                'all': all
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
            self.logger.error(f"Direct execution failed: {type(e).__name__}")
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
                self.logger.warning(f"Missing columns: {len(missing_cols)}")
                return False
            
            # Basic validation passed
            return True
            
        except Exception as e:
            self.logger.error(f"Validation error: {type(e).__name__}")
            return False

    def _log_usage(self, method: str, metadata: Dict[str, Any], num_rows: int, timings: Dict[str, float]):
        """Log usage information for analytics with concurrent access handling."""
        try:
            # Try to use safe logging with file locking
            try:
                from src.utils.log_rotation import safe_append_log
                use_safe_logging = True
            except ImportError:
                use_safe_logging = False

            log_dir = Path("logs/usage")
            log_dir.mkdir(parents=True, exist_ok=True)

            # Check if this is a test/demo dataset
            is_test_data = False
            if "file_info" in metadata:
                filename = metadata["file_info"].get("filename", "").lower()
                is_test_data = any(test_name in filename for test_name in [
                    "test", "demo", "sample", "example", "mock"
                ])

            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "method": method,
                "num_rows": num_rows,
                "num_columns": len(metadata["structure"]["columns"]),
                "timings": timings,
                "total_time": timings.get('total', sum(v for k, v in timings.items() if k != 'total')),
                "cache_hit": method == "cached",
                "is_test_data": is_test_data
            }

            # Append to daily log file
            log_file = log_dir / f"usage_{datetime.now().strftime('%Y-%m-%d')}.jsonl"

            if use_safe_logging:
                # Use file locking for concurrent access
                safe_append_log(log_file, log_entry)
            else:
                # Fallback to simple append
                with open(log_file, 'a') as f:
                    f.write(json.dumps(log_entry) + '\n')

            self.logger.debug(f"Usage logged to {log_file}")
        except Exception as e:
            self.logger.warning(f"Failed to log usage: {e}")