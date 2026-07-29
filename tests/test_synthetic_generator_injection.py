"""Security regression tests for the template-based (no-LLM) fallback generator.

The fallback path builds Python source text from metadata and then executes it.
Metadata is derived from an uploaded file, so every value interpolated into that
source is attacker-controlled. These tests pin the requirement that untrusted
text can never escape into executable position.

The payloads read their target path from the ``BYOD_PWN_PATH`` environment
variable rather than embedding it literally, so that the exploit string itself
stays free of words (``test``, ``date``, ...) that would steer metadata
extraction onto a different code branch.
"""

import ast

import pandas as pd
import pytest

from src.core.metadata_extractor import MetadataExtractor
from src.core.synthetic_generator import SyntheticDataGenerator

# Reads the sentinel path from the environment at exec time and touches it.
PAYLOAD_BODY = "open(__import__('os').environ['BYOD_PWN_PATH'], 'w').write('pwned')"


def _metadata_for(df: pd.DataFrame) -> dict:
    return MetadataExtractor().extract(df)


def _unique_strings(prefix: str, count: int = 12) -> list:
    """Values unique enough to avoid the categorical code path."""
    return [f"{prefix}-{i:03d}" for i in range(count)]


@pytest.fixture
def sentinel(tmp_path, monkeypatch):
    """A path the injected payload would create if it ever executed."""
    path = tmp_path / "pwned"
    monkeypatch.setenv("BYOD_PWN_PATH", str(path))
    return path


def test_column_header_cannot_inject_executable_python(sentinel):
    """A CSV header carrying Python must not execute when the fallback runs."""
    malicious_header = f"col'] = [0] * num_rows; {PAYLOAD_BODY}; data['other"

    df = pd.DataFrame({malicious_header: _unique_strings("v")})
    generator = SyntheticDataGenerator()

    code, method = generator._generate_fallback_code(_metadata_for(df), num_rows=5)

    assert method == "fallback"
    result = generator._execute_generation_code(code, randomize_seed=False)

    assert not sentinel.exists(), "injected code from the CSV header was executed"
    assert list(result.columns) == [malicious_header]
    assert len(result) == 5


def test_column_header_with_newline_cannot_inject_executable_python(sentinel):
    """A quoted CSV header may contain newlines; comments must not leak them."""
    malicious_header = f"col\n{PAYLOAD_BODY}\ntrailing"

    df = pd.DataFrame({malicious_header: _unique_strings("w")})
    generator = SyntheticDataGenerator()

    code, _ = generator._generate_fallback_code(_metadata_for(df), num_rows=5)
    result = generator._execute_generation_code(code, randomize_seed=False)

    assert not sentinel.exists(), "injected code from a multi-line header was executed"
    assert list(result.columns) == [malicious_header]


def test_cell_values_cannot_inject_executable_python(sentinel):
    """Preserved categorical values come from cells and are equally untrusted."""
    malicious_value = f"a'; {PAYLOAD_BODY}; b = ['"

    df = pd.DataFrame({"status": [malicious_value, "ok"] * 10})
    generator = SyntheticDataGenerator()

    code, _ = generator._generate_fallback_code(_metadata_for(df), num_rows=5)
    result = generator._execute_generation_code(code, randomize_seed=False)

    assert not sentinel.exists(), "injected code from a cell value was executed"
    assert list(result.columns) == ["status"]


@pytest.mark.parametrize(
    "header",
    [
        "col with spaces",
        "col-with-dashes",
        "col.with.dots",
        "it's quoted",
        'has "double" quotes',
        "back\\slash",
        "unicode-héader",
        "1_starts_with_digit",
        "class",  # Python keyword
    ],
)
def test_awkward_but_legitimate_headers_round_trip(header):
    """Headers that are not valid Python identifiers must still generate data."""
    df = pd.DataFrame({header: _unique_strings("x")})
    generator = SyntheticDataGenerator()

    code, _ = generator._generate_fallback_code(_metadata_for(df), num_rows=5)
    ast.parse(code)  # must be syntactically valid before we execute it

    result = generator._execute_generation_code(code, randomize_seed=False)
    assert list(result.columns) == [header]
    assert len(result) == 5


def test_fallback_code_assigns_only_to_declared_columns():
    """Every ``data[...]`` key in the generated source is a declared column."""
    df = pd.DataFrame(
        {
            "patient_id": _unique_strings("P"),
            "age": list(range(30, 42)),
            "visit_date": pd.date_range("2024-01-01", periods=12),
            "sex": ["M", "F"] * 6,
        }
    )
    metadata = _metadata_for(df)
    generator = SyntheticDataGenerator()

    code, _ = generator._generate_fallback_code(metadata, num_rows=5)
    tree = ast.parse(code)

    declared = {col["name"] for col in metadata["structure"]["columns"]}
    keys = {
        node.slice.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "data"
        and isinstance(node.slice, ast.Constant)
    }

    assert keys == declared
