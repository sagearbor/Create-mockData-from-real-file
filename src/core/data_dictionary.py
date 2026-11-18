"""Data Dictionary Handler for constraint-based data generation.

Shapes understood (see ``ACCEPTED_SHAPES``): the original ones (``{"columns":
{...}}``, a list of ``{"name": ...}`` items, a ``{column: type-or-definition}``
mapping, CSV/Excel/text), plus JSON Schema, Frictionless Table Schema and HL7
FHIR StructureDefinitions (alone or in a Bundle). Anything else is refused with
``UnrecognizedDictionaryError`` instead of being loaded as nonsense columns.

A file may define several tables (a FHIR Bundle, JSON Schema ``$defs``); the
caller then has to name one (``table``), or gets ``DictionaryTableRequired``
listing the names. ``fit_to_prompt_budget`` bounds how much dictionary text is
sent to the model (env ``MOCKDATA_DICTIONARY_PROMPT_MAX_CHARS``).
"""

import copy
import difflib
import json
import os
import pandas as pd
import yaml
from typing import Dict, Any, List, Optional, Tuple, Union
from pathlib import Path
import re

from src.utils.logger import logger

# Characters of dictionary text allowed into one LLM prompt. The dictionary is
# rendered twice there (statistics JSON + constraint lines); both count.
PROMPT_BUDGET_ENV = "MOCKDATA_DICTIONARY_PROMPT_MAX_CHARS"
DEFAULT_PROMPT_BUDGET_CHARS = 60_000

# Largest dictionary file accepted by the web dictionary routes.
MAX_BYTES_ENV = "MOCKDATA_DICTIONARY_MAX_BYTES"
DEFAULT_MAX_BYTES = 64 * 1024 * 1024  # 64 MB: the 34 MB FHIR spec bundle fits

ACCEPTED_SHAPES = (
    "Accepted shapes: a CSV or Excel sheet with one row per column; JSON or YAML "
    "with \"columns\": {name: definition}; a list of {\"name\": ...} objects; a "
    "mapping of column name to a type or definition; JSON Schema (\"properties\" "
    "or \"$defs\"); a Frictionless Table Schema (\"fields\"); a FHIR "
    "StructureDefinition or a FHIR Bundle of StructureDefinitions."
)


def _env_positive_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def prompt_budget_chars() -> int:
    """Prompt budget for dictionary text, read per call so env changes apply."""
    return _env_positive_int(PROMPT_BUDGET_ENV, DEFAULT_PROMPT_BUDGET_CHARS)


def max_dictionary_bytes() -> int:
    """Upload size limit for dictionary files, read per call."""
    return _env_positive_int(MAX_BYTES_ENV, DEFAULT_MAX_BYTES)


# --------------------------------------------------------------------------- #
# Errors: each carries a 4xx status and an error_class for the uniform shape
# --------------------------------------------------------------------------- #

class DictionaryError(ValueError):
    """A dictionary problem the user can fix; ``str(exc)`` is safe to show."""

    http_status = 400
    error_class = "DictionaryError"


class UnrecognizedDictionaryError(DictionaryError):
    error_class = "UnrecognizedDictionary"

    def __init__(self, reason: str):
        super().__init__(
            f"This file does not look like a data dictionary ({reason}), so nothing "
            f"was loaded. {ACCEPTED_SHAPES}")


def _name_list(names: List[str], limit: int = 300) -> str:
    shown = ", ".join(names[:limit])
    return shown + (f", ... and {len(names) - limit} more" if len(names) > limit else "")


class DictionaryTableRequired(DictionaryError):
    error_class = "DictionaryTableRequired"

    def __init__(self, tables: List[str]):
        self.tables = list(tables)
        super().__init__(
            f"This dictionary defines {len(self.tables)} tables; choose one with the "
            f"\"table\" field. Available: {_name_list(self.tables)}.")


class UnknownDictionaryTable(DictionaryError):
    error_class = "UnknownDictionaryTable"

    def __init__(self, table: str, tables: List[str]):
        self.tables = list(tables)
        close = difflib.get_close_matches(table, self.tables, n=5, cutoff=0.6)
        hint = f" Did you mean: {', '.join(close)}?" if close else ""
        super().__init__(
            f"Table \"{table[:100]}\" is not in this dictionary.{hint} "
            f"Available: {_name_list(self.tables)}.")


class NoDictionaryLoaded(DictionaryError):
    error_class = "NoDictionary"


class DictionaryTooLarge(DictionaryError):
    http_status = 413
    error_class = "DictionaryTooLarge"


# --------------------------------------------------------------------------- #
# A parsed file: one or more tables, each in the standard {"columns": ...} form
# --------------------------------------------------------------------------- #

