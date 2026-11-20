"""Screen a model-written (or cached) generation script before it is run.

The script only needs to build a table with pandas and numpy. Anything else it
asks for (files, the network, processes, the interpreter's own internals) is
refused here, before the script is started.

This is a screen, not isolation. It narrows what a script can do by reading its
syntax tree; it cannot follow values computed at run time, and a script that
passes still runs with the application's user. Real isolation (a separate worker
with no network, no cloud identity and no view of the application) is tracked
separately and this module does not replace it.

What is refused:

* a script that does not parse, or is too deep or too large to check (fail closed);
* importing any module that is not listed, by full dotted path, in
  ``ALLOWED_MODULES``;
* for the standard-library modules, any name not listed for that module in
  ``MODULE_NAMES`` (an allowed module can re-export a dangerous one, so only
  named functions and classes may be taken from it);
* ``match`` statements (their class patterns read attributes by name);
* the names in ``FORBIDDEN_NAMES`` (``open``, ``eval``, ``exec``, ``getattr``, ...);
* any attribute whose name starts with an underscore;
* any ``read_*`` attribute, and any ``to_*`` attribute not in ``ALLOWED_TO_METHODS``;
* the attribute names in ``FORBIDDEN_ATTRIBUTES`` (other readers and writers,
  ``eval`` and ``query``, lookups by name, and doors to other modules such as
  ``.os`` or ``.io``);
* ``.format`` / ``.format_map`` on anything but a text literal, and text
  literals that contain a double-underscore name (both are ways to reach
  internals through string formatting).
"""

from __future__ import annotations

import ast
import re
from typing import List

# Modules a generation script may import, by full dotted path.
ALLOWED_MODULES = frozenset({
    "pandas", "numpy", "numpy.random", "random", "datetime", "math", "string", "re",
    "uuid", "itertools", "collections", "decimal", "typing", "__future__",
})

# pandas and numpy are too large to list name by name; they are covered by the
# read_* / to_* rules and FORBIDDEN_ATTRIBUTES. Every other module may only be
# used through the names listed here ("*" = any public name; the module has no
# re-exported modules or file access).
MODULE_NAMES = {
    "random": frozenset({
        "seed", "random", "randint", "randrange", "choice", "choices", "sample", "shuffle",
        "uniform", "gauss", "normalvariate", "lognormvariate", "expovariate", "betavariate",
        "gammavariate", "triangular", "weibullvariate", "paretovariate", "vonmisesvariate",
        "getrandbits"}),
    "datetime": frozenset({"datetime", "date", "time", "timedelta", "timezone"}),
    "math": frozenset({"*"}),
    "itertools": frozenset({"*"}),
    "string": frozenset({
        "ascii_letters", "ascii_lowercase", "ascii_uppercase", "digits", "hexdigits",
        "octdigits", "punctuation", "whitespace", "capwords"}),
    "re": frozenset({
        "compile", "match", "fullmatch", "search", "sub", "subn", "split", "findall",
        "finditer", "escape", "IGNORECASE", "I", "MULTILINE", "M"}),
    "uuid": frozenset({"uuid4", "UUID"}),
    "collections": frozenset({"Counter", "defaultdict", "OrderedDict", "deque", "namedtuple"}),
    "decimal": frozenset({"Decimal", "ROUND_HALF_UP", "ROUND_HALF_EVEN", "ROUND_DOWN", "ROUND_UP"}),
    "typing": frozenset({
        "List", "Dict", "Optional", "Tuple", "Any", "Union", "Set", "Sequence", "Iterable",
        "Callable"}),
    "__future__": frozenset({"annotations"}),
}

# Builtins that open files, run text as code, or look things up by name.
FORBIDDEN_NAMES = frozenset({
    "open", "eval", "exec", "compile", "__import__", "input", "breakpoint",
    "globals", "locals", "vars", "getattr", "setattr", "delattr", "memoryview",
    "help", "exit", "quit", "__builtins__", "__loader__", "__spec__", "__file__",
})

# Double-underscore names a script may legitimately use as plain names.
ALLOWED_DUNDER_NAMES = frozenset({"__name__"})

# ``to_*`` methods that convert in memory and take no file target.
ALLOWED_TO_METHODS = frozenset({
    "to_datetime", "to_numeric", "to_timedelta", "to_dict", "to_list", "to_numpy",
    "to_frame", "to_series", "to_period", "to_timestamp", "to_pydatetime",
    "to_pytimedelta", "to_julian_date", "to_flat_index", "to_records",
})

