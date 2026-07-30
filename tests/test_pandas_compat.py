"""Cross-version pandas/numpy compatibility tests.

The pins in requirements.txt (pandas 2.x, numpy 1.x) are not the only versions
this code has to survive. pandas 3 changed two things that silently broke
metadata extraction:

1. Text columns default to the ``str`` extension dtype, so ``is_object_dtype()``
   no longer identifies them — every guard written as "if object dtype" simply
   stopped firing, disabling date detection and pattern extraction.
2. ``Series.quantile()`` on a boolean column now raises, and ``is_numeric_dtype``
   reports True for booleans, so boolean columns crashed metadata extraction.

These tests assert on behaviour, so they hold on pandas 2 and pandas 3 alike.
"""

import pandas as pd
import pytest

from src.core.data_loader import DataLoader
from src.core.metadata_extractor import MetadataExtractor


@pytest.fixture
def extractor():
    return MetadataExtractor()


# --------------------------------------------------------------------------- #
# Boolean columns
# --------------------------------------------------------------------------- #

def test_boolean_column_does_not_break_extraction(extractor):
    """is_numeric_dtype() is True for bool, so bool hits the numeric path."""
    df = pd.DataFrame({"is_active": [True, False, True, True, False] * 4})

    metadata = extractor.extract(df)
    stats = metadata["statistics"]["is_active"]

    assert stats["type"] == "numeric"
    # quantile() on a bool Series raises on pandas 3 / numpy 2
    assert stats["q25"] == pytest.approx(0.0)
    assert stats["q75"] == pytest.approx(1.0)
    assert stats["min"] == pytest.approx(0.0)
    assert stats["max"] == pytest.approx(1.0)
    assert stats["is_integer"] is True


def test_boolean_column_survives_a_full_generation_round_trip(extractor):
    """A bool column must still produce data through the fallback generator."""
    from src.core.synthetic_generator import SyntheticDataGenerator

    df = pd.DataFrame({"is_active": [True, False] * 10})
    metadata = extractor.extract(df)

    generator = SyntheticDataGenerator()
    code, _ = generator._generate_fallback_code(metadata, num_rows=5)
    result = generator._execute_generation_code(code, randomize_seed=False)

    assert list(result.columns) == ["is_active"]
    assert set(result["is_active"].unique()) <= {0, 1}


# --------------------------------------------------------------------------- #
# Text columns (object dtype on pandas 2, str dtype on pandas 3)
# --------------------------------------------------------------------------- #

def test_patterns_are_extracted_for_text_columns(extractor):
    """Pattern extraction must fire for text columns on any pandas version."""
    df = pd.DataFrame({
        "patient_id": [f"PT{i:04d}" for i in range(20)],
        "count": range(20),
    })

    metadata = extractor.extract(df)

    assert "patient_id" in metadata["patterns"], (
        "text column got no pattern analysis — the dtype guard did not fire"
    )
    assert "count" not in metadata["patterns"]


def test_id_prefix_pattern_is_detected(extractor):
    """The prefix_sequential pattern drives ID generation downstream."""
    df = pd.DataFrame({"subject_id": [f"SUBJ{i:03d}" for i in range(1, 21)]})

    patterns = extractor.extract(df)["patterns"]

    assert patterns["subject_id"]["id_pattern"]["type"] == "prefix_sequential"
    assert patterns["subject_id"]["id_pattern"]["prefix"] == "SUBJ"


def test_categorical_associations_consider_text_columns(extractor):
    """select_dtypes-based categorical association must see text columns."""
    df = pd.DataFrame({
        "site": ["A", "B"] * 10,
        "arm": ["placebo", "drug"] * 10,
    })

    correlations = extractor.extract(df)["correlations"]

    assert correlations["categorical_associations"], (
        "no categorical associations computed for two text columns"
    )


def test_explicit_object_dtype_still_works(extractor):
    """Callers may still hand us object dtype; both dtypes must be handled."""
    df = pd.DataFrame({"code": pd.Series([f"AB{i:03d}" for i in range(20)], dtype=object)})

    metadata = extractor.extract(df)

    assert "code" in metadata["patterns"]
    assert metadata["statistics"]["code"]["type"] == "string"


# --------------------------------------------------------------------------- #
# Date detection
# --------------------------------------------------------------------------- #

@pytest.fixture
def loader():
    return DataLoader()


def test_iso_date_strings_are_converted(loader):
    df = pd.DataFrame({
        "admission_date": ["2024-01-10", "2024-02-15", "2024-03-20"],
        "value": [1, 2, 3],
    })

    result = loader._detect_and_convert_dates(df)

    assert pd.api.types.is_datetime64_any_dtype(result["admission_date"])
    assert not pd.api.types.is_datetime64_any_dtype(result["value"])


def test_datetime_with_time_component_is_converted(loader):
    df = pd.DataFrame({
        "timestamp": ["2024-01-10 14:30:00", "2024-02-15 09:15:00"],
    })

    result = loader._detect_and_convert_dates(df)

    assert pd.api.types.is_datetime64_any_dtype(result["timestamp"])
    assert result["timestamp"].iloc[0].hour == 14
    assert result["timestamp"].iloc[0].minute == 30


def test_date_detection_by_column_name(loader):
    df = pd.DataFrame({
        "created_date": ["2024-01-10", "2024-02-15"],
        "dob": ["1990-05-15", "1985-08-20"],
        "regular_column": ["abc", "def"],
    })

    result = loader._detect_and_convert_dates(df)

    assert pd.api.types.is_datetime64_any_dtype(result["created_date"])
    assert pd.api.types.is_datetime64_any_dtype(result["dob"])
    assert not pd.api.types.is_datetime64_any_dtype(result["regular_column"])


# --------------------------------------------------------------------------- #
# Categorical dtype
# --------------------------------------------------------------------------- #

def test_categorical_dtype_reports_python_type_category(extractor):
    """is_categorical_dtype() is deprecated; the reported type must not change."""
    series = pd.Series(["a", "b", "a"], dtype="category")

    assert extractor._get_python_type(series) == "category"


def test_categorical_column_extraction_does_not_warn(extractor, recwarn):
    """Deprecated pandas API must not be reached during extraction."""
    df = pd.DataFrame({"grade": pd.Series(["low", "high"] * 10, dtype="category")})

    extractor.extract(df)

    deprecations = [
        w for w in recwarn
        if issubclass(w.category, (DeprecationWarning, FutureWarning))
        and "is_categorical_dtype" in str(w.message)
    ]
    assert not deprecations, f"deprecated pandas API used: {deprecations}"
