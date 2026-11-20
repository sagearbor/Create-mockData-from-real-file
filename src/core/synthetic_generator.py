"""Synthetic data generation using LLM and metadata."""

import json
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


# Reasoning effort sent to reasoning models. Default "low": gpt-5-nano at the
# API default ("medium") spent ~9.5k of 9.8k output tokens thinking (59 s) for
# one generation. LLM_REASONING_EFFORT=off sends nothing (deployment default).
_REASONING_EFFORT_OFF = {"off", "default", ""}


def reasoning_effort_setting() -> Optional[str]:
    """Return the reasoning_effort to send, or None to omit the parameter."""
    value = (os.environ.get("LLM_REASONING_EFFORT", "low") or "").strip().lower()
    return None if value in _REASONING_EFFORT_OFF else value


def _rejects_reasoning_effort(exc: Exception) -> bool:
    """True if a 400 from the provider is about the reasoning_effort parameter."""
    if getattr(exc, "status_code", None) != 400:
        return False
    return "reasoning_effort" in str(exc) or "reasoning_effort" in str(getattr(exc, "body", "") or "")


class AIGenerationError(RuntimeError):
    """AI generation failed; no data was generated.

    There is deliberately no template fallback: the caller turns this into an
    HTTP error the user sees. ``reason`` is short and content-free (never
    prompt, metadata or provider message text).
    """

    http_status = 502

    def __init__(self, reason: str, *, error_class: Optional[str] = None,
                 finish_reason: Optional[str] = None, upstream_status: Optional[int] = None):
        super().__init__(reason)
        self.reason = reason
        self.error_class = error_class or type(self).__name__
        self.finish_reason = finish_reason
        self.upstream_status = upstream_status

    @property
    def user_message(self) -> str:
        return f"AI generation failed: {self.reason}. No data was generated."


class AINotConfiguredError(AIGenerationError):
    """No usable Azure OpenAI client (endpoint unset or client build failed)."""

    http_status = 503


class LLMOutputError(AIGenerationError):
    """The LLM call returned but its output is unusable (truncated or empty)."""


class CodeExecutionError(AIGenerationError):
    """The AI-written (or cached) generation code failed in the sandbox.

    ``sandbox_stderr`` is the end of the sandbox's error output. It is only ever handed back
    to the model so it can correct its own code: never logged, never shown to the user.
    """

    def __init__(self, reason: str, *, detail: str = "", **kwargs):
        super().__init__(reason, **kwargs)
        self.sandbox_stderr = detail


# How many times the model is asked to correct code that failed to run.
MAX_CODE_FIX_ATTEMPTS = 2
# How much of the sandbox's error output goes back to the model.
_ERROR_DETAIL_CHARS = 1500


class AIRequestTooLargeError(AIGenerationError):
    """The provider refused the request as too large (over the model's context)."""

    http_status = 413


# Provider error codes meaning "the prompt is too big" (OpenAI / Azure OpenAI).
_TOO_LARGE_CODES = {"context_length_exceeded", "string_above_max_length",
                    "tokens_limit_reached", "request_too_large"}
_TOO_LARGE_TEXT = re.compile(
    r"context[_ ]length|maximum context|too many tokens|reduce the length|request too large", re.I)


def _is_request_too_large(exc: Exception) -> bool:
    """True if a provider error says the request was too large.

    Uses the status, the error ``code`` and, last, the message text; the text is
    only inspected here and never shown to the user.
    """
    status = getattr(exc, "status_code", None)
    if status == 413:
        return True
    if status != 400:
        return False
    codes = {getattr(exc, "code", None)}
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        codes.add(body.get("code"))
        if isinstance(body.get("error"), dict):
            codes.add(body["error"].get("code"))
    if codes & _TOO_LARGE_CODES:
        return True
    return bool(_TOO_LARGE_TEXT.search(f"{exc} {body or ''}"))


