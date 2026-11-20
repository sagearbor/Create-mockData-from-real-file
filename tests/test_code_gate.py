"""The screen that reads a generation script before it is allowed to run."""
import pytest

from src.core import code_gate

GOOD = '''
import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta

def generate_synthetic_data():
    random.seed(1); np.random.seed(1)
    n = 5
    start = datetime(2024, 1, 1)
    df = pd.DataFrame({
        "id": [f"P{i:03d}" for i in range(n)],
        "when": [start + timedelta(days=int(d)) for d in np.random.randint(0, 30, n)],
        "score": np.round(np.random.normal(5, 2, n), 2),
        "site": np.random.choice(["North", "South"], n, p=[0.6, 0.4]),
    })
    df["when"] = pd.to_datetime(df["when"])
    return df.sort_values("id").reset_index(drop=True)

if __name__ == "__main__":
    pass
result = generate_synthetic_data()
'''


def test_ordinary_generation_script_passes():
    assert code_gate.find_problems(GOOD) == []
    code_gate.check(GOOD)


@pytest.mark.parametrize("snippet, word", [
    ("import os\nresult = os.listdir('.')", "os"),
    ("import subprocess", "subprocess"),
    ("import socket", "socket"),
    ("from pathlib import Path", "pathlib"),
    ("import urllib.request", "urllib"),
    ("import pickle", "pickle"),
    ("import importlib", "importlib"),
    ("from . import x", "import from"),
    ("result = open('/etc/passwd').read()", "open"),
    ("eval('1+1')", "eval"),
    ("exec('x=1')", "exec"),
    ("__import__('os')", "__import__"),
    ("getattr(x, 'y')", "getattr"),
    ("globals()", "globals"),
    ("x = ().__class__.__bases__", "__class__"),
    ("import pandas as pd\nresult = pd.read_csv('/app/data/cache/x.json')", "read_csv"),
    ("import pandas as pd\npd.DataFrame().to_csv('/app/x')", "to_csv"),
    ("import pandas as pd\npd.DataFrame().to_pickle('/app/x')", "to_pickle"),
    ("import numpy as np\nnp.load('x.npy', allow_pickle=True)", "load"),
    ("import pandas as pd\npd.eval('1+1')", "eval"),
    ("import pandas as pd\npd.DataFrame().query('a > 1')", "query"),
    ("import pandas as pd\nx = pd.io.common.os", ".io"),
    ("import numpy as np\nx = np.os", ".os"),
    ("import operator\nf = operator.attrgetter('a')", "attrgetter"),
    ("x = '{0.__class__}'.format(1)", "double-underscore"),
    ("T = type('T', (), {})", "type()"),
    ("from numpy import load", "load"),
])
def test_dangerous_constructs_are_refused(snippet, word):
    problems = code_gate.find_problems(snippet)
    assert problems, snippet
    assert any(word in p for p in problems), problems
    with pytest.raises(code_gate.CodeRejected):
        code_gate.check(snippet)


def test_reasons_name_the_line_and_quote_only_the_script():
    problems = code_gate.find_problems("x = 1\nimport os\n")
    assert problems == ["line 2: import of 'os' is not allowed"]


def test_text_that_does_not_parse_is_left_to_the_runner():
    assert code_gate.find_problems("def f(:\n") is None
    code_gate.check("def f(:\n")  # no exception: nothing runs in a file that does not parse


def test_main_guard_and_ordinary_text_are_allowed():
    assert code_gate.find_problems('if __name__ == "__main__":\n    x = "first_name"\n') == []
