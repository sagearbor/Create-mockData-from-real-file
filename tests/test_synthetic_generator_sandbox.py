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


def test_script_that_reads_the_environment_is_refused_before_it_runs():
    """The screen stops the probe; the child process is never started."""
    import pytest
    from src.core.synthetic_generator import CodeExecutionError

    with pytest.raises(CodeExecutionError) as exc:
        SyntheticDataGenerator()._execute_generation_code(LEAK_PROBE, randomize_seed=False)
    assert "refused before running" in str(exc.value)
    assert "import of 'os' is not allowed" in exc.value.sandbox_stderr


def test_generated_code_cannot_read_azure_credentials(monkeypatch):
    """Second line of defence: even with the screen switched off, secrets in the
    parent environment are not passed to the child process."""
    from src.core import code_gate
    monkeypatch.setattr(code_gate, "check", lambda code: None)
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


# --------------------------------------------------------------------------- #
# The result comes back as checked JSON, never as a pickle
# --------------------------------------------------------------------------- #
TYPES_CODE = """
import pandas as pd
import numpy as np
from datetime import date, datetime

def generate_synthetic_data():
    return pd.DataFrame({
        'n': np.array([1, 2, 3], dtype='int64'),
        'x': [1.5, None, 3.25],
        'flag': [True, False, True],
        'when': pd.to_datetime(['2024-01-02 00:00:00', '2024-03-04 05:06:07', None]),
        'day': [date(2024, 1, 2), date(2024, 1, 3), None],
        'stamp': [datetime(2024, 1, 2, 3, 4, 5), None, datetime(2024, 1, 3)],
        'label': ['a', None, 'c'],
        'cat': pd.Categorical(['u', 'v', 'u']),
    })

result = generate_synthetic_data()
"""


def test_result_round_trips_with_its_types():
    df = SyntheticDataGenerator()._execute_generation_code(TYPES_CODE, randomize_seed=False)
    assert list(df.columns) == ['n', 'x', 'flag', 'when', 'day', 'stamp', 'label', 'cat']
    assert str(df['n'].dtype) == 'int64' and df['n'].tolist() == [1, 2, 3]
    assert df['flag'].tolist() == [True, False, True]
    assert str(df['when'].dtype).startswith('datetime64')
    assert df['when'].iloc[1] == pd.Timestamp('2024-03-04 05:06:07') and pd.isna(df['when'].iloc[2])
    assert df['day'].tolist()[:2] == ['2024-01-02', '2024-01-03']        # as a CSV would show a date
    assert df['stamp'].iloc[0] == pd.Timestamp('2024-01-02 03:04:05')  # pandas makes this a datetime column
    assert df['label'].iloc[0] == 'a' and pd.isna(df['label'].iloc[1])
    assert df['cat'].tolist() == ['u', 'v', 'u']
    assert pd.isna(df['x'].iloc[1]) and df['x'].iloc[2] == 3.25


def test_no_pickle_is_read_from_the_child(monkeypatch):
    """A file the child leaves behind is never unpickled."""
    def forbidden(*a, **k):
        raise AssertionError("read_pickle must not be called")

    monkeypatch.setattr(pd, "read_pickle", forbidden)
    df = SyntheticDataGenerator()._execute_generation_code(AGES_CODE, randomize_seed=False)
    assert len(df) == 5
    import inspect
    from src.core import synthetic_generator
    source = inspect.getsource(synthetic_generator)
    assert "read_pickle" not in source and "to_pickle" not in source and "import pickle" not in source


def test_result_that_is_not_a_table_is_an_error():
    import pytest
    from src.core.synthetic_generator import CodeExecutionError

    with pytest.raises(CodeExecutionError):
        SyntheticDataGenerator()._execute_generation_code("result = [1, 2, 3]\n", randomize_seed=False)


def test_malformed_result_file_is_refused(tmp_path):
    import pytest
    from src.core.synthetic_generator import CodeExecutionError, _load_result

    for text in ('[1, 2]', '{"columns": ["a"], "data": [[1, 2]], "dtypes": ["int64"]}',
                 '{"columns": ["a"], "data": [[1]]}', 'not json', '{"columns": [["x"]], "data": [], "dtypes": ["o"]}'):
        f = tmp_path / "r.json"
        f.write_text(text)
        with pytest.raises(CodeExecutionError):
            _load_result(f)


def test_failure_summary_names_the_error_and_the_line_but_not_the_runtime_text():
    import pytest
    from src.core.synthetic_generator import CodeExecutionError

    code = "values = ['SECRET-CELL-777']\nx = int(values[0])\nresult = None\n"
    with pytest.raises(CodeExecutionError) as exc:
        SyntheticDataGenerator()._execute_generation_code(code, randomize_seed=False)
    summary = exc.value.sandbox_stderr
    assert summary.startswith("ValueError at line 2 of the script: x = int(values[0])")
    assert "SECRET-CELL-777" not in summary  # the message text of the error is not passed on


def test_script_that_runs_too_long_is_stopped(monkeypatch):
    import pytest
    from src.core import synthetic_generator
    from src.core.synthetic_generator import CodeExecutionError

    monkeypatch.setattr(synthetic_generator, "SANDBOX_TIMEOUT_SECONDS", 2)
    with pytest.raises(CodeExecutionError) as exc:
        SyntheticDataGenerator()._execute_generation_code(
            "while True:\n    pass\n", randomize_seed=False)
    assert "timed out" in str(exc.value)