class SyntheticDataGenerator:
    """Generate synthetic data based on metadata using LLM."""

    # Set once a deployment rejects reasoning_effort, so we stop sending it.
    _reasoning_effort_rejected = False

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
        cached_entry = None
        if use_cached:
            cache_start = time.time()
            try:
                cached_entry = self.cache_manager.find_similar_cached(
                    metadata, match_threshold=0.95, num_rows=num_rows)
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
        if generation_code is None:
            code_gen_start = time.time()
            # Raises AIGenerationError on any AI failure: there is no template fallback.
            generation_code, generation_method, llm_response_time = self._generate_code_with_llm(
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
        
        # Execute the code safely. Model-written code sometimes fails to run: hand the
        # error back to the model and ask for corrected code, a limited number of times.
        exec_start = time.time()
        retried_after_failure = False
        fix_attempts = 0
        while True:
            try:
                synthetic_df = self._execute_generation_code(generation_code)
                if generation_method == 'cached' and len(synthetic_df) != num_rows:
                    # A cached script writes the row count it was made for. It is a good
                    # script, just not for this request: leave it cached, write new code.
                    self.logger.info("Cached code makes a different number of rows; generating new code")
                    generation_code, generation_method, _ = self._generate_code_with_llm(
                        metadata, num_rows, match_threshold, operation="generate_code")
                    continue
                break
            except CodeExecutionError as failure:
                if generation_method == 'cached':
                    # Cached code that no longer runs must not be served again.
                    self.forget_cached(cached_entry)
                if fix_attempts >= MAX_CODE_FIX_ATTEMPTS:
                    raise
                fix_attempts += 1
                self.logger.warning(
                    f"Generated code failed to run; asking the model to correct it "
                    f"(attempt {fix_attempts} of {MAX_CODE_FIX_ATTEMPTS})")
                retried_after_failure = True
                generation_code, generation_method, _ = self._generate_code_with_llm(
                    metadata, num_rows, match_threshold, operation="regenerate_code",
                    failed_error=failure.sandbox_stderr)
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
        if retried_after_failure:
            generation_info["retried_after_failure"] = True
        # Log usage for analytics
        self._log_usage(generation_method, metadata, num_rows, step_timings)

        if validation_passed:
            self.logger.info(f"Successfully generated synthetic data with shape {synthetic_df.shape}")
            if generation_method == 'llm':
                self._remember_code(metadata, generation_code, num_rows)
            return synthetic_df, generation_info
        else:
            self.logger.warning("Validation failed, regenerating with stricter parameters")
            # Try again with stricter threshold. If that attempt cannot be run, keep the
            # first result (it ran) and say its columns differ, rather than return nothing.
            try:
                generation_code, generation_method, _ = self._generate_code_with_llm(
                    metadata, num_rows, min(match_threshold + 0.1, 1.0), operation="regenerate_code")
                second_df = self._execute_generation_code(generation_code)
            except AIGenerationError as e:
                self.logger.warning(f"Regeneration failed ({type(e).__name__}); keeping the first result")
                generation_info["structure_mismatch"] = True
                return synthetic_df, generation_info
            generation_info["method"] = generation_method
            generation_info["regenerated"] = True
            if not self._validate_synthetic_data(second_df, metadata):
                generation_info["structure_mismatch"] = True
            else:
                self._remember_code(metadata, generation_code, num_rows)
            return second_df, generation_info

    def _remember_code(self, metadata: Dict[str, Any], code: str, num_rows: Optional[int] = None) -> None:
        """Cache code only once it has run and produced the expected columns."""
        try:
            self.cache_manager.cache_generation(metadata, code, num_rows=num_rows)
            self.logger.info("Cached generation code for future use")
        except Exception as e:
            self.logger.warning(f"Failed to cache: {type(e).__name__}")

    def forget_cached(self, cached_entry: Optional[Dict[str, Any]]) -> None:
        """Drop a cache entry whose code failed to run, so it is not served again."""
        cache_file = (cached_entry or {}).get("cache_file")
        if not cache_file:
            return
        try:
            self.cache_manager.remove_entry(cache_file)
            self.logger.warning("Removed cached code that failed to run")
        except Exception as e:
            self.logger.warning(f"Could not remove failed cache entry: {type(e).__name__}")
    
    def _generate_code_with_llm(
        self,
        metadata: Dict[str, Any],
        num_rows: int,
        match_threshold: float,
        operation: str = "generate_code",
        failed_error: Optional[str] = None,
    ) -> Tuple[str, str, float]:
        """
        Generate Python code using LLM based on metadata.

        Args:
            metadata: Metadata dictionary
            num_rows: Number of rows to generate
            match_threshold: Statistical matching threshold
            operation: Stable telemetry name for this call (dcri_llm ``operation``)
            failed_error: End of the error output from a previous attempt's code, so the
                model can avoid the same mistake

        Returns:
            Tuple of (code, ``"llm"``, LLM seconds).

        Raises:
            AINotConfiguredError: no Azure OpenAI client.
            AIGenerationError: the call failed or returned unusable output.
        """
        model = settings.azure_openai_chat_deployment
        if not self.openai_client:
            err = AINotConfiguredError("Azure OpenAI is not configured on this server")
            self._log_ai_failure(err, operation, model)
            raise err

        prompt = self._construct_generation_prompt(metadata, num_rows, match_threshold)
        if failed_error is not None:
            prompt += (
                "\n\nYour previous code for this request failed when it was run. "
                "Write the code again, complete, avoiding this error. Keep it simple: "
                "standard library, pandas and numpy only.\n"
                f"ERROR OUTPUT:\n{failed_error[-_ERROR_DETAIL_CHARS:] or '(none captured)'}"
            )

        from src.dcri_llm import llm_action  # lazy: keeps module import light

        request: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": prompt},
            ],
            "max_completion_tokens": LLM_MAX_COMPLETION_TOKENS,
        }
        is_reasoning = bool(_REASONING_MODEL_RE.match(model or ""))
        if not is_reasoning:
            # Reasoning models only accept the default temperature.
            request["temperature"] = 0.3
        effort = reasoning_effort_setting()
        if is_reasoning and effort and not SyntheticDataGenerator._reasoning_effort_rejected:
            request["reasoning_effort"] = effort

        finish_reason = None
        try:
            self.logger.info(f"Calling Azure OpenAI with model: {model} "
                             f"(reasoning_effort={request.get('reasoning_effort', 'unset')})")
            self.logger.debug(f"Prompt length: {len(prompt)} characters")

            llm_start = time.time()
            with llm_action(operation):
                try:
                    response = self.openai_client.chat.completions.create(**request)
                except Exception as e:  # noqa: BLE001
                    if "reasoning_effort" in request and _rejects_reasoning_effort(e):
                        # Deployment doesn't take the parameter: drop it for good, retry once.
                        SyntheticDataGenerator._reasoning_effort_rejected = True
                        self.logger.warning(
                            "Deployment %s rejected reasoning_effort; retrying without it", model)
                        request.pop("reasoning_effort")
                        response = self.openai_client.chat.completions.create(**request)
                    else:
                        raise
            llm_response_time = time.time() - llm_start

            choice = response.choices[0] if response.choices else None
            finish_reason = getattr(choice, "finish_reason", None)
            code = (choice.message.content if choice and choice.message else None) or ""
            if finish_reason == "length":
                raise LLMOutputError(
                    "the model ran out of its token budget before finishing (finish_reason=length)",
                    finish_reason=finish_reason)
            if not code.strip():
                raise LLMOutputError(
                    f"the model returned an empty response (finish_reason={finish_reason})",
                    finish_reason=finish_reason)

            generation_method = "llm"
            self.logger.info(f"Successfully received LLM response ({len(code)} characters) in {llm_response_time:.2f}s")
        except AIGenerationError as err:
            self._log_ai_failure(err, operation, model)
            raise
        except Exception as e:
            # Type/status only: provider messages can echo request content.
            status = getattr(e, "status_code", None)
            if _is_request_too_large(e):
                from src.core.data_dictionary import PROMPT_BUDGET_ENV  # lazy
                err = AIRequestTooLargeError(
                    "the request was too large for the AI model (the data dictionary or data "
                    "description sent to it is over the model's limit). Use a smaller table or "
                    f"fewer columns, or lower {PROMPT_BUDGET_ENV} on the server",
                    finish_reason=finish_reason, upstream_status=status)
                self._log_ai_failure(err, operation, model)
                raise err from e
            reason = f"the Azure OpenAI call failed ({type(e).__name__}"
            reason += f", HTTP {status})" if status else ")"
            err = AIGenerationError(reason, error_class=type(e).__name__,
                                    finish_reason=finish_reason, upstream_status=status)
            self._log_ai_failure(err, operation, model)
            raise err from e

        # Not cached here: code is cached by generate() only after it has run.
        # Extract code from markdown if present
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0]
        elif "```" in code:
            code = code.split("```")[1].split("```")[0]

        return code.strip(), generation_method, llm_response_time

    def _log_ai_failure(self, err: "AIGenerationError", operation: str, model: Optional[str]) -> None:
        """One structured ERROR line per AI failure (no prompt or data text)."""
        try:
            from src.dcri_llm import current_context
            action_id = current_context().get("action_id")
        except Exception:  # noqa: BLE001
            action_id = None
        self.logger.error(json.dumps({
            "event": "ai_generation_failed",
            "operation": operation,
            "model": model,
            "error_class": err.error_class,
            "reason": err.reason,
            "finish_reason": err.finish_reason,
            "upstream_status": err.upstream_status,
            "request_id": action_id,
        }))

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
            # Keep the line's own indentation: a fixed indent breaks module-level code.
            (r'(?m)^([ \t]*)fake = Faker\(\)', rf'\1fake = Faker()\n\1fake.seed_instance({seed})'),
            (r'Faker\(seed=\d+\)', f'Faker(seed={seed})'),
            (r'default_rng\(\d+\)', f'default_rng({seed})'),
            (r'RandomState\(\d+\)', f'RandomState({seed})'),
        ]

        modified_code = code
        seed_found = False

        for pattern, replacement in seed_patterns:
            if re.search(pattern, modified_code):
                modified_code = re.sub(pattern, replacement, modified_code)
                seed_found = True

        # If no seed found, seed at the very top of the module. Inserting inside the
        # function body breaks code whose signature or indentation is not the usual shape.
        if not seed_found:
            modified_code = (
                f"import random as _seed_random\nimport numpy as _seed_np\n"
                f"_seed_random.seed({seed})\n_seed_np.random.seed({seed})\n" + modified_code
            )

        # Never let seeding turn runnable code into code that does not parse.
        try:
            compile(modified_code, "<generated>", "exec")
        except SyntaxError:
            try:
                compile(code, "<generated>", "exec")
            except SyntaxError:
                return modified_code  # the original is broken too; let the sandbox report it
            return code

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
                # run is generated (by an LLM, or from the cache of LLM output),
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
                    raise CodeExecutionError(
                        f"generated code failed in the sandbox (exit {result.returncode})",
                        detail=(result.stderr or "")[-_ERROR_DETAIL_CHARS:])

                # Load the generated data
                if not pickle_path.exists():
                    raise CodeExecutionError("generated code produced no result")
                return pd.read_pickle(pickle_path)

        except subprocess.TimeoutExpired:
            self.logger.error("Code execution timeout")
            raise CodeExecutionError("generated code timed out after 30s in the sandbox")
        except AIGenerationError:
            raise
        except Exception as e:
            # No in-process exec fallback: generated code only ever runs in the sandbox.
            self.logger.error(f"Code execution error: {type(e).__name__}")
            raise CodeExecutionError(f"generated code could not be run ({type(e).__name__})") from e
        finally:
            # Clean up temp file
            if Path(temp_file).exists():
                Path(temp_file).unlink()
    
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
            # Expected column names: from the data file's structure, or, when generating from a
            # dictionary alone (no structure columns), from the dictionary's column names.
            expected_names = [col['name'] for col in metadata['structure']['columns']]
            if not expected_names:
                expected_names = list(metadata.get('expected_columns') or [])
            if not expected_names:
                return len(df.columns) > 0

            # Check column count
            expected_cols = len(expected_names)
            if len(df.columns) != expected_cols:
                self.logger.warning(f"Column count mismatch: expected {expected_cols}, got {len(df.columns)}")
                return False
            
            # Check column names
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