"""Extract comprehensive metadata from DataFrames for synthetic data generation."""

import pandas as pd
import numpy as np
import re
import json
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from src.utils.logger import logger
from src.utils.pandas_compat import is_categorical, is_text_dtype, text_columns
from src.core.clinical_reference import ClinicalReferenceLibrary


# Privacy rules for what may leave the extractor. Everything extract() returns
# is sent to the model and written to the cache, so masking happens here.
MIN_ROWS_FOR_REAL_VALUES = 20   # below this, no cell value or fragment is emitted
MIN_VALUE_COUNT = 5             # a category must occur at least this often to be shown
MAX_UNIQUE_RATIO = 0.2          # distinct values / non-null rows
MAX_CATEGORY_LENGTH = 30
MAX_FRAGMENT_LENGTH = 6         # longest shared prefix that may be emitted
CATEGORY_LIMITS = {"balanced": 10, "permissive": 50}

# Column-name words that mark a column as identifying. Long words match at the
# start or end of a name token ("firstname", "birthdate", "notes"). Short words
# match a whole token, its end, or its start plus a few letters ("zipcode" but
# not "dobutamine"). "id" must be a whole token so "valid" and "paid" pass.
_ID_NAME_WORDS = ("name", "birth", "address", "email", "phone", "note", "comment", "postal")
_ID_NAME_SHORT_WORDS = ("mrn", "ssn", "dob", "zip")
_ID_SUFFIX_OWNERS = ("patient", "subject", "participant", "person", "user", "member",
                     "customer", "client", "employee", "provider", "account", "record",
                     "encounter", "visit", "case", "study", "site", "sample", "specimen",
                     "order", "device",
                     "subj", "usubj", "pat", "pt", "emp", "cust", "acct", "mbr", "enc", "rec")

# Value shapes that are never treated as a category label (unanchored).
_SENSITIVE_VALUE_PATTERNS = [
    re.compile(r'[^@\s]+@[^@\s]+'),                               # email
    re.compile(r'\d{3}-\d{2}-\d{4}'),                             # SSN
    re.compile(r'\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]\d{4}'),          # phone
    re.compile(r'\d{3}[\s.\-]\d{4}'),                            # short phone
    re.compile(r'\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}'),               # numeric date
    re.compile(r'\d{1,2}[-\s]?[A-Za-z]{3,9}[-\s,]*\d{2,4}'),      # 15-Jan-2024
    re.compile(r'[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{2,4}'),       # Jan 15, 2024
    re.compile(r'\d{5,}'),                                        # long digit run
]


def _round_significant(value: float, digits: int, direction: str = "nearest") -> float:
    """Round to `digits` significant figures; "down"/"up" widen a range instead of clipping it."""
    import math
    if value is None or value == 0 or not math.isfinite(value):
        return value
    scale = 10 ** (math.floor(math.log10(abs(value))) - digits + 1)
    scaled = value / scale
    rounded = math.floor(scaled) if direction == "down" else math.ceil(scaled) if direction == "up" else round(scaled)
    return float(rounded * scale)


def is_identifier_like_name(column_name: Any) -> bool:
    """True if a column name suggests identifying content (name, MRN, id, DOB, ...)."""
    if column_name is None:
        return False
    # Split camelCase, then on anything that is not a letter.
    spaced = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', str(column_name))
    for token in re.split(r'[^a-z]+', spaced.lower()):
        if not token:
            continue
        if token in ("id", "ids"):
            return True
        if any(token.startswith(w) or token.endswith(w) or token.endswith(w + "s")
               for w in _ID_NAME_WORDS):
            return True
        if any(token.endswith(w) or token.endswith(w + "s")
               or (token.startswith(w) and len(token) <= len(w) + 4)
               for w in _ID_NAME_SHORT_WORDS):
            return True
        # Joined lower-case forms such as "patientid".
        if token.endswith("id") and token[:-2] in _ID_SUFFIX_OWNERS:
            return True
    return False


