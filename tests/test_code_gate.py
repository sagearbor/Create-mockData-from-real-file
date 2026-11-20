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
    ("import os\nresult = os.listdir('.')", "'os'"),
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


def test_text_that_cannot_be_checked_is_refused():
    assert "does not parse" in code_gate.find_problems("def f(:\n")[0]
    with pytest.raises(code_gate.CodeRejected):
        code_gate.check("def f(:\n")
    assert "too long" in code_gate.find_problems("x = 1\n" * 100_000)[0]
    deep = "x = " + "(" * 5000 + "1" + ")" * 5000
    assert code_gate.find_problems(deep)  # too deep to parse: refused, never passed


@pytest.mark.parametrize("snippet, word", [
    ("import pandas.io.common", "pandas.io.common"),
    ("from pandas import io", "io"),
    ("from pandas.io import common", "pandas.io"),
    ("from numpy import *", "import *"),
    ("from string import Formatter", "Formatter"),
    ("import string\nstring.Formatter().get_field('a', (), {})", "Formatter"),
    ("from typing import get_type_hints", "get_type_hints"),
    ("import typing\ntyping.ForwardRef('x')", "ForwardRef"),
    ("import typing\ntyping._eval_type", "underscore"),
    ("import functools", "functools"),
    ("import dataclasses", "dataclasses"),
    ("import copy", "copy"),
    ("import pandas as pd\npd.DataFrame().to_json('/app/x')", "to_json"),
    ("import pandas as pd\npd.DataFrame().to_string('/app/x')", "to_string"),
    ("import pandas as pd\npd.ExcelWriter('/app/x')", "ExcelWriter"),
    ("import pandas as pd\npd.HDFStore('/app/x')", "HDFStore"),
    ("import pandas as pd\npd.api.types", "api"),
    ("import pandas as pd\npd.read_anything_new('x')", "read_anything_new"),
    ("fmt = '{0._' + '_class_' + '_}'\nfmt.format(1)", "text literal"),
    ("x = 1\nx._private", "underscore"),
])
def test_review_follow_up_cases_are_refused(snippet, word):
    problems = code_gate.find_problems(snippet)
    assert problems and any(word in p for p in problems), (snippet, problems)


@pytest.mark.parametrize("snippet, word", [
    ("import json", "json"),
    ("import faker", "faker"),
    ("import time", "time"),
    ("import random\nrandom.SystemRandom", "SystemRandom"),
    ("import random as r\nr.os", "os"),
    ("import datetime\ndatetime.sys", "sys"),
    ("import re\nre.sre_parse", "sre_parse"),
    ("import string as s\ns.Template", "Template"),
    ("from collections import abc", "abc"),
    ("from decimal import localcontext", "localcontext"),
    ("import uuid\nuuid.getnode()", "getnode"),
    ("import numpy as np\nnp.lookfor('x')", "lookfor"),
    ("import pandas as pd\npd.show_versions()", "show_versions"),
    ("x = 1\nx.open('f')", "open"),
    ("x = 1\nx.import_module('os')", "import_module"),
    ("x = 1\nx.execve", "execve"),
    ("match x:\n    case object(real=r):\n        pass", "match"),
    ("import random\nr = random\nr.seed(1)", "may only be used as"),
    ("import re\nmods = [re]", "may only be used as"),
    ("import datetime as d\nf = lambda m: m\nf(d)", "may only be used as"),
    ("import re\nre.enum", "enum"),
    ("import re\nre.functools", "functools"),
    ("x = 1\nx.bltns", "bltns"),
])
def test_module_re_exports_and_match_are_refused(snippet, word):
    problems = code_gate.find_problems(snippet)
    assert problems and any(word in p for p in problems), (snippet, problems)


def test_in_memory_conversions_and_literal_format_are_allowed():
    ok = (
        "import pandas as pd\nimport numpy as np\nfrom numpy import random as npr\n"
        "import numpy.random\nfrom datetime import datetime, timedelta\nfrom typing import List, Dict\n"
        "d = pd.to_datetime(['2024-01-01'])\nn = pd.to_numeric(['1'])\n"
        "import random\nimport math\nimport string\nimport uuid\nimport re\n"
        "v = random.choice([1, 2]) + math.floor(2.5)\nw = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))\n"
        "u = str(uuid.uuid4())\nm = re.sub(r'\\d', 'x', 'a1')\nt = datetime.now() + timedelta(days=1)\n"
        "df = pd.DataFrame({'a': [1]})\nx = df.to_dict('records')\ny = df['a'].to_numpy().tolist()\n"
        "label = 'ID-{:04d}'.format(7)\nlabel2 = f'ID-{7:04d}'\nresult = df\n"
    )
    assert code_gate.find_problems(ok) == []


def test_main_guard_and_ordinary_text_are_allowed():
    assert code_gate.find_problems('if __name__ == "__main__":\n    x = "first_name"\n') == []
