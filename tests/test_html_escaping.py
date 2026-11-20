"""Text from uploaded files and server responses is escaped before it is inserted as HTML.

A column name such as ``<img src=x onerror=...>`` used to be written into the page with
innerHTML by the metadata summary and by the dashboard's cache list. These checks read the
page scripts and fail if a dynamic value is interpolated into an HTML string unescaped.
"""
import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "src" / "web"
APP_JS = (WEB / "static" / "js" / "app.js").read_text()
DASHBOARD = (WEB / "dashboard.html").read_text()


def _function_body(source, name):
    start = source.index(f"function {name}(")
    depth, i = 0, source.index("{", start)
    for j in range(i, len(source)):
        depth += source[j] == "{"
        depth -= source[j] == "}"
        if depth == 0:
            return source[start:j + 1]
    raise AssertionError(f"unterminated function {name}")


def _unescaped_interpolations(body, allowed=()):
    """${...} expressions inside the body that are not wrapped in an escaper or allow-listed."""
    found = []
    for expr in re.findall(r"\$\{([^}]*)\}", body):
        expr = expr.strip()
        if expr.startswith(("escapeHtml(", "esc(")) or expr in allowed:
            continue
        found.append(expr)
    return found


def test_app_js_has_one_shared_escaper():
    assert APP_JS.count("function escapeHtml(") == 1
    body = _function_body(APP_JS, "escapeHtml")
    for ch in ("&amp;", "&lt;", "&gt;", "&quot;", "&#39;"):
        assert ch in body


def test_metadata_summary_escapes_column_names():
    assert _unescaped_interpolations(_function_body(APP_JS, "displayMetadata")) == []


def test_results_and_table_helpers_escape_names_and_cells():
    assert _unescaped_interpolations(_function_body(APP_JS, "displayResults")) == []
    assert _unescaped_interpolations(_function_body(APP_JS, "createTableFromJSON")) == []


def test_dictionary_columns_are_escaped():
    body = _function_body(APP_JS, "showLoadedDictionary")
    html_part = body[body.index("columnsDiv.innerHTML"):]  # the only HTML built in this function
    left = [e for e in _unescaped_interpolations(html_part) if "allowed_values.length > 3" not in e]
    assert left == []


def test_dashboard_escapes_cache_columns_and_log_fields():
    assert "function escapeHtml(" in DASHBOARD
    assert "escapeHtml((entry.columns || []).join(', ')" in DASHBOARD
    table = _function_body(DASHBOARD, "updateLogsTable")
    for field in ("log.method", "log.num_rows", "log.num_columns"):
        assert f"${{escapeHtml({field})}}" in table
        assert f"${{{field}}}" not in table


def test_escaper_neutralises_markup():
    """Run the real escaper (node, when present) on a hostile column name."""
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    script = _function_body(APP_JS, "escapeHtml") + \
        "\nprocess.stdout.write(escapeHtml('<img src=x onerror=\"alert(1)\">&\\''));"
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=20).stdout
    assert out == "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;&amp;&#39;"