class DictionaryCatalog:
    """The tables found in one dictionary file.

    Single-table shapes that carry no name use the table name ``""``; a
    ``table`` selector is then ignored, as before.
    """

    def __init__(self, shape: str, tables: Dict[str, Dict[str, Any]], notes: Optional[List[str]] = None):
        self.shape = shape
        self.tables = tables
        self.notes = notes or []

    @property
    def names(self) -> List[str]:
        return list(self.tables)

    @property
    def is_multi_table(self) -> bool:
        return len(self.tables) > 1

    def select(self, table: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
        """Return ``(name, dictionary)`` for one table; raise if the choice is unclear."""
        table = (table or "").strip()
        names = self.names
        if not table:
            if len(names) == 1:
                return names[0], self.tables[names[0]]
            raise DictionaryTableRequired(names)
        if len(names) == 1 and names[0] == "":
            return "", self.tables[""]  # unnamed single table: nothing to choose
        if table in self.tables:
            return table, self.tables[table]
        folded = {name.casefold(): name for name in names}
        if table.casefold() in folded:
            name = folded[table.casefold()]
            return name, self.tables[name]
        raise UnknownDictionaryTable(table, names)


# Keys that mark a dict as a column definition in the {column: definition} shape.
_COLUMN_DEF_KEYS = {
    "type", "dtype", "data_type", "datatype", "description", "label", "constraints",
    "allowed_values", "values", "enum", "choices", "options", "min", "max", "min_value",
    "max_value", "minimum", "maximum", "required", "nullable", "unique", "pattern",
    "format", "default", "example", "examples", "length", "min_length", "max_length",
    "unit", "units", "categories", "distribution",
}

# Words that mark a string as a type name ("integer", "varchar(20)", "free text").
_TYPE_WORDS = (
    "int", "number", "float", "decimal", "double", "real", "numeric", "money",
    "currency", "bool", "bit", "yesno", "truefalse", "logical", "date", "time",
    "year", "month", "str", "text", "char", "clob", "memo", "categor", "enum",
    "choice", "option", "select", "radio", "dropdown", "checkbox", "long", "uuid",
)

_SCALARS = (str, int, float, bool)

# FHIR elements that are infrastructure, not data. Resource-level ones are only
# skipped at the top (Patient.communication.language is real data); extensions
# are skipped at any depth.
_FHIR_SKIP_TOP = {"meta", "implicitRules", "language", "text", "contained"}
_FHIR_SKIP_ANY = {"extension", "modifierExtension"}
_FHIR_TYPE_MAP = {
    "boolean": "boolean", "integer": "integer", "integer64": "integer",
    "positiveint": "integer", "unsignedint": "integer", "decimal": "float",
    "date": "datetime", "datetime": "datetime", "instant": "datetime", "time": "datetime",
}
_CODE_TOKEN = re.compile(r"^[A-Za-z0-9._\-]+$")

# JSON Schema keywords allowed at the top level of a schema document.
_SCHEMA_KEYS = {"$schema", "$id", "id", "title", "description", "type", "properties",
                "required", "additionalProperties", "definitions", "$defs", "$comment",
                "examples", "default", "$ref"}


class DataDictionary:
    """Handles data dictionary parsing, validation, and constraint application."""

    def __init__(self):
        """Initialize the data dictionary handler."""
        self.logger = logger
        self.dictionary = {}
        self.constraints = {}
        # Every table of the last uploaded file, so a table can be picked later
        # without uploading the file again (compact columns only, no raw file).
        self.catalog: Optional[DictionaryCatalog] = None

    def parse_dictionary(self, content: Union[str, bytes, dict], format: str = 'auto',
                         filename: str = '', table: Optional[str] = None) -> Dict[str, Any]:
        """
        Parse data dictionary from various formats.

        Args:
            content: Dictionary content (string, bytes, or dict)
            format: Format type ('json', 'yaml', 'csv', 'excel', 'pdf', 'auto')
            filename: Original filename for format detection
            table: Which table to return when the file defines several

        Returns:
            Parsed dictionary structure for one table: ``{"columns": {...}}``

        Raises:
            UnrecognizedDictionaryError: the content is not a data dictionary.
            DictionaryTableRequired: several tables and no ``table`` given.
            UnknownDictionaryTable: ``table`` names no table in the file.
        """
        return self.load_catalog(content, format, filename).select(table)[1]

    def load_catalog(self, content: Union[str, bytes, dict], format: str = 'auto',
                     filename: str = '') -> DictionaryCatalog:
        """Parse a dictionary file into its tables (see ``parse_dictionary``)."""
        if format == 'auto':
            format = self._detect_format(content, filename)

        self.logger.info(f"Parsing data dictionary in {format} format")

        if format == 'json':
            catalog = self._catalog_from_object(self._load_json(content))
        elif format == 'yaml':
            catalog = self._catalog_from_object(self._load_yaml(content))
        elif format == 'csv':
            catalog = DictionaryCatalog("csv", {"": self._parse_csv(content)})
        elif format in ['excel', 'xls', 'xlsx']:
            catalog = DictionaryCatalog("excel", {"": self._parse_excel(content)})
        elif format == 'pdf':
            catalog = DictionaryCatalog("pdf", {"": self._parse_pdf(content)})
        elif format == 'text':
            catalog = DictionaryCatalog("text", {"": self._parse_text_with_llm(content)})
        else:
            # Try to parse as text with LLM
            catalog = DictionaryCatalog("text", {"": self._parse_text_with_llm(str(content))})

        # A "dictionary" with no columns is not one: never report "0 columns loaded".
        catalog.tables = {name: table for name, table in catalog.tables.items()
                          if isinstance(table.get("columns"), dict) and table["columns"]}
        if not catalog.tables:
            raise UnrecognizedDictionaryError("no column definitions were found in it")
        self.logger.info(f"Dictionary shape {catalog.shape}: {len(catalog.tables)} table(s)")
        return catalog

    def _detect_format(self, content: Union[str, bytes, dict], filename: str = '') -> str:
        """Detect the format of the data dictionary."""
        if isinstance(content, dict):
            return 'json'

        # Check file extension first
        if filename:
            ext = filename.lower().split('.')[-1] if '.' in filename else ''
            if ext in ['json']:
                return 'json'
            elif ext in ['yaml', 'yml']:
                return 'yaml'
            elif ext in ['csv']:
                return 'csv'
            elif ext in ['xls', 'xlsx']:
                return 'excel'
            elif ext in ['pdf']:
                return 'pdf'

        # Convert bytes to string if needed for content detection
        if isinstance(content, bytes):
            # Check for PDF magic bytes
            if content.startswith(b'%PDF'):
                return 'pdf'
            # Check for Excel magic bytes
            if content.startswith(b'PK') or content.startswith(b'\xd0\xcf'):
                return 'excel'

            content = content.decode('utf-8', errors='ignore')

        content_str = str(content).strip()

        # Check for JSON
        if content_str.startswith('{') or content_str.startswith('['):
            try:
                json.loads(content_str)
                return 'json'
            except:
                pass

        # Check for YAML
        if ':' in content_str and (
            content_str.startswith('---') or
            any(line.strip().endswith(':') for line in content_str.split('\n')[:10])
        ):
            return 'yaml'

        # Check for CSV-like structure
        lines = content_str.split('\n')
        if len(lines) > 1 and ',' in lines[0]:
            headers = lines[0].lower()
            if any(keyword in headers for keyword in ['column', 'field', 'type', 'constraint']):
                return 'csv'

        # Default to text for LLM parsing
        return 'text'

    def _load_json(self, content: Union[str, bytes, dict, list]) -> Any:
        """Decode JSON content (or pass a dict/list through)."""
        if isinstance(content, (dict, list)):
            return content
        try:
            return json.loads(content)  # bytes are fine: json detects UTF-8/16/32
        except (ValueError, TypeError) as exc:
            raise UnrecognizedDictionaryError(
                f"it is not valid JSON: {type(exc).__name__}") from None

    def _load_yaml(self, content: Union[str, bytes]) -> Any:
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='replace')
        try:
            return yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise UnrecognizedDictionaryError(
                f"it is not valid YAML: {type(exc).__name__}") from None

    def _parse_json(self, content: Union[str, dict]) -> Dict[str, Any]:
        """Parse JSON format dictionary (single table)."""
        return self._catalog_from_object(self._load_json(content)).select(None)[1]

    def _parse_yaml(self, content: Union[str, bytes]) -> Dict[str, Any]:
        """Parse YAML format dictionary (single table)."""
        return self._catalog_from_object(self._load_yaml(content)).select(None)[1]

    # ------------------------------------------------------------------ #
    # Shape recognition for JSON / YAML content
    # ------------------------------------------------------------------ #

    def _catalog_from_object(self, data: Any) -> DictionaryCatalog:
        """Recognise the shape of decoded JSON/YAML; refuse what is not a dictionary.

        Checked in this order; the first match wins:
        1. ``{"columns": {...}}``                 -> returned unchanged
        2. ``{"resourceType": ...}``              -> FHIR (StructureDefinition or Bundle)
        3. JSON Schema (``properties`` / ``$defs``)
        4. Frictionless Table Schema (``fields``)
        5. ``{column: type-or-definition}``       -> only if most values look like one
        6. ``[{"name": ...}, ...]``
        """
        if isinstance(data, dict):
            if "columns" in data:
                columns = data["columns"]
                if isinstance(columns, dict) and columns:
                    return DictionaryCatalog("columns", {"": data})
                if isinstance(columns, list):
                    named = self._named_items(columns)
                    if named:
                        return DictionaryCatalog("columns", {"": {"columns": named}})
                raise UnrecognizedDictionaryError(
                    "its \"columns\" entry is empty or is not a mapping of column definitions")

            if isinstance(data.get("resourceType"), str):
                return self._fhir_catalog(data)

            if self._looks_like_json_schema(data):
                return self._json_schema_catalog(data)

            fields = data.get("fields")
            if isinstance(fields, list) and fields and all(
                    isinstance(f, dict) and "name" in f for f in fields):
                return DictionaryCatalog("table_schema", {"": {"columns": self._table_schema_columns(fields)}})

            flat = self._flat_mapping(data)
            if flat:
                return DictionaryCatalog("mapping", {"": {"columns": flat}})

            keys = ", ".join(str(k)[:40] for k in list(data)[:8]) or "none"
            raise UnrecognizedDictionaryError(f"its top-level keys are: {keys}")

        if isinstance(data, list):
            named = self._named_items(data)
            if named:
                return DictionaryCatalog("list", {"": {"columns": named}})
            if data and all(isinstance(item, dict) for item in data):
                raise UnrecognizedDictionaryError(
                    "it is a list of records with no \"name\" key; that looks like data "
                    "rows, which belong in the data file upload instead")
            raise UnrecognizedDictionaryError("it is a list with no {\"name\": ...} column definitions")

        raise UnrecognizedDictionaryError(
            f"its top level is a {type(data).__name__}, not a mapping or a list")

    @staticmethod
    def _named_items(items: list) -> Dict[str, Any]:
        """``[{"name": "age", ...}, ...]`` -> ``{"age": {...}}`` (the original list shape)."""
        columns = {}
        for item in items:
            if isinstance(item, dict) and 'name' in item:
                item = dict(item)
                col_name = item.pop('name')
                columns[col_name] = item
        return columns

    @staticmethod
    def _is_type_word(value: str) -> bool:
        lowered = value.lower()
        return len(value) <= 80 and any(word in lowered for word in _TYPE_WORDS)

    def _flat_mapping(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """The original ``{column: definition}`` shape, if this mapping looks like one.

        A value counts as a column definition when it is a dict with a known
        definition key (type, description, constraints, ...), a type-name string
        ("integer", "free text"), or a list of plain values (allowed values).
        At least half the values must count, and no value may be a list of
        objects (that is data or a wrapper, never a column definition).
        """
        if not data:
            return None
        looks_right = 0
        for value in data.values():
            if isinstance(value, dict):
                if _COLUMN_DEF_KEYS & {str(k).lower() for k in value}:
                    looks_right += 1
            elif isinstance(value, str):
                if self._is_type_word(value):
                    looks_right += 1
            elif isinstance(value, list):
                if not value or not all(isinstance(v, _SCALARS) for v in value):
                    return None
                looks_right += 1
        if looks_right * 2 < len(data):
            return None

        columns = {}
        for key, value in data.items():
            if isinstance(value, dict):
                columns[key] = value
            elif isinstance(value, list):
                columns[key] = {"type": "categorical", "constraints": {"allowed_values": value}}
            else:
                # Simple type mapping
                columns[key] = {"type": str(value)}
        return columns

    # -- JSON Schema ------------------------------------------------------ #

    @staticmethod
    def _looks_like_json_schema(data: Dict[str, Any]) -> bool:
        schema_doc = "$schema" in data or set(data) <= _SCHEMA_KEYS
        props = data.get("properties")
        if isinstance(props, dict) and props and all(isinstance(v, dict) for v in props.values()):
            if schema_doc or data.get("type") == "object":
                return True
        defs = data.get("$defs") if isinstance(data.get("$defs"), dict) else data.get("definitions")
        if isinstance(defs, dict) and schema_doc:
            return any(isinstance(v, dict) and isinstance(v.get("properties"), dict)
                       for v in defs.values())
        return False

    def _json_schema_catalog(self, data: Dict[str, Any]) -> DictionaryCatalog:
        if isinstance(data.get("properties"), dict) and data["properties"]:
            name = str(data.get("title") or "")
            return DictionaryCatalog("json_schema", {name: {"columns": self._json_schema_columns(data)}})
        defs = data.get("$defs") if isinstance(data.get("$defs"), dict) else data.get("definitions")
        tables = {str(name): {"columns": self._json_schema_columns(schema)}
                  for name, schema in defs.items()
                  if isinstance(schema, dict) and isinstance(schema.get("properties"), dict)}
        return DictionaryCatalog("json_schema", tables)

    @staticmethod
    def _json_schema_columns(schema: Dict[str, Any]) -> Dict[str, Any]:
        required = set(schema.get("required") or []) if isinstance(schema.get("required"), list) else set()
        columns = {}
        for name, prop in schema["properties"].items():
            if not isinstance(prop, dict):
                continue
            kind = prop.get("type")
            if isinstance(kind, list):
                kind = next((k for k in kind if k != "null"), None)
            fmt = prop.get("format")
            if kind == "integer":
                col_type = "integer"
            elif kind == "number":
                col_type = "float"
            elif kind == "boolean":
                col_type = "boolean"
            elif fmt in ("date", "date-time", "time"):
                col_type = "datetime"
            else:
                col_type = "string"
            enum = prop.get("enum")
            if isinstance(enum, list) and enum:
                col_type = "categorical"

            col: Dict[str, Any] = {"type": col_type}
            text = prop.get("description") or prop.get("title")
            if kind in ("array", "object"):
                text = f"{text} (JSON {kind})" if text else f"JSON {kind}"
            if text:
                col["description"] = str(text)
            constraints: Dict[str, Any] = {}
            if name in required:
                constraints["required"] = True
            for src, dst in (("minimum", "min_value"), ("exclusiveMinimum", "min_value"),
                             ("maximum", "max_value"), ("exclusiveMaximum", "max_value"),
                             ("minLength", "min_length"), ("maxLength", "max_length"),
                             ("pattern", "pattern")):
                if isinstance(prop.get(src), (int, float, str)) and not isinstance(prop.get(src), bool):
                    constraints.setdefault(dst, prop[src])
            if isinstance(enum, list) and enum:
                constraints["allowed_values"] = enum
            if col_type == "datetime" and fmt:
                constraints["format"] = fmt
            if constraints:
                col["constraints"] = constraints
            columns[str(name)] = col
        return columns

    # -- Frictionless Table Schema ----------------------------------------- #

    @staticmethod
    def _table_schema_columns(fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        type_map = {"integer": "integer", "number": "float", "boolean": "boolean",
                    "date": "datetime", "datetime": "datetime", "time": "datetime",
                    "year": "datetime", "yearmonth": "datetime"}
        columns = {}
        for field in fields:
            raw = field.get("constraints") if isinstance(field.get("constraints"), dict) else {}
            col: Dict[str, Any] = {"type": type_map.get(str(field.get("type", "")).lower(), "string")}
            text = field.get("description") or field.get("title")
            if text:
                col["description"] = str(text)
            constraints: Dict[str, Any] = {}
            for src, dst in (("required", "required"), ("unique", "unique"),
                             ("minimum", "min_value"), ("maximum", "max_value"),
                             ("minLength", "min_length"), ("maxLength", "max_length"),
                             ("pattern", "pattern"), ("enum", "allowed_values")):
                if src in raw:
                    constraints[dst] = raw[src]
            if constraints.get("allowed_values"):
                col["type"] = "categorical"
            if constraints:
                col["constraints"] = constraints
            columns[str(field["name"])] = col
        return columns

    # -- HL7 FHIR ------------------------------------------------------------ #

    def _fhir_catalog(self, data: Dict[str, Any]) -> DictionaryCatalog:
        resource_type = data["resourceType"]
        if resource_type == "StructureDefinition":
            name, columns, partial = self._fhir_table(data)
            if not columns:
                raise UnrecognizedDictionaryError(
                    "it is a FHIR StructureDefinition with no data elements")
            notes = [f"{name}: no snapshot, differential elements only"] if partial else []
            return DictionaryCatalog("fhir_structure_definition", {name: {"columns": columns}}, notes)

        if resource_type == "Bundle":
            tables, notes = {}, []
            for entry in data.get("entry") or []:
                resource = entry.get("resource") if isinstance(entry, dict) else None
                if not (isinstance(resource, dict)
                        and resource.get("resourceType") == "StructureDefinition"):
                    continue  # OperationDefinition, CapabilityStatement, records, ...
                name, columns, partial = self._fhir_table(resource)
                if columns and name not in tables:
                    tables[name] = {"columns": columns}
                    if partial:
                        notes.append(f"{name}: no snapshot, differential elements only")
            if not tables:
                raise UnrecognizedDictionaryError(
                    "it is a FHIR Bundle with no StructureDefinitions in it; a Bundle of "
                    "patient or other records is data, not a dictionary")
            return DictionaryCatalog("fhir_bundle", tables, notes)

        raise UnrecognizedDictionaryError(
            f"it is a FHIR {str(resource_type)[:40]} resource, which is a record, not a "
            f"StructureDefinition")

    @staticmethod
    def _fhir_table(sd: Dict[str, Any]) -> Tuple[str, Dict[str, Any], bool]:
        """One StructureDefinition -> (table name, columns, used differential only).

        Rules: the root element and infrastructure elements (meta, text,
        extension, ...) are skipped; a BackboneElement is not a column itself,
        its children are, named with their parent path (``contact.name``);
        ``[x]`` choice elements become one column without the suffix, typed by
        their first type, all types listed in the description; elements with
        ``max = 0``, slices and ``contentReference`` repeats are skipped.
        """
        name = str(sd.get("name") or sd.get("id") or sd.get("type") or "StructureDefinition")
        elements = ((sd.get("snapshot") or {}).get("element")) or []
        partial = False
        if not elements:
            elements = ((sd.get("differential") or {}).get("element")) or []
            partial = bool(elements)

        columns: Dict[str, Any] = {}
        excluded: List[str] = []  # element paths whose children are skipped too
        for el in elements:
            if not isinstance(el, dict):
                continue
            path = str(el.get("path") or el.get("id") or "")
            if "." not in path:
                continue  # the resource itself
            rel = path.split(".", 1)[1]
            parts = rel.split(".")
            if any(rel.startswith(prefix + ".") for prefix in excluded):
                continue
            if el.get("sliceName") or ":" in str(el.get("id") or ""):
                continue  # slices repeat an element already seen
            types = [str(t.get("code")) for t in el.get("type") or []
                     if isinstance(t, dict) and t.get("code")]
            if (str(el.get("max")) == "0" or (len(parts) == 1 and parts[0] in _FHIR_SKIP_TOP)
                    or any(p in _FHIR_SKIP_ANY for p in parts)
                    or el.get("contentReference") or not types):
                excluded.append(rel)
                continue
            if len(parts) > 1 and parts[-1] == "id":
                continue  # internal id of a backbone element
            if any(t in ("BackboneElement", "Element") for t in types):
                continue  # container: its children become the columns

            col_name = rel.replace("[x]", "")
            if col_name in columns:
                continue
            short_types = [t.rsplit("System.", 1)[-1] if t.startswith("http") else t for t in types]
            first = short_types[0].lower()
            col_type = _FHIR_TYPE_MAP.get(first, "string")

            constraints: Dict[str, Any] = {}
            mn, mx = el.get("min", 0), str(el.get("max", "1"))
            if isinstance(mn, int) and mn >= 1:
                constraints["required"] = True

            short = str(el.get("short") or "").strip()
            binding = el.get("binding") if isinstance(el.get("binding"), dict) else {}
            value_set = str(binding.get("valueSet") or "")
            if first == "code" and binding.get("strength") == "required" and " | " in short:
                # "registered | final | amended +" : a trailing "+" means "and more"
                codes = [c.strip().rstrip("+").strip() for c in short.split("|")]
                codes = [c for c in codes if c]
                if codes and all(_CODE_TOKEN.match(c) for c in codes):
                    constraints["allowed_values"] = codes
                    col_type = "categorical"

            details = [f"FHIR {' | '.join(short_types)}", f"{mn}..{mx}"]
            if value_set:
                vs_name = value_set.split("|", 1)[0].rstrip("/").rsplit("/", 1)[-1]
                details.append(f"value set {vs_name} ({binding.get('strength', 'unspecified')})")
            col: Dict[str, Any] = {"type": col_type,
                                   "description": f"{short} [{'; '.join(details)}]".strip()}
            if constraints:
                col["constraints"] = constraints
            columns[col_name] = col
        return name, columns, partial

    def _parse_excel_dictionary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Generic parser for Excel data dictionaries."""
        dictionary = {"columns": {}}

        # Map common column patterns to their semantic meaning
        column_patterns = {
            'name': ['variable', 'field', 'column', 'name', 'attribute', 'parameter', 'element'],
            'type': ['type', 'datatype', 'data_type', 'dtype', 'format', 'class'],
            'description': ['description', 'label', 'definition', 'comment', 'notes', 'meaning', 'prompt', 'question'],
            'choices': ['choices', 'values', 'options', 'allowed', 'valid', 'enum', 'list', 'responses', 'response'],
            'min': ['min', 'minimum', 'lower', 'low', 'floor'],
            'max': ['max', 'maximum', 'upper', 'high', 'ceiling'],
            'required': ['required', 'mandatory', 'nullable', 'optional'],
            'validation': ['validation', 'constraint', 'rule', 'check', 'format'],
            'length': ['length', 'size', 'width', 'max_length', 'maxlength'],
            'default': ['default', 'initial', 'preset'],
            'unique': ['unique', 'distinct', 'key', 'identifier'],
            'pattern': ['pattern', 'regex', 'regexp', 'expression', 'mask']
        }

        # Identify which columns map to what semantic meaning
        column_mapping = {}
        for col in df.columns:
            col_lower = col.lower().strip()
            for semantic_key, patterns in column_patterns.items():
                if any(pattern in col_lower for pattern in patterns):
                    # Prioritize more specific matches
                    if semantic_key not in column_mapping or len(col_lower) < len(column_mapping[semantic_key].lower()):
                        column_mapping[semantic_key] = col
                    break

        self.logger.info(f"Column mapping detected for fields: {sorted(column_mapping)}")

        # If no name column found, try to use the first column
        if 'name' not in column_mapping and len(df.columns) > 0:
            column_mapping['name'] = df.columns[0]
            self.logger.info("Using first column as field name")

        # Parse each row as a field definition
        for _, row in df.iterrows():
            # Get field name
            field_name = None
            if 'name' in column_mapping:
                field_name_val = row.get(column_mapping['name'])
                if pd.notna(field_name_val):
                    field_name = str(field_name_val).strip()

            if not field_name:
                continue

            col_def = {}

            # Get type
            if 'type' in column_mapping:
                type_val = row.get(column_mapping['type'])
                if pd.notna(type_val):
                    col_def['type'] = self._normalize_type(str(type_val))

            # Get description
            if 'description' in column_mapping:
                desc_val = row.get(column_mapping['description'])
                if pd.notna(desc_val):
                    col_def['description'] = str(desc_val).strip()

            # Get allowed values/choices
            if 'choices' in column_mapping:
                choices_val = row.get(column_mapping['choices'])
                if pd.notna(choices_val):
                    parsed_choices = self._parse_choices(str(choices_val))
                    if parsed_choices:
                        col_def['allowed_values'] = parsed_choices
                        # If we have allowed values, it's likely categorical
                        if not col_def.get('type') or col_def.get('type') == 'string':
                            # Check if values are numeric codes
                            if all(c[0].isdigit() or c.startswith('-') for c in str(choices_val).split(';') if c.strip()):
                                col_def['type'] = 'categorical_numeric'
                            else:
                                col_def['type'] = 'categorical'

            # Get validation/constraints
            constraints = {}

            # Min value
            if 'min' in column_mapping:
                min_val = row.get(column_mapping['min'])
                if pd.notna(min_val):
                    try:
                        constraints['min_value'] = float(min_val)
                    except:
                        pass

            # Max value
            if 'max' in column_mapping:
                max_val = row.get(column_mapping['max'])
                if pd.notna(max_val):
                    try:
                        constraints['max_value'] = float(max_val)
                    except:
                        pass

            # Required field
            if 'required' in column_mapping:
                req_val = row.get(column_mapping['required'])
                if pd.notna(req_val):
                    req_str = str(req_val).lower().strip()
                    if req_str in ['y', 'yes', 'true', '1', 'required', 'mandatory']:
                        constraints['required'] = True
                    elif req_str in ['n', 'no', 'false', '0', 'optional']:
                        constraints['required'] = False

            # Length constraint
            if 'length' in column_mapping:
                length_val = row.get(column_mapping['length'])
                if pd.notna(length_val):
                    try:
                        constraints['max_length'] = int(length_val)
                    except:
                        pass

            # Pattern
            if 'pattern' in column_mapping:
                pattern_val = row.get(column_mapping['pattern'])
                if pd.notna(pattern_val):
                    constraints['pattern'] = str(pattern_val).strip()

            # Validation rules
            if 'validation' in column_mapping:
                val_val = row.get(column_mapping['validation'])
                if pd.notna(val_val):
                    validation = str(val_val).lower().strip()
                    # Try to infer type from validation
                    if not col_def.get('type'):
                        if 'int' in validation:
                            col_def['type'] = 'integer'
                        elif 'float' in validation or 'decimal' in validation or 'number' in validation:
                            col_def['type'] = 'float'
                        elif 'date' in validation:
                            col_def['type'] = 'datetime'
                        elif 'email' in validation:
                            constraints['pattern'] = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                        elif 'phone' in validation:
                            constraints['pattern'] = r'^[\d\s\-\(\)\+]+$'
                        elif 'url' in validation or 'website' in validation:
                            constraints['pattern'] = r'^https?://'

            # Unique constraint
            if 'unique' in column_mapping:
                unique_val = row.get(column_mapping['unique'])
                if pd.notna(unique_val):
                    unique_str = str(unique_val).lower().strip()
                    if unique_str in ['y', 'yes', 'true', '1', 'unique']:
                        constraints['unique'] = True

            # Default value
            if 'default' in column_mapping:
                default_val = row.get(column_mapping['default'])
                if pd.notna(default_val):
                    col_def['default'] = str(default_val)

            # Add constraints if any were found
            if constraints:
                col_def['constraints'] = constraints

            # If no type was determined, default to string
            if 'type' not in col_def:
                col_def['type'] = 'string'

            dictionary["columns"][field_name] = col_def

        return dictionary

    def _normalize_type(self, type_str: str) -> str:
        """Normalize various type representations to standard types."""
        type_lower = type_str.lower().strip()

        # Integer types
        if any(t in type_lower for t in ['int', 'integer', 'bigint', 'smallint', 'tinyint', 'long', 'number']):
            if 'float' not in type_lower and 'decimal' not in type_lower and 'double' not in type_lower:
                return 'integer'

        # Float/decimal types
        if any(t in type_lower for t in ['float', 'decimal', 'double', 'real', 'numeric', 'money', 'currency']):
            return 'float'

        # Boolean types
        if any(t in type_lower for t in ['bool', 'boolean', 'bit', 'yesno', 'truefalse', 'logical']):
            return 'boolean'

        # Date/time types
        if any(t in type_lower for t in ['date', 'time', 'timestamp', 'datetime', 'year', 'month']):
            return 'datetime'

        # String types
        if any(t in type_lower for t in ['str', 'string', 'text', 'char', 'varchar', 'nvarchar', 'clob', 'memo']):
            return 'string'

        # Categorical
        if any(t in type_lower for t in ['category', 'categorical', 'enum', 'choice', 'option', 'select', 'radio', 'dropdown', 'checkbox']):
            return 'categorical'

        # Default to string for unknown types
        return 'string'

    def _parse_choices(self, choices_str: str) -> list:
        """Parse various formats of choices/allowed values."""
        choices_str = choices_str.strip()

        # Special case: if it's just "text", return None (not a categorical field)
        if choices_str.lower() == 'text':
            return None

        choices = []

        # First check for semicolon-separated format (e.g., "0, Description;1, Another;...")
        if ';' in choices_str:
            parts = choices_str.split(';')
            for part in parts:
                part = part.strip()
                if not part:
                    continue

                # Check if it's "code, description" format
                if ',' in part:
                    # Split only on first comma to preserve descriptions with commas
                    subparts = part.split(',', 1)
                    if len(subparts) == 2:
                        code = subparts[0].strip()
                        desc = subparts[1].strip()
                        # Store both code and description as a tuple or just description
                        # For now, storing the full "code: description" for clarity
                        choices.append(f"{code}: {desc}")
                    else:
                        choices.append(part)
                else:
                    choices.append(part)

        # Try pipe-separated format
        elif '|' in choices_str:
            parts = choices_str.split('|')
            for part in parts:
                part = part.strip()
                if not part:
                    continue

                # Handle "key: value" format
                if ':' in part:
                    choices.append(part)
                elif ',' in part:
                    # Might be "1, Option 1" format
                    subparts = part.split(',', 1)
                    if len(subparts) > 1:
                        choices.append(f"{subparts[0].strip()}: {subparts[1].strip()}")
                    else:
                        choices.append(part)
                else:
                    choices.append(part)

        # Try comma-separated only if no semicolons or pipes
        elif ',' in choices_str and '\n' not in choices_str:
            # This might be a simple comma-separated list
            parts = choices_str.split(',')
            # Only treat as comma-separated if we have multiple items
            if len(parts) > 2:
                choices = [p.strip() for p in parts if p.strip()]
            else:
                # Might be a single "code, description" pair
                choices = [choices_str.strip()]

        # Try newline-separated
        elif '\n' in choices_str:
            lines = choices_str.split('\n')
            for line in lines:
                line = line.strip()
                if line:
                    choices.append(line)

        # If no separator found, treat as single choice (unless it's empty)
        elif choices_str and choices_str.lower() not in ['na', 'n/a', 'none']:
            choices = [choices_str]

        return choices if choices else None


    def _parse_csv(self, content: Union[str, bytes]) -> Dict[str, Any]:
        """Parse CSV format dictionary."""
        if isinstance(content, bytes):
            content = content.decode('utf-8')

        import io
        df = pd.read_csv(io.StringIO(content))

        dictionary = {"columns": {}}

        # Common column name mappings
        col_mappings = {
            'column': 'name',
            'field': 'name',
            'column_name': 'name',
            'field_name': 'name',
            'data_type': 'type',
            'datatype': 'type',
            'constraint': 'constraints',
            'validation': 'constraints',
            'description': 'description',
            'values': 'allowed_values',
            'allowed_values': 'allowed_values',
            'min': 'min_value',
            'max': 'max_value',
            'required': 'required',
            'nullable': 'nullable'
        }

        # Normalize column names
        df.columns = [col.lower().strip() for col in df.columns]

        for _, row in df.iterrows():
            col_name = None
            col_def = {}

            for csv_col, dict_key in col_mappings.items():
                if csv_col in df.columns and pd.notna(row[csv_col]):
                    if dict_key == 'name':
                        col_name = str(row[csv_col])
                    else:
                        col_def[dict_key] = row[csv_col]

            if col_name:
                dictionary["columns"][col_name] = col_def

        return dictionary

    def _parse_excel(self, content: bytes) -> Dict[str, Any]:
        """Parse Excel format dictionary with multi-sheet support."""
        import io

        # Read all sheets
        excel_file = pd.ExcelFile(io.BytesIO(content))
        sheet_names = excel_file.sheet_names

        self.logger.info(f"Excel file contains {len(sheet_names)} sheets")

        # Try to find the data dictionary sheet
        dict_sheet = None
        dict_df = None

        # Common data dictionary sheet names (case-insensitive)
        common_dict_names = ['dictionary', 'data dictionary', 'data_dictionary', 'dict',
                            'metadata', 'schema', 'codebook', 'variables', 'fields',
                            'field_definitions', 'column_definitions', 'columns',
                            'data_model', 'datamodel', 'spec', 'specification']

        # First, try to find by sheet name
        for sheet_name in sheet_names:
            sheet_lower = sheet_name.lower().strip()
            if any(dict_name in sheet_lower for dict_name in common_dict_names):
                dict_sheet = sheet_name
                self.logger.info("Found dictionary sheet by name")
                break

        # If no obvious dictionary sheet, check each sheet's content
        if dict_sheet is None:
            for sheet_name in sheet_names:
                df = pd.read_excel(excel_file, sheet_name=sheet_name)

                if df.empty or len(df) == 0:
                    continue

                # Check if this looks like a data dictionary
                # Look for common dictionary column headers
                common_headers = ['field', 'variable', 'column', 'field_name', 'variable_name',
                                'type', 'data_type', 'datatype', 'field_type',
                                'description', 'label', 'field_label',
                                'choices', 'values', 'allowed_values', 'validation']

                df_columns_lower = [col.lower().strip() for col in df.columns]
                matches = sum(1 for header in common_headers if any(header in col for col in df_columns_lower))

                # If we have at least 2 matching headers, likely a dictionary
                if matches >= 2:
                    dict_sheet = sheet_name
                    dict_df = df
                    self.logger.info("Found dictionary sheet by content analysis")
                    break

        # If still no dictionary found, use the first non-empty sheet
        if dict_sheet is None:
            for sheet_name in sheet_names:
                df = pd.read_excel(excel_file, sheet_name=sheet_name)
                if not df.empty and len(df) > 0:
                    dict_sheet = sheet_name
                    dict_df = df
                    self.logger.warning("No clear dictionary sheet found, using first non-empty sheet")
                    break

        # Load the identified sheet if not already loaded
        if dict_df is None and dict_sheet:
            dict_df = pd.read_excel(excel_file, sheet_name=dict_sheet)

        if dict_df is None or dict_df.empty:
            raise ValueError("Could not find valid data dictionary in Excel file")

        # Use generic Excel dictionary parser
        return self._parse_excel_dictionary(dict_df)

    def _parse_pdf(self, content: bytes) -> Dict[str, Any]:
        """Parse PDF format dictionary using text extraction."""
        try:
            import PyPDF2
            import io

            pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text()

            # Parse extracted text
            return self._parse_text_with_llm(text)
        except ImportError:
            # If PyPDF2 not available, try basic text extraction
            self.logger.warning("PyPDF2 not available, using basic text extraction")
            text = content.decode('utf-8', errors='ignore')
            return self._parse_text_with_llm(text)
        except Exception as e:
            self.logger.error(f"Error parsing PDF: {e}")
            # Fallback to text parsing
            return self._parse_text_with_llm(str(content))

    def _parse_text_with_llm(self, content: str) -> Dict[str, Any]:
        """
        Parse unstructured text using LLM to extract data dictionary.
        This is a fallback for non-standard formats.
        """
        # For now, use pattern matching as fallback
        # In production, this would call the LLM to interpret the text

        dictionary = {"columns": {}}

        # Try to extract column definitions using patterns
        lines = content.split('\n')
        current_column = None

        for line in lines:
            line = line.strip()

            # Look for column definitions
            if re.match(r'^[A-Za-z_][A-Za-z0-9_]*\s*[:=]', line):
                parts = re.split(r'[:=]', line, 1)
                if len(parts) == 2:
                    col_name = parts[0].strip()
                    col_info = parts[1].strip()

                    dictionary["columns"][col_name] = {
                        "description": col_info,
                        "type": self._infer_type_from_description(col_info)
                    }
                    current_column = col_name

            # Look for constraints on current column
            elif current_column and any(keyword in line.lower() for keyword in ['min', 'max', 'values', 'required']):
                if 'min' in line.lower():
                    match = re.search(r'min[:\s]+(\d+)', line, re.IGNORECASE)
                    if match:
                        dictionary["columns"][current_column]["min_value"] = int(match.group(1))

                if 'max' in line.lower():
                    match = re.search(r'max[:\s]+(\d+)', line, re.IGNORECASE)
                    if match:
                        dictionary["columns"][current_column]["max_value"] = int(match.group(1))

        return dictionary

    def _infer_type_from_description(self, description: str) -> str:
        """Infer data type from description text."""
        desc_lower = description.lower()

        if any(word in desc_lower for word in ['date', 'time', 'timestamp']):
            return 'datetime'
        elif any(word in desc_lower for word in ['int', 'number', 'count', 'age', 'quantity']):
            return 'integer'
        elif any(word in desc_lower for word in ['float', 'decimal', 'amount', 'price', 'rate']):
            return 'float'
        elif any(word in desc_lower for word in ['bool', 'flag', 'yes/no', 'true/false']):
            return 'boolean'
        else:
            return 'string'

    def _standardize_dictionary(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Standardize dictionary to common format.

        Expected format:
        {
            "columns": {
                "column_name": {
                    "type": "string|integer|float|datetime|boolean",
                    "description": "Column description",
                    "constraints": {
                        "required": true|false,
                        "unique": true|false,
                        "min_value": number,
                        "max_value": number,
                        "min_length": number,
                        "max_length": number,
                        "pattern": "regex pattern",
                        "allowed_values": ["value1", "value2"],
                        "format": "date format or other format spec"
                    }
                }
            }
        }
        """
        return self._catalog_from_object(data).select(None)[1]

    def validate_data(self, df: pd.DataFrame, dictionary: Optional[Dict[str, Any]] = None) -> Dict[str, List[str]]:
        """
        Validate DataFrame against data dictionary.

        Args:
            df: DataFrame to validate
            dictionary: Data dictionary (uses stored if not provided)

        Returns:
            Dictionary of column names to list of validation errors
        """
        if dictionary is None:
            dictionary = self.dictionary

        errors = {}

        for col_name, col_def in dictionary.get("columns", {}).items():
            if col_name not in df.columns:
                if col_def.get("constraints", {}).get("required", False):
                    errors[col_name] = [f"Required column '{col_name}' is missing"]
                continue

            col_errors = self._validate_column(df[col_name], col_def)
            if col_errors:
                errors[col_name] = col_errors

        return errors

    def _validate_column(self, series: pd.Series, definition: Dict[str, Any]) -> List[str]:
        """Validate a single column against its definition."""
        errors = []
        constraints = definition.get("constraints", {})

        # Check data type
        expected_type = definition.get("type", "string").lower()
        if not self._check_type_compatibility(series, expected_type):
            errors.append(f"Type mismatch: expected {expected_type}")

        # Check constraints
        if constraints.get("required") and series.isna().any():
            errors.append("Contains null values but marked as required")

        if constraints.get("unique") and series.duplicated().any():
            errors.append("Contains duplicate values but marked as unique")

        # Numeric constraints
        if expected_type in ['integer', 'float', 'numeric']:
            if 'min_value' in constraints:
                if (series.dropna() < constraints['min_value']).any():
                    errors.append(f"Values below minimum {constraints['min_value']}")

            if 'max_value' in constraints:
                if (series.dropna() > constraints['max_value']).any():
                    errors.append(f"Values above maximum {constraints['max_value']}")

        # String constraints
        if expected_type == 'string':
            if 'min_length' in constraints:
                if (series.dropna().str.len() < constraints['min_length']).any():
                    errors.append(f"Strings shorter than minimum length {constraints['min_length']}")

            if 'max_length' in constraints:
                if (series.dropna().str.len() > constraints['max_length']).any():
                    errors.append(f"Strings longer than maximum length {constraints['max_length']}")

            if 'pattern' in constraints:
                pattern = constraints['pattern']
                if not series.dropna().str.match(pattern).all():
                    errors.append(f"Values don't match pattern: {pattern}")

        # Allowed values
        if 'allowed_values' in constraints:
            allowed = set(constraints['allowed_values'])
            actual = set(series.dropna().unique())
            if not actual.issubset(allowed):
                invalid = actual - allowed
                errors.append(f"Invalid values found: {list(invalid)[:5]}")

        return errors

    def _check_type_compatibility(self, series: pd.Series, expected_type: str) -> bool:
        """Check if series type is compatible with expected type."""
        if expected_type in ['integer', 'int']:
            return pd.api.types.is_integer_dtype(series) or series.dropna().apply(lambda x: isinstance(x, int)).all()
        elif expected_type in ['float', 'numeric', 'decimal']:
            return pd.api.types.is_numeric_dtype(series)
        elif expected_type in ['string', 'text', 'varchar']:
            return pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series)
        elif expected_type in ['datetime', 'date', 'timestamp']:
            return pd.api.types.is_datetime64_any_dtype(series)
        elif expected_type in ['boolean', 'bool']:
            return pd.api.types.is_bool_dtype(series)
        else:
            return True  # Unknown type, assume compatible

    def apply_to_metadata(self, metadata: Dict[str, Any], dictionary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Apply data dictionary constraints to metadata for generation.

        Args:
            metadata: Metadata from MetadataExtractor
            dictionary: Data dictionary (uses stored if not provided)

        Returns:
            Enhanced metadata with dictionary constraints
        """
        if dictionary is None:
            dictionary = self.dictionary

        enhanced_metadata = metadata.copy()

        for col_name, col_def in dictionary.get("columns", {}).items():
            # Add or update column in metadata
            if col_name not in enhanced_metadata.get("statistics", {}):
                enhanced_metadata["statistics"][col_name] = {}

            col_stats = enhanced_metadata["statistics"][col_name]

            # Apply type
            col_stats["type"] = col_def.get("type", "string")

            # Apply constraints
            constraints = col_def.get("constraints", {})

            if "allowed_values" in constraints:
                col_stats["allowed_values"] = constraints["allowed_values"]
                col_stats["is_categorical"] = True

            if "min_value" in constraints:
                col_stats["min"] = constraints["min_value"]

            if "max_value" in constraints:
                col_stats["max"] = constraints["max_value"]

            if "pattern" in constraints:
                col_stats["pattern"] = constraints["pattern"]

            if "format" in constraints:
                col_stats["format"] = constraints["format"]

            # Add description for better generation
            if "description" in col_def:
                col_stats["description"] = col_def["description"]

            # Mark as dictionary-defined
            col_stats["from_dictionary"] = True

        return enhanced_metadata

    def to_generation_constraints(self, dictionary: Optional[Dict[str, Any]] = None) -> str:
        """
        Convert dictionary to generation constraints text for LLM.

        Args:
            dictionary: Data dictionary (uses stored if not provided)

        Returns:
            Text description of constraints for LLM prompt
        """
        if dictionary is None:
            dictionary = self.dictionary

        constraints_text = []

        for col_name, col_def in dictionary.get("columns", {}).items():
            constraint_parts = [f"{col_name}: {col_def.get('type', 'string')} type"]

            if "description" in col_def:
                constraint_parts.append(f"({col_def['description']})")

            constraints = col_def.get("constraints", {})

            if "allowed_values" in constraints:
                values = constraints["allowed_values"][:10]  # Limit to first 10
                constraint_parts.append(f"must be one of: {values}")

            if "min_value" in constraints:
                constraint_parts.append(f"min={constraints['min_value']}")

            if "max_value" in constraints:
                constraint_parts.append(f"max={constraints['max_value']}")

            if "pattern" in constraints:
                constraint_parts.append(f"pattern={constraints['pattern']}")

            if constraints.get("required"):
                constraint_parts.append("REQUIRED")

            if constraints.get("unique"):
                constraint_parts.append("UNIQUE")

            constraints_text.append(" - ".join(constraint_parts))

        return "\n".join(constraints_text)

    # ------------------------------------------------------------------ #
    # Prompt budget
    # ------------------------------------------------------------------ #

    def dictionary_prompt_chars(self, dictionary: Dict[str, Any]) -> int:
        """Characters this dictionary adds to the LLM prompt.

        The prompt carries it twice: as per-column statistics (JSON, indent 2,
        built by ``apply_to_metadata``) and as constraint lines
        (``to_generation_constraints``). Both are counted.
        """
        stats = self.apply_to_metadata({"statistics": {}}, dictionary)["statistics"]
        return (len(self.to_generation_constraints(dictionary))
                + len(json.dumps(stats, indent=2, default=str)))

    def fit_to_prompt_budget(self, dictionary: Dict[str, Any],
                             max_chars: Optional[int] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Return ``(dictionary_for_prompt, trimming_info)`` within the prompt budget.

        The input is never modified. When it is over budget a copy is trimmed,
        cheapest loss first, stopping as soon as it fits:

        1. allowed-value lists cut to 20 values;
        2. descriptions cut to 160 characters, then 60, then removed;
        3. allowed-value lists cut to 5 values;
        4. whole columns dropped: optional columns before required ones, from
           the end of the dictionary backwards.

        Raises ``DictionaryTooLarge`` if not even one column fits.
        """
        budget = max_chars or prompt_budget_chars()
        columns = dictionary.get("columns") or {}
        total = len(columns)
        before = self.dictionary_prompt_chars(dictionary)
        info: Dict[str, Any] = {
            "trimmed": False, "budget_chars": budget,
            "prompt_chars_before": before, "prompt_chars_after": before,
            "columns_total": total, "columns_kept": total, "columns_dropped": 0,
            "dropped_columns": [], "steps": [], "message": "",
        }
        if before <= budget:
            return dictionary, info

        work = copy.deepcopy(dictionary)
        cols = work["columns"]
        steps: List[str] = []

        def cap_values(limit: int) -> bool:
            changed = False
            for col in cols.values():
                if not isinstance(col, dict):
                    continue
                for holder in (col, col.get("constraints")):
                    if isinstance(holder, dict) and isinstance(holder.get("allowed_values"), list) \
                            and len(holder["allowed_values"]) > limit:
                        holder["allowed_values"] = holder["allowed_values"][:limit]
                        changed = True
            return changed

        def cut_descriptions(limit: int) -> bool:
            changed = False
            for col in cols.values():
                if isinstance(col, dict) and "description" in col:
                    text = str(col["description"])
                    if limit == 0:
                        del col["description"]
                        changed = True
                    elif len(text) > limit:
                        col["description"] = text[:limit - 3].rstrip() + "..."
                        changed = True
            return changed

        size = before
        for label, step in (
            ("allowed-value lists cut to 20 values", lambda: cap_values(20)),
            ("descriptions cut to 160 characters", lambda: cut_descriptions(160)),
            ("descriptions cut to 60 characters", lambda: cut_descriptions(60)),
            ("descriptions removed", lambda: cut_descriptions(0)),
            ("allowed-value lists cut to 5 values", lambda: cap_values(5)),
        ):
            if step():
                steps.append(label)
                size = self.dictionary_prompt_chars(work)
                if size <= budget:
                    break

        dropped: List[str] = []
        if size > budget:
            # Keep required columns first, then optional, each in file order.
            def is_required(col: Any) -> bool:
                return isinstance(col, dict) and bool((col.get("constraints") or {}).get("required"))

            order = ([n for n, c in cols.items() if is_required(c)]
                     + [n for n, c in cols.items() if not is_required(c)])
            cost = {n: self.dictionary_prompt_chars({"columns": {n: cols[n]}}) for n in order}
            keep, used = [], 0
            for name in order:
                if used + cost[name] > budget:
                    break
                keep.append(name)
                used += cost[name]
            while True:
                kept = set(keep)
                work["columns"] = {n: c for n, c in cols.items() if n in kept}
                size = self.dictionary_prompt_chars(work)
                if size <= budget or not keep:
                    break
                keep.pop()
            if not keep:
                raise DictionaryTooLarge(
                    f"Not even one column of this data dictionary fits the AI prompt budget of "
                    f"{budget} characters. Raise {PROMPT_BUDGET_ENV} on the server.")
            dropped = [n for n in cols if n not in set(keep)]
            steps.append(f"{len(dropped)} columns dropped")

        kept_count = total - len(dropped)
        info.update({
            "trimmed": True, "prompt_chars_after": size,
            "columns_kept": kept_count, "columns_dropped": len(dropped),
            "dropped_columns": dropped[:50], "steps": steps,
            "message": (f"The data dictionary was too large for the AI prompt ({before} "
                        f"characters, budget {budget}), so it was trimmed: {'; '.join(steps)}. "
                        f"Kept {kept_count} of {total} columns ({len(dropped)} dropped)."),
        })
        self.logger.warning(f"Dictionary trimmed for prompt: {before} -> {size} chars, "
                            f"kept {kept_count}/{total} columns")
        return work, info

    def save(self, filepath: Union[str, Path]):
        """Save dictionary to file."""
        filepath = Path(filepath)
        with open(filepath, 'w') as f:
            json.dump(self.dictionary, f, indent=2)

    def load(self, filepath: Union[str, Path]):
        """Load dictionary from file."""
        filepath = Path(filepath)
        with open(filepath, 'r') as f:
            self.dictionary = json.load(f)