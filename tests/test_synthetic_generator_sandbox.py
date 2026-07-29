"""Tests for the isolation of the generated-code execution subprocess.

Generated code is executed, so the process running it must not carry secrets
that the code has no reason to see (Azure OpenAI keys, cloud metadata tokens).
"""

import pandas as pd

from src.core.synthetic_generator import SyntheticDataGenerator

LEAK_PROBE = """
import os
import pandas as pd

def generate_synthetic_data():
    return pd.DataFrame({'leaked': [os.environ.get('AZURE_OPENAI_API_KEY', 'absent')]})

result = generate_synthetic_data()
"""


def test_generated_code_cannot_read_azure_credentials(monkeypatch):
    """Secrets in the parent environment are not passed to the exec subprocess."""
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "super-secret-key")

    generator = SyntheticDataGenerator()
    result = generator._execute_generation_code(LEAK_PROBE, randomize_seed=False)

    assert result["leaked"].tolist() == ["absent"]


def test_generation_still_works_with_a_scrubbed_environment():
    """Scrubbing the environment must not break ordinary generation."""
    df = pd.DataFrame({"age": list(range(20, 40))})

    from src.core.metadata_extractor import MetadataExtractor

    metadata = MetadataExtractor().extract(df)
    generator = SyntheticDataGenerator()

    code, _ = generator._generate_fallback_code(metadata, num_rows=5)
    result = generator._execute_generation_code(code, randomize_seed=False)

    assert list(result.columns) == ["age"]
    assert len(result) == 5