FORBIDDEN_ATTRIBUTES = frozenset({
    # readers and writers not caught by the read_* / to_* rules
    "load", "save", "savez", "savez_compressed", "savetxt", "loadtxt", "genfromtxt",
    "fromfile", "tofile", "memmap", "DataSource", "fromregex", "dump", "open",
    "ExcelFile", "ExcelWriter", "HDFStore", "api", "TarFile", "ZipFile",
    "lookfor", "source", "info", "show_config", "show_versions", "get_include",
    # text evaluated as code
    "eval", "query",
    # lookups by name, and formatters that can walk attributes
    "attrgetter", "methodcaller", "Formatter", "get_field", "format_field", "vformat",
    "get_type_hints", "ForwardRef",
    # doors to other modules
    "os", "sys", "subprocess", "builtins", "importlib", "io", "pathlib", "shutil",
    "socket", "ctypes", "ctypeslib", "pickle", "marshal", "shelve", "tempfile", "glob",
    "urllib", "requests", "http", "compat", "testing", "distutils", "f2py", "lib",
    "core", "util", "environ", "getenv", "system", "popen", "Popen", "run", "codecs",
    "tarfile", "zipfile", "zoneinfo", "factory", "import_module",
})
_FORBIDDEN_PREFIXES = ("exec", "spawn", "fork")

_FORMAT_METHODS = frozenset({"format", "format_map"})
_DUNDER_IN_TEXT = re.compile(r"__[A-Za-z]\w*__")
MAX_SCRIPT_CHARS = 200_000


class CodeRejected(ValueError):
    """The script asks for something a generation script may not use."""

    def __init__(self, problems: List[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def _line(node: ast.AST) -> str:
    return f"line {getattr(node, 'lineno', '?')}"


def _attribute_problem(name: str) -> str:
    """Why this attribute (or imported name) is refused, or '' if it is allowed."""
    if name.startswith("_"):
        return f"'{name}' (names starting with an underscore) is not allowed"
    if name.startswith("read_") or (name.startswith("to_") and name not in ALLOWED_TO_METHODS):
        return f"'.{name}' (reading or writing files) is not allowed"
    if name in FORBIDDEN_ATTRIBUTES or name.startswith(_FORBIDDEN_PREFIXES):
        return f"'.{name}' is not allowed"
    return ""


def _module_name_problem(module: str, name: str) -> str:
    """Why `name` may not be taken from `module`, or '' (pandas/numpy use the general rules)."""
    allowed = MODULE_NAMES.get(module)
    if allowed is None or name in allowed or ("*" in allowed and not name.startswith("_")):
        return ""
    return f"'{name}' may not be used from '{module}'"


def find_problems(code: str, max_problems: int = 10) -> List[str]:
    """Return the reasons the script is refused; an empty list means it may run.

    The reasons quote only the script's own text (names and line numbers).
    """
    if len(code) > MAX_SCRIPT_CHARS:
        return [f"the script is too long to check ({len(code)} characters)"]
    try:
        tree = ast.parse(code)
    except SyntaxError as err:
        return [f"line {err.lineno or '?'}: the script does not parse ({err.msg})"]
    except (ValueError, RecursionError, MemoryError) as err:
        return [f"the script could not be checked ({type(err).__name__})"]

    problems: List[str] = []

    def add(message: str) -> None:
        if len(problems) < max_problems and message not in problems:
            problems.append(message)

    # Names the script binds to a listed standard-library module (`import random as r`).
    module_aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in MODULE_NAMES:
                    module_aliases[alias.asname or alias.name] = alias.name

    for node in ast.walk(tree):
        if isinstance(node, ast.Match):
            add(f"{_line(node)}: 'match' statements are not allowed")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in ALLOWED_MODULES:
                    add(f"{_line(node)}: import of '{alias.name}' is not allowed")
        elif isinstance(node, ast.ImportFrom):
            if node.level or (node.module or "") not in ALLOWED_MODULES:
                add(f"{_line(node)}: import from '{node.module or '.'}' is not allowed")
            for alias in node.names:
                full = f"{node.module}.{alias.name}"
                if alias.name == "*":
                    add(f"{_line(node)}: 'import *' is not allowed")
                elif full in ALLOWED_MODULES:
                    continue  # e.g. `from numpy import random`
                else:
                    why = _attribute_problem(alias.name) or \
                        _module_name_problem(node.module or "", alias.name)
                    if why:
                        add(f"{_line(node)}: importing {why}")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES:
                add(f"{_line(node)}: use of '{node.id}' is not allowed")
            elif node.id.startswith("__") and node.id not in ALLOWED_DUNDER_NAMES:
                add(f"{_line(node)}: use of '{node.id}' is not allowed")
        elif isinstance(node, ast.Attribute):
            why = _attribute_problem(node.attr)
            if not why and isinstance(node.value, ast.Name) and node.value.id in module_aliases:
                why = _module_name_problem(module_aliases[node.value.id], node.attr)
            if why:
                add(f"{_line(node)}: {why}")
            elif node.attr in _FORMAT_METHODS and not (
                    isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
                add(f"{_line(node)}: '.{node.attr}' is only allowed on a text literal")
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
