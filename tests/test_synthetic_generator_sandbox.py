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


AGES_CODE = """
import numpy as np
import pandas as pd

def generate_synthetic_data():
    return pd.DataFrame({'age': np.arange(20, 25)})

result = generate_synthetic_data()
"""


def test_generation_still_works_with_a_scrubbed_environment():
    """Scrubbing the environment must not break ordinary generated code."""
    generator = SyntheticDataGenerator()
    result = generator._execute_generation_code(AGES_CODE, randomize_seed=False)

    assert list(result.columns) == ["age"]
    assert len(result) == 5


def test_broken_generated_code_raises_instead_of_running_in_process():
    """A sandbox failure is an error, never a retry via in-process exec()."""
    import pytest
    from src.core.synthetic_generator import CodeExecutionError

    generator = SyntheticDataGenerator()
    with pytest.raises(CodeExecutionError) as exc:
        generator._execute_generation_code("raise SystemExit(3)\n", randomize_seed=False)
    assert "AI generation failed" in exc.value.user_message
