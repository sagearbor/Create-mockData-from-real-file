"""Screen a model-written (or cached) generation script before it is run.

The script only needs to build a table with pandas and numpy. Anything else it
asks for (files, the network, processes, the interpreter's own internals) is
refused here, before the script is started.

This is a screen, not isolation: it narrows what a script can do by reading its
syntax tree, and a script that passes still runs with the application's user.
Real isolation (a separate worker with no network, no cloud identity and no view
of the application) is tracked separately and this module does not replace it.

What is refused:

* importing anything outside ``ALLOWED_IMPORTS``;
* the names in ``FORBIDDEN_NAMES`` (``open``, ``eval``, ``exec``, ``getattr``, ...);
* any attribute whose name starts with two underscores, and the attribute names
  in ``FORBIDDEN_ATTRIBUTES`` (file readers and writers of pandas/numpy, ``eval``
  and ``query``, and doors to other modules such as ``.os`` or ``.io``);
* text constants that contain a double-underscore name (used to reach
  internals through string formatting or name lookups).
"""

from __future__ import annotations

import ast
import re
from typing import List, Optional

# Top-level modules a generation script may import.
ALLOWED_IMPORTS = frozenset({
    "pandas", "numpy", "random", "datetime", "math", "string", "re", "uuid",
    "itertools", "collections", "decimal", "fractions", "statistics", "typing",
    "time", "calendar", "json", "functools", "secrets", "textwrap", "enum",
    "dataclasses", "copy", "bisect", "heapq", "numbers", "zoneinfo", "dateutil",
    "faker", "__future__",
})

# Builtins that open files, run text as code, or look things up by name.
FORBIDDEN_NAMES = frozenset({
    "open", "eval", "exec", "compile", "__import__", "input", "breakpoint",
    "globals", "locals", "vars", "getattr", "setattr", "delattr", "memoryview",
    "help", "exit", "quit", "__builtins__", "__loader__", "__spec__", "__file__",
})

# Double-underscore names a script may legitimately use as plain names.
ALLOWED_DUNDER_NAMES = frozenset({"__name__"})

FORBIDDEN_ATTRIBUTES = frozenset({
    # pandas / numpy readers and writers
    "read_csv", "read_excel", "read_json", "read_pickle", "read_parquet", "read_html",
    "read_sql", "read_sql_query", "read_sql_table", "read_table", "read_fwf", "read_xml",
    "read_feather", "read_hdf", "read_clipboard", "read_sas", "read_spss", "read_stata",
    "read_orc", "read_gbq",
    "to_pickle", "to_csv", "to_excel", "to_parquet", "to_hdf", "to_feather", "to_sql",
    "to_clipboard", "to_stata", "to_orc", "to_xml", "to_html", "to_latex", "to_markdown",
    "to_gbq",
    "load", "save", "savez", "savez_compressed", "savetxt", "loadtxt", "genfromtxt",
    "fromfile", "tofile", "memmap", "DataSource", "fromregex", "dump",
    # text evaluated as code
    "eval", "query",
    # lookups by name
    "attrgetter", "methodcaller",
    # doors to other modules
    "os", "sys", "subprocess", "builtins", "importlib", "io", "pathlib", "shutil",
    "socket", "ctypes", "ctypeslib", "pickle", "marshal", "shelve", "tempfile", "glob",
    "urllib", "requests", "http", "compat", "testing", "distutils", "f2py", "lib",
    "core", "environ", "getenv", "system", "popen",
})

_DUNDER_IN_TEXT = re.compile(r"__[A-Za-z]\w*__")


class CodeRejected(ValueError):
    """The script asks for something a generation script may not use."""

    def __init__(self, problems: List[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def _line(node: ast.AST) -> str:
    return f"line {getattr(node, 'lineno', '?')}"


def find_problems(code: str, max_problems: int = 10) -> Optional[List[str]]:
    """Return the reasons the script is refused, or an empty list if it may run.

    Returns ``None`` when the text does not parse: the caller lets the normal
    run report the syntax error (nothing executes in a file that does not parse).
    """
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError):
        return None

    problems: List[str] = []

    def add(message: str) -> None:
        if len(problems) < max_problems and message not in problems:
            problems.append(message)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in ALLOWED_IMPORTS:
                    add(f"{_line(node)}: import of '{root}' is not allowed")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if node.level or root not in ALLOWED_IMPORTS:
                add(f"{_line(node)}: import from '{node.module or '.'}' is not allowed")
            for alias in node.names:
                if alias.name in FORBIDDEN_ATTRIBUTES or alias.name.startswith("__"):
                    add(f"{_line(node)}: importing '{alias.name}' is not allowed")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES:
                add(f"{_line(node)}: use of '{node.id}' is not allowed")
            elif node.id.startswith("__") and node.id not in ALLOWED_DUNDER_NAMES:
                add(f"{_line(node)}: use of '{node.id}' is not allowed")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                add(f"{_line(node)}: attribute '{node.attr}' is not allowed")
            elif node.attr in FORBIDDEN_ATTRIBUTES:
                add(f"{_line(node)}: '.{node.attr}' is not allowed")
        elif isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
            text = node.value if isinstance(node.value, str) else node.value.decode("latin-1")
            if text != "__main__" and _DUNDER_IN_TEXT.search(text):
                add(f"{_line(node)}: text containing a double-underscore name is not allowed")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "type" and len(node.args) == 3:
            add(f"{_line(node)}: building a class with type() is not allowed")
    return problems


def check(code: str) -> None:
    """Raise :class:`CodeRejected` if the script may not run."""
    problems = find_problems(code)
    if problems:
        raise CodeRejected(problems)
