"""Guards on the pinned dependency lists (ADP-63).

The deployed image installs requirements-aca.txt. These tests read that file as
text (they never import the packages to learn a version) and fail if someone
loosens a pin, reintroduces a version with a published advisory, or brings back
the retired PyPDF2. A final test proves the pypdf-based PDF reader really
extracts text.
"""

import io
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ACA_REQUIREMENTS = REPO_ROOT / "requirements-aca.txt"
OTHER_REQUIREMENTS = [REPO_ROOT / "requirements.txt", REPO_ROOT / "requirements-api.txt"]

# Versions the security audit found in the deployed image, each with published advisories.
KNOWN_BAD = {
    "fastapi": "0.109.0",
    "starlette": "0.35.1",
    "python-multipart": "0.0.6",
    "pypdf2": "3.0.1",
    "aiohttp": "3.9.1",
    "cryptography": "41.0.7",
    "jinja2": "3.1.2",
    "python-dotenv": "1.0.0",
}

# Lowest version with no advisory open (highest "fix version" pip-audit reported
# for the old pins, 2026-11-20). Raise these when a new advisory is published.
MINIMUM_SAFE = {
    "fastapi": "0.109.1",
    "starlette": "1.3.1",
    "python-multipart": "0.0.31",
    "cryptography": "49.0.0",
    "python-dotenv": "1.2.2",
}


def _normalise(name: str) -> str:
    """PEP 503 name: lower case, runs of -_. become one dash, extras dropped."""
    name = name.split("[", 1)[0]
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def _requirement_lines(path: Path) -> list[str]:
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


def _exact_pins(path: Path) -> dict[str, str]:
    """name -> version for every `name==version` line; other lines are ignored."""
    pins = {}
    for line in _requirement_lines(path):
        match = re.fullmatch(r"([A-Za-z0-9._-]+(?:\[[^\]]+\])?)\s*==\s*([A-Za-z0-9.!+_-]+)", line)
        if match:
            pins[_normalise(match.group(1))] = match.group(2)
    return pins


def _version_tuple(version: str) -> tuple[int, ...]:
    parts = []
    for piece in version.split("."):
        digits = re.match(r"\d+", piece)
        if not digits:
            break
        parts.append(int(digits.group()))
    return tuple(parts)


def test_version_tuple_orders_numerically():
    assert _version_tuple("0.0.31") > _version_tuple("0.0.6")
    assert _version_tuple("1.3.1") > _version_tuple("0.47.2")
    assert _version_tuple("0.140.13") > _version_tuple("0.109.1")


def test_aca_requirements_pin_every_line_exactly():
    lines = _requirement_lines(ACA_REQUIREMENTS)
    assert lines, "requirements-aca.txt is empty"
    pins = _exact_pins(ACA_REQUIREMENTS)
    not_exact = [
        line for line in lines
        if _normalise(re.split(r"[=<>!~;\s]", line, maxsplit=1)[0]) not in pins
        or any(op in line for op in (">=", "<=", "~=", "!=", ">", "<", "*"))
    ]
    assert not_exact == [], f"not pinned with a single ==: {not_exact}"


def test_aca_requirements_has_no_known_bad_version():
    pins = _exact_pins(ACA_REQUIREMENTS)
    bad = {name: version for name, version in KNOWN_BAD.items() if pins.get(name) == version}
    assert bad == {}, f"versions with published advisories are back: {bad}"


@pytest.mark.parametrize("path", [ACA_REQUIREMENTS, *OTHER_REQUIREMENTS], ids=lambda p: p.name)
def test_pypdf2_is_gone(path):
    if not path.exists():
        pytest.skip(f"{path.name} is not present here (only requirements-aca.txt ships in the image)")
    names = {_normalise(re.split(r"[=<>!~;\s]", line, maxsplit=1)[0]) for line in _requirement_lines(path)}
    assert "pypdf2" not in names, f"{path.name} still lists the retired PyPDF2"


@pytest.mark.parametrize("name", sorted(MINIMUM_SAFE))
def test_aca_requirements_meet_minimum_safe_versions(name):
    pins = _exact_pins(ACA_REQUIREMENTS)
    assert name in pins, f"{name} must be pinned explicitly in requirements-aca.txt"
    assert _version_tuple(pins[name]) >= _version_tuple(MINIMUM_SAFE[name]), (
        f"{name}=={pins[name]} is below the minimum safe version {MINIMUM_SAFE[name]}"
    )


@pytest.mark.parametrize("path", OTHER_REQUIREMENTS, ids=lambda p: p.name)
def test_other_requirement_files_agree_with_aca(path):
    """Local-dev and API-only files must use the deployed versions for shared packages."""
    if not path.exists():
        pytest.skip(f"{path.name} is not present here")
    aca = _exact_pins(ACA_REQUIREMENTS)
    other = _exact_pins(path)
    differing = {
        name: (other[name], aca[name]) for name in aca.keys() & other.keys() if other[name] != aca[name]
    }
    assert differing == {}, f"{path.name} disagrees with requirements-aca.txt (theirs, aca): {differing}"


@pytest.mark.parametrize("path", OTHER_REQUIREMENTS, ids=lambda p: p.name)
def test_mcp_is_pinned_exactly_where_listed(path):
    """An unpinned mcp once pulled a new major version and crash-looped on import."""
    if not path.exists():
        pytest.skip(f"{path.name} is not present here")
    mcp_lines = [line for line in _requirement_lines(path) if _normalise(re.split(r"[=<>!~;\s]", line, maxsplit=1)[0]) == "mcp"]
    for line in mcp_lines:
        assert re.fullmatch(r"mcp==[0-9][A-Za-z0-9.]*", line), f"{path.name}: mcp must be pinned exactly, got {line!r}"


def _one_page_pdf(text: str) -> bytes:
    """Build a one-page PDF with real text, in memory, using pypdf itself."""
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
    })
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_pdf_dictionary_reader_extracts_text_with_pypdf(monkeypatch):
    pytest.importorskip("pypdf")
    from src.core.data_dictionary import DataDictionary

    try:
        pdf_bytes = _one_page_pdf("patient_id integer unique subject identifier")
    except Exception as exc:  # pypdf internals moved: skip rather than fail on the fixture
        pytest.skip(f"could not build an in-memory PDF with this pypdf: {exc}")
    assert pdf_bytes.startswith(b"%PDF")

    dictionary = DataDictionary()
    seen = []
    # The reader falls back to str(raw bytes) on any error, so capture exactly
    # what it hands on: real extracted text, not the raw file.
    monkeypatch.setattr(dictionary, "_parse_text_with_llm", lambda text: seen.append(text) or {})

    dictionary._parse_pdf(pdf_bytes)

    assert len(seen) == 1
    assert "patient_id integer unique subject identifier" in seen[0]
    assert "%PDF" not in seen[0]