def _looks_sensitive_value(value: str) -> bool:
    """True if a value looks like an email, phone, SSN, date or long number."""
    return any(p.search(value) for p in _SENSITIVE_VALUE_PATTERNS)


class MetadataExtractor:
    """Extract statistical and structural metadata from pandas DataFrames."""
    
    def __init__(self, use_clinical_reference: bool = True, safety_mode: str = "balanced"):
        """
        Initialize the MetadataExtractor.

        Args:
            use_clinical_reference: Whether to use clinical reference library for medical data
            safety_mode: Level of data preservation ('strict', 'balanced', 'permissive')
                - 'strict': No cell value and no fragment of one is emitted
                - 'balanced': Repeated, non-sensitive category labels are kept (<=10 unique)
                - 'permissive': Same rule as balanced, up to 50 unique values
                See _is_safe_to_preserve for the full rule.
        """
        self.logger = logger
        self.clinical_reference = ClinicalReferenceLibrary() if use_clinical_reference else None
        # Anything that is not one of the three modes is treated as the most private one.
        mode = str(safety_mode or "").strip().lower()
        self.safety_mode = mode if mode in ("strict", "balanced", "permissive") else "strict"
        
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

        # The privacy mode travels with the description: a generation script cached
        # from it is only reused for requests in the same mode (cache_manager.cache_variant).
        metadata["privacy_mode"] = self.safety_mode

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
                col_stats.update(self._extract_numeric_stats(df[col], column_name=col))
            
            # DateTime columns
            elif pd.api.types.is_datetime64_any_dtype(df[col]):
                col_stats.update(self._extract_datetime_stats(df[col], column_name=col))
            
            # String/Object columns
            else:
                col_stats.update(self._extract_string_stats(df[col], column_name=col))
                # Add column name context for better type detection
                col_stats["column_name"] = col
            
            stats[col] = col_stats
        
        return stats
    
    def _extract_numeric_stats(self, series: pd.Series, column_name: str = None) -> Dict[str, Any]:
        """Extract statistics for numeric columns."""
        # is_numeric_dtype() reports True for booleans, so bool columns arrive
        # here. Cast them to integers: quantile() on a boolean Series raises on
        # pandas 3 / numpy 2 ("numpy boolean subtract ... is not supported"),
        # and the 0/1 statistics this produces are what pandas 2 produced too.
        if pd.api.types.is_bool_dtype(series):
            series = series.astype("Int64" if series.isna().any() else "int64")

        # Remove NaN values for calculation
        clean_series = series.dropna()

        # Check if this might be currency/money
        is_likely_currency = False
        decimal_places = None
        if len(clean_series) > 0:
            # Check column name for currency hints
            if column_name:
                money_keywords = ['amount', 'price', 'cost', 'fee', 'payment', 'balance', 'total', 'subtotal', 'tax', 'discount']
                is_likely_currency = any(keyword in column_name.lower() for keyword in money_keywords)

            # Check decimal patterns
            if is_likely_currency or (clean_series % 1).any():  # Has decimals
                # Check consistent decimal places (like currency)
                decimal_strs = clean_series.astype(str)
                decimal_parts = decimal_strs.str.split('.').str[1].fillna('')
                decimal_lengths = decimal_parts.str.len()
                # If most values have 2 decimal places, likely currency
                if (decimal_lengths == 2).sum() > len(decimal_lengths) * 0.8:
                    is_likely_currency = True
                    decimal_places = 2
                elif (decimal_lengths == 0).sum() > len(decimal_lengths) * 0.8:
                    # Mostly whole numbers but in a money column
                    decimal_places = 0
        
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
            "has_zero": bool((clean_series == 0).any()),
            "is_likely_currency": is_likely_currency,
            "decimal_places": decimal_places
        }
        
        # Check if it might be a percentage (values between 0 and 1 or 0 and 100)
        if stats["min"] >= 0:
            if stats["max"] <= 1:
                stats["might_be_percentage"] = "decimal"
            elif stats["max"] <= 100:
                stats["might_be_percentage"] = "whole"

        # min, max, median and quartiles are (or can equal) single real cells.
        if is_identifier_like_name(column_name):
            # patient_id, mrn, zip: every one of these would be a real identifier.
            for key in ("min", "max", "median", "q25", "q75"):
                stats.pop(key, None)
            if len(clean_series) < MIN_ROWS_FOR_REAL_VALUES:
                stats.pop("mean", None)  # with few rows the mean is close to a real cell
            stats["min_max_omitted"] = True
            stats["order_statistics_omitted"] = True
        elif self.safety_mode == "strict" or len(clean_series) < MIN_ROWS_FOR_REAL_VALUES:
            # Strict mode, or too few rows to hide a cell in: send rounded values only.
            # The range is widened (min down, max up) so generated data still covers it.
            stats["min"] = _round_significant(stats["min"], 1, "down")
            stats["max"] = _round_significant(stats["max"], 1, "up")
            for key in ("median", "q25", "q75", "mean"):
                stats[key] = _round_significant(stats[key], 2)
            stats["values_rounded"] = True

        return stats
    
    def _extract_datetime_stats(self, series: pd.Series, column_name: str = None) -> Dict[str, Any]:
        """Extract statistics for datetime columns.

        The earliest and latest value are real cells (an earliest date of birth, a
        first visit), so they are never sent exactly: the range is widened to whole
        months, or to whole years for identifier-like columns (dob, birth), strict
        mode and files with too few rows to hide a cell in.
        """
        clean_series = series.dropna()

        if len(clean_series) == 0:
            return {"type": "datetime", "all_null": True}

        as_dt = pd.to_datetime(clean_series)
        earliest, latest = as_dt.min(), as_dt.max()
        to_year = (is_identifier_like_name(column_name) or self.safety_mode == "strict"
                   or len(clean_series) < MIN_ROWS_FOR_REAL_VALUES)
        if pd.notna(earliest) and pd.notna(latest):
            if to_year:
                shown_min = earliest.replace(month=1, day=1).normalize()
                shown_max = latest.replace(month=12, day=31).normalize()
            else:
                shown_min = earliest.replace(day=1).normalize()
                shown_max = (latest + pd.offsets.MonthEnd(0)).normalize()
            range_days = int((shown_max - shown_min).days)
        else:
            shown_min = shown_max = None
            range_days = 0

        return {
            "type": "datetime",
            "min": shown_min.isoformat() if shown_min is not None else None,
            "max": shown_max.isoformat() if shown_max is not None else None,
            "range_rounded_to": "year" if to_year else "month",
            "range_days": range_days,
            "most_common_hour": int(as_dt.dt.hour.mode()[0]),
            "most_common_dayofweek": int(as_dt.dt.dayofweek.mode()[0]),
            "has_time_component": bool(not (as_dt.dt.time == pd.Timestamp("00:00:00").time()).all())
        }

    def _extract_string_stats(self, series: pd.Series, column_name: str = None) -> Dict[str, Any]:
        """Extract statistics for string/object columns."""
        clean_series = series.dropna()

        if len(clean_series) == 0:
            return {"type": "string", "all_null": True}

        # Convert to string for analysis
        str_series = clean_series.astype(str)

        value_counts = str_series.value_counts()
        unique_ratio = len(value_counts) / len(clean_series)

        # Check if this might be datetime stored as string
        is_datetime_string = False
        datetime_format = None
        if len(clean_series) > 0:
            # Try to detect datetime patterns
            sample_val = str_series.iloc[0]
            if self._looks_like_datetime(sample_val):
                is_datetime_string = True
                # Try to detect the format
                if ':' in sample_val and '-' in sample_val:
                    if len(sample_val) > 16:  # Has seconds
                        datetime_format = '%Y-%m-%d %H:%M:%S'
                    else:
                        datetime_format = '%Y-%m-%d %H:%M'
                elif '-' in sample_val and len(sample_val) == 10:
                    datetime_format = '%Y-%m-%d'

        # Real values are emitted only for columns that pass _is_safe_to_preserve.
        # Strict mode never emits one.
        is_safe_categorical = self._is_safe_to_preserve(
            str_series, value_counts, column_name=column_name
        )

        # Masked values keep their count under a value_N key so the shape of
        # the distribution survives. In a preserved column, values seen fewer
        # than MIN_VALUE_COUNT times are still masked.
        most_common = {}
        for i, (value, count) in enumerate(value_counts.head(10).items()):
            keep = is_safe_categorical and count >= MIN_VALUE_COUNT
            most_common[value if keep else f"value_{i}"] = int(count)

        stats = {
            "type": "string",
            "unique_values": int(len(value_counts)),
            "unique_ratio": float(unique_ratio),
            "most_common_values": most_common,
            "preserve_values": is_safe_categorical,  # True only if real values are present
            "avg_length": float(str_series.str.len().mean()),
            "min_length": int(str_series.str.len().min()),
            "max_length": int(str_series.str.len().max()),
            "is_categorical": unique_ratio < 0.5 and len(value_counts) < 100,
            "is_datetime_string": is_datetime_string,
            "datetime_format": datetime_format,
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

        # Enhanced detection based on actual values
        sample_values = list(value_counts.index[:5])  # Get top 5 values

        # Check if all values are emails
        if all(self._is_email(v) for v in sample_values if v):
            stats["detected_type"] = "email"
            stats["preserve_format"] = True

        # Check if all values are phone numbers
        elif all(self._is_phone(v) for v in sample_values if v):
            stats["detected_type"] = "phone"
            stats["preserve_format"] = True
            # Detect phone format
            if sample_values:
                if '-' in sample_values[0]:
                    stats["phone_format"] = "dash"  # 555-0101 or 555-555-5555
                elif '.' in sample_values[0]:
                    stats["phone_format"] = "dot"  # 555.555.5555
                elif '(' in sample_values[0]:
                    stats["phone_format"] = "parentheses"  # (555) 555-5555

        return stats

    def _is_email(self, value: str) -> bool:
        """Check if a value looks like an email."""
        import re
        return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', value))

    def _is_phone(self, value: str) -> bool:
        """Check if a value looks like a phone number."""
        import re
        phone_patterns = [
            r'^\+?1?\d{10}$',  # Simple 10 digits
            r'^\d{3}-\d{3}-\d{4}$',  # 555-555-5555
            r'^\d{3}\.\d{3}\.\d{4}$',  # 555.555.5555
            r'^\(\d{3}\)\s?\d{3}-\d{4}$',  # (555) 555-5555
            r'^\d{3}-\d{4}$',  # 555-5555
        ]
        return any(re.match(pattern, value) for pattern in phone_patterns)
    
    def _extract_patterns(self, df: pd.DataFrame, sample_size: int) -> Dict[str, Any]:
        """Extract data patterns and regularities."""
        patterns = {}
        
        # Sample the dataframe if it's too large
        if len(df) > sample_size:
            sample_df = df.sample(n=sample_size, random_state=42)
        else:
            sample_df = df
        
        for col in df.columns:
            if is_text_dtype(df[col]):
                patterns[col] = self._extract_string_patterns(sample_df[col])
        
        return patterns
    
    def _extract_string_patterns(self, series: pd.Series) -> Dict[str, Any]:
        """Extract common patterns from string columns."""
        clean_series = series.dropna().astype(str)

        if len(clean_series) == 0:
            return {}

        # Fragments of real cells (prefix, suffix) are emitted only outside
        # strict mode and only for columns with enough rows.
        allow_fragments = (
            self.safety_mode != 'strict'
            and len(clean_series) >= MIN_ROWS_FOR_REAL_VALUES
        )
        identifier_name = is_identifier_like_name(series.name)

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
            "phone_us": r'^\+?1?\d{10}$|^\d{3}-\d{3}-\d{4}$|^\d{3}\.\d{3}\.\d{4}$|^\(\d{3}\)\s?\d{3}-\d{4}$',
            "phone_simple": r'^\d{3}-\d{4}$',  # Like 555-0101
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

        # Enhanced prefix/suffix detection for IDs with patterns
        if len(clean_series) > 2:
            # Check for consistent prefix pattern (like C001, C002, P001, ACC001)
            first_val = clean_series.iloc[0]

            # Try to detect prefix + number pattern
            import re
            prefix_match = re.match(r'^([A-Za-z]+[\-_]?)([0-9]+)$', first_val)
            if prefix_match:
                prefix = prefix_match.group(1)
                # Check if all values follow this pattern
                matching = clean_series[clean_series.str.match(f'^{re.escape(prefix)}[0-9]+$', na=False)]
                pattern_matches = len(matching)
                if pattern_matches > len(clean_series) * 0.9:  # 90% threshold
                    # Describe the shape instead of quoting a real cell.
                    digit_count = int((matching.str.len() - len(prefix)).mode().iloc[0])
                    show_prefix = allow_fragments and self._is_safe_fragment(prefix, matching)
                    id_pattern = {
                        "type": "prefix_sequential",
                        "prefix_length": len(prefix),
                        "digit_count": digit_count,
                        "shape": f"{prefix if show_prefix else f'<{len(prefix)} characters>'}<{digit_count} digits>",
                        "confidence": float(pattern_matches / len(clean_series))
                    }
                    if show_prefix:
                        id_pattern["prefix"] = prefix
                    patterns["id_pattern"] = id_pattern

            if allow_fragments and not identifier_name:
                # Longest prefix shared by 90% of rows, cut at the first digit.
                min_len = clean_series.str.len().min()
                if min_len >= 2:
                    for prefix_len in range(min(min_len, 10), 0, -1):
                        potential_prefix = clean_series.iloc[0][:prefix_len]
                        sharing = clean_series[clean_series.str.startswith(potential_prefix)]
                        if len(sharing) > len(clean_series) * 0.9:
                            fragment = re.match(r'^\D*', potential_prefix).group(0)
                            if self._is_safe_fragment(fragment, sharing):
                                patterns["common_prefix"] = fragment
                            break

                # Common suffixes (values longer than the suffix only)
                long_values = clean_series[clean_series.str.len() > 3]
                if len(long_values) > 0:
                    suffix_counts = long_values.str[-3:].value_counts()
                    suffix = suffix_counts.index[0]
                    if suffix_counts.iloc[0] > len(long_values) * 0.3:
                        sharing = long_values[long_values.str.endswith(suffix)]
                        if self._is_safe_fragment(suffix, sharing):
                            patterns["common_suffix"] = suffix

        return patterns

    def _is_safe_fragment(self, fragment: str, sharing: pd.Series) -> bool:
        """
        Decide whether a shared prefix/suffix may be emitted.

        It must be short, contain no digit or whitespace-only text, be shared
        by at least MIN_VALUE_COUNT distinct values, and not be a whole cell.
        """
        if not fragment.strip() or len(fragment) > MAX_FRAGMENT_LENGTH:
            return False
        if re.search(r'\d', fragment):
            return False
        if sharing.nunique() < MIN_VALUE_COUNT:
            return False
        if (sharing.str.strip() == fragment.strip()).any():
            return False
        return True
    
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
        categorical_cols = text_columns(df)
        if len(categorical_cols) > 1:
            associations = []
            for i in range(min(len(categorical_cols), 10)):  # Limit to first 10 to avoid explosion
                for j in range(i+1, min(len(categorical_cols), 10)):
                    col1, col2 = categorical_cols[i], categorical_cols[j]
                    # Simple association metric based on unique value overlap
                    unique1 = df[col1].nunique()
                    unique2 = df[col2].nunique()
                    # An all-null column has nunique() == 0, which would make the
                    # denominator zero. Such a column carries no information, so
                    # there is no association to report.
                    if unique1 == 0 or unique2 == 0:
                        continue
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
    
    def _looks_like_datetime(self, value: str) -> bool:
        """Check if a string value looks like a datetime."""
        import re
        # Common datetime patterns
        datetime_patterns = [
            r'^\d{4}-\d{2}-\d{2}$',  # 2024-01-15
            r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$',  # 2024-01-15 09:30:00
            r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',  # ISO format
            r'^\d{2}/\d{2}/\d{4}',  # 01/15/2024
            r'^\d{1,2}-[A-Za-z]{3}-\d{4}',  # 15-Jan-2024
        ]
        return any(re.match(pattern, value) for pattern in datetime_patterns)

    def _is_safe_to_preserve(self, str_series: pd.Series, value_counts: pd.Series,
                             column_name: Any = None) -> bool:
        """
        Decide whether a string column's real values may be emitted.

        True only if ALL of these hold; anything else is masked:
          - the mode is 'balanced' (<=10 distinct values) or 'permissive' (<=50);
            'strict' never preserves
          - the column has at least MIN_ROWS_FOR_REAL_VALUES (20) non-null rows
          - distinct values / non-null rows <= MAX_UNIQUE_RATIO (0.2)
          - at least one value occurs MIN_VALUE_COUNT (5) or more times; rarer
            values in the same column are masked individually by the caller
          - no value is longer than MAX_CATEGORY_LENGTH (30) characters
          - no value (checked over every distinct value) looks like an email,
            phone number, SSN or date, or contains 5 or more digits in a row
          - the column name is not identifier-like (is_identifier_like_name)

        So small files and unique columns never qualify. A name that repeats
        five times in a column with a neutral name still looks like a category.

        Args:
            str_series: Non-null values as strings
            value_counts: Value counts of the series
            column_name: Column name, if known

        Returns:
            True if the repeated values may be emitted
        """
        limit = CATEGORY_LIMITS.get(self.safety_mode)
        if limit is None:  # strict, or an unknown mode
            return False
        if len(value_counts) > limit:
            return False
        if len(str_series) < MIN_ROWS_FOR_REAL_VALUES:
            return False
        if len(value_counts) / len(str_series) > MAX_UNIQUE_RATIO:
            return False
        if value_counts.iloc[0] < MIN_VALUE_COUNT:
            return False
        if is_identifier_like_name(column_name):
            return False
        for value in value_counts.index:
            if len(value) > MAX_CATEGORY_LENGTH or _looks_sensitive_value(value):
                return False
        return True

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
        elif is_categorical(series):
            return "category"
        else:
            return "str"
    
    def to_secure_json(self, metadata: Dict[str, Any]) -> str:
        """
        Convert metadata to secure JSON format.

        extract() already masks values, so on its output this changes nothing.
        It stays as a safety net for metadata built elsewhere or by older code.

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
                    # Check if values should be preserved (non-sensitive)
                    if not col_stats.get("preserve_values", False):
                        # Only keep the counts, not the actual values for sensitive data
                        col_stats["most_common_values"] = {
                            f"value_{i}": count
                            for i, count in enumerate(col_stats["most_common_values"].values())
                        }
                    # If preserve_values is True, keep the actual values

        # Older metadata quoted a real cell here.
        for col_patterns in (secure_metadata.get("patterns") or {}).values():
            if isinstance(col_patterns, dict) and isinstance(col_patterns.get("id_pattern"), dict):
                col_patterns["id_pattern"].pop("example", None)

        return json.dumps(secure_metadata, indent=2, default=str)