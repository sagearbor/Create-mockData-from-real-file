"""No raw cell value may reach the model prompt (ADP-40).

The extractor is the single choke point: whatever extract() returns is put in
the prompt, written to the cache and returned by the upload endpoints. These
tests plant distinctive marker values in a DataFrame and look for them in the
extractor output and in the prompt text.
"""

import json
from types import SimpleNamespace

import pandas as pd
import pytest

from src.core.metadata_extractor import MetadataExtractor, is_identifier_like_name
from src.core.synthetic_generator import SyntheticDataGenerator

MODES = ("strict", "balanced", "permissive")


def _generator():
    """A generator with no AI client and no disk cache; only the prompt builder is used."""
    gen = SyntheticDataGenerator(openai_client=SimpleNamespace(
        chat=SimpleNamespace(completions=None)))
    gen.cache_manager = SimpleNamespace(
        cache_generation=lambda *a, **k: None, find_similar_cached=lambda *a, **k: None)
    return gen


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # nothing is written into the repo


def _outputs(df, mode):
    """(metadata, metadata as JSON text, prompt text) for one safety mode."""
    extractor = MetadataExtractor(safety_mode=mode)
    metadata = extractor.extract(df)
    dumped = json.dumps(metadata, default=str)
    prompt = _generator()._construct_generation_prompt(metadata, 50, 0.8)
    # The safety net must have nothing left to do.
    assert json.loads(extractor.to_secure_json(metadata)) == json.loads(dumped)
    return metadata, dumped, prompt


def _assert_absent(markers, dumped, prompt, mode):
    for marker in markers:
        assert marker not in dumped, f"{mode}: {marker!r} is in the extracted metadata"
        assert marker not in prompt, f"{mode}: {marker!r} is in the model prompt"


def _assert_masked(col_stats, expected_rows):
    """Placeholders only, and the counts are still there."""
    assert col_stats["preserve_values"] is False
    values = col_stats["most_common_values"]
    assert values, "the distribution shape was dropped"
    assert all(k.startswith("value_") for k in values), list(values)
    assert all(isinstance(c, int) and c >= 1 for c in values.values())
    assert sum(values.values()) <= expected_rows


def _numbered(template, n, start=1000):
    return [template.format(i) for i in range(start, start + n)]


# Unique, sensitive columns. Column names are neutral on purpose: the value
# checks alone must be enough. (column, values, markers that must never appear)
UNIQUE_CASES = {
    "unique_names": ("participant",
                     ["Zzyzx Quillfeather", "Bartholomew Xanthopoulos"] + _numbered("Qwyrk Vandersnoot{}", 38),
                     ["Zzyzx Quillfeather", "Bartholomew Xanthopoulos", "Quillfeather", "Vandersnoot"]),
    "mrn_ids": ("chart",
                ["MRN-9917354", "MRN-9917360"] + _numbered("MRN-88{}", 38, 20000),
                ["MRN-9917354", "MRN-9917360", "9917354", "MRN-8820000"]),
    "dashed_ssns": ("code",
                    ["917-83-6462", "918-84-7573"] + [f"9{i:02d}-55-{7000 + i}" for i in range(38)],
                    ["917-83-6462", "918-84-7573", "917-83", "83-6462"]),
    "emails": ("contact",
               ["zzyzx.quill@fernwick-example.org", "bxanth@fernwick-example.org"]
               + _numbered("user{}@fernwick-example.org", 38),
               ["zzyzx.quill", "bxanth", "fernwick"]),
    "phones": ("reach",
               ["919-837-6462", "919-837-6470"] + [f"919-837-{7000 + i}" for i in range(38)],
               ["919-837-6462", "919-837-6470", "837-6462", "919-837"]),
    "free_text": ("remarks",
                  ["Pt Zzyzx reports dizziness after starting florbetapir",
                   "Family history of quillfeather syndrome in mother"]
                  + _numbered("Followed up by telephone regarding visit {}", 38),
                  ["Zzyzx", "dizziness", "florbetapir", "quillfeather syndrome", "telephone regarding"]),
}


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", sorted(UNIQUE_CASES))
def test_unique_sensitive_values_never_leave_the_extractor(case, mode):
    column, values, markers = UNIQUE_CASES[case]
    df = pd.DataFrame({column: values, "age": range(40, 40 + len(values))})

    metadata, dumped, prompt = _outputs(df, mode)

    _assert_absent(markers, dumped, prompt, mode)
    # Every cell of the column, not just the markers.
    _assert_absent([json.dumps(v)[1:-1] for v in values], dumped, prompt, mode)
    _assert_masked(metadata["statistics"][column], len(values))


@pytest.mark.parametrize("mode", MODES)
def test_id_pattern_describes_the_shape_without_quoting_a_cell(mode):
    """The old `example` field quoted the first cell in full."""
    values = ["MRN-9917354"] + [f"MRN-{8820000 + i}" for i in range(39)]
    df = pd.DataFrame({"chart": values})

    metadata, dumped, prompt = _outputs(df, mode)

    id_pattern = metadata["patterns"]["chart"]["id_pattern"]
    assert "example" not in id_pattern
    assert id_pattern["digit_count"] == 7
    assert id_pattern["prefix_length"] == 4
    _assert_absent(["9917354", "8820000"], dumped, prompt, mode)
    if mode == "strict":
        assert "prefix" not in id_pattern
        assert "MRN" not in dumped
    else:
        # A short alphabetic prefix shared by many distinct IDs is not a cell value.
        assert id_pattern["prefix"] == "MRN-"
        assert id_pattern["shape"] == "MRN-<7 digits>"


@pytest.mark.parametrize("mode", MODES)
def test_small_file_of_distinct_names_is_masked(mode):
    """Five rows used to pass the '<=6 unique values' rule and were sent verbatim."""
    names = ["Zzyzx Quillfeather", "Bartholomew Xanthopoulos", "Ottoline Brackenridge",
             "Thaddeus Wickersham", "Persephone Zdunowski"]
    df = pd.DataFrame({"participant": names, "site": ["Nfld", "Nfld", "Nfld", "Sask", "Sask"],
                       "chart": ["QX001", "QX002", "QX003", "QX004", "QX005"]})

    metadata, dumped, prompt = _outputs(df, mode)

    _assert_absent(names + ["Quillfeather", "Nfld", "Sask", "QX00", "QX"], dumped, prompt, mode)
    _assert_masked(metadata["statistics"]["participant"], 5)
    _assert_masked(metadata["statistics"]["site"], 5)
    for col_patterns in metadata["patterns"].values():
        assert "common_prefix" not in col_patterns
        assert "common_suffix" not in col_patterns
        assert "prefix" not in col_patterns.get("id_pattern", {})


@pytest.mark.parametrize("mode", MODES)
def test_small_file_with_one_repeated_name_is_masked(mode):
    """Five identical rows have unique_ratio 0.2 but are still a tiny file."""
    df = pd.DataFrame({"participant": ["Zzyzx Quillfeather"] * 5})

    metadata, dumped, prompt = _outputs(df, mode)

    _assert_absent(["Zzyzx", "Quillfeather"], dumped, prompt, mode)
    _assert_masked(metadata["statistics"]["participant"], 5)


def _categories_frame(column):
    return pd.DataFrame({column: ["M"] * 90 + ["F"] * 80 + ["U"] * 30, "age": range(200)})


@pytest.mark.parametrize("mode", ("balanced", "permissive"))
def test_repeated_categories_are_preserved(mode):
    """Genuine categories still reach the model so distributions can be matched."""
    metadata, _, prompt = _outputs(_categories_frame("grp"), mode)

    stats = metadata["statistics"]["grp"]
    assert stats["preserve_values"] is True
    assert stats["most_common_values"] == {"M": 90, "F": 80, "U": 30}
    assert '"M": 90' in prompt


def test_repeated_categories_are_placeholders_in_strict_mode():
    metadata, _, prompt = _outputs(_categories_frame("grp"), "strict")

    stats = metadata["statistics"]["grp"]
    assert stats["preserve_values"] is False
    assert stats["most_common_values"] == {"value_0": 90, "value_1": 80, "value_2": 30}
    assert '"M": 90' not in prompt


@pytest.mark.parametrize("mode", MODES)
def test_identifier_named_column_is_never_preserved(mode):
    """Three repeated values would qualify, but the column is called patient_name."""
    names = ["Zzyzx Quillfeather", "Bartholomew Xanthopoulos", "Ottoline Brackenridge"]
    df = pd.DataFrame({"patient_name": [names[0]] * 90 + [names[1]] * 80 + [names[2]] * 30})

    metadata, dumped, prompt = _outputs(df, mode)

    _assert_absent(names + ["Zzyzx", "Xanth", "Ottoline", "ridge"], dumped, prompt, mode)
    stats = metadata["statistics"]["patient_name"]
    assert stats["most_common_values"] == {"value_0": 90, "value_1": 80, "value_2": 30}
    assert stats["preserve_values"] is False


@pytest.mark.parametrize("mode", ("balanced", "permissive"))
def test_rare_value_in_a_preserved_column_is_masked(mode):
    """One stray entry in a category column must not ride along with the categories."""
    df = pd.DataFrame({"grp": ["M"] * 100 + ["F"] * 99 + ["Zzyzx Quillfeather"]})

    metadata, dumped, prompt = _outputs(df, mode)

    _assert_absent(["Zzyzx", "Quillfeather"], dumped, prompt, mode)
    assert metadata["statistics"]["grp"]["most_common_values"] == {"M": 100, "F": 99, "value_2": 1}


@pytest.mark.parametrize("mode", ("balanced", "permissive"))
@pytest.mark.parametrize("values", [
    ["917-83-6462", "918-84-7573", "919-85-8684"],                        # SSNs
    ["zq@fernwick-example.org", "bx@fernwick-example.org", "ob@fernwick-example.org"],
    ["919-837-6462", "919-837-6470", "919-837-6488"],                     # phones
    ["1957-03-14", "1961-11-02", "1949-07-29"],                           # dates
    ["Acct 4417392", "Acct 4417393", "Acct 4417394"],                     # long digit runs
    ["Q" * 31, "R" * 31, "S" * 31],                                       # too long
])
def test_repeated_values_that_look_sensitive_are_not_preserved(values, mode):
    df = pd.DataFrame({"grp": [values[0]] * 90 + [values[1]] * 80 + [values[2]] * 30})

    metadata, dumped, prompt = _outputs(df, mode)

    _assert_absent(values, dumped, prompt, mode)
    _assert_masked(metadata["statistics"]["grp"], 200)


@pytest.mark.parametrize("mode", MODES)
def test_identifier_numeric_column_does_not_emit_exact_min_max(mode):
    """min/max of a numeric ID column are two real identifiers."""
    ids = [9917354 + 37 * i for i in range(40)]          # even count: median is not a cell
    df = pd.DataFrame({"patient_id": ids, "age": range(40, 80)})

    metadata, dumped, prompt = _outputs(df, mode)

    stats = metadata["statistics"]["patient_id"]
    assert "min" not in stats and "max" not in stats
    assert stats["min_max_omitted"] is True
    assert "mean" in stats and "std" in stats
    _assert_absent([str(min(ids)), str(max(ids))], dumped, prompt, mode)
    # Ordinary numeric columns keep their range.
    assert metadata["statistics"]["age"]["min"] == 40.0
    assert metadata["statistics"]["age"]["max"] == 79.0


@pytest.mark.parametrize("name", [
    "patient_id", "subject id", "MRN", "first_name", "patientId", "patientid", "DOB",
    "date_of_birth", "home_address", "Email", "phone2", "notes", "Comments", "zip",
    "ZipCode", "postal_code", "ssn_last4", "ID",
    "SUBJID", "USUBJID", "PATID", "PTID", "EMPID", "CUSTID",
])
def test_identifier_like_names_are_recognised(name):
    assert is_identifier_like_name(name)


@pytest.mark.parametrize("name", ["valid", "paid", "sex", "status", "arm", "age", "dobutamine_dose", None])
def test_ordinary_names_are_not_identifier_like(name):
    assert not is_identifier_like_name(name)


def test_prompt_tells_the_model_how_to_read_placeholders():
    system_prompt = _generator()._get_system_prompt()
    assert "value_0" in system_prompt and "placeholder" in system_prompt


# --------------------------------------------------------------------------- #
# Numbers and dates: no exact smallest, largest or middle value of a real cell
# --------------------------------------------------------------------------- #
def _stats(df, mode="balanced"):
    from src.core.metadata_extractor import MetadataExtractor
    return MetadataExtractor(safety_mode=mode).extract(df)["statistics"]


def test_identifier_like_number_column_sends_no_order_statistics():
    import pandas as pd
    df = pd.DataFrame({"patient_id": [9917354 + i * 7 for i in range(60)]})
    s = _stats(df)["patient_id"]
    for key in ("min", "max", "median", "q25", "q75"):
        assert key not in s
    assert s["order_statistics_omitted"] is True and "mean" in s
    few = _stats(pd.DataFrame({"patient_id": [9917354, 9917361, 9917368]}))["patient_id"]
    assert "mean" not in few


def test_small_file_numbers_are_rounded_and_the_range_is_widened():
    import pandas as pd
    df = pd.DataFrame({"weight": [61.37, 72.91, 88.43, 54.19, 93.77]})
    s = _stats(df)["weight"]
    assert s["values_rounded"] is True
    assert s["min"] == 50.0 and s["max"] == 100.0            # widened, never a real cell
    assert s["median"] == 73.0
    text = str(s)
    for cell in ("61.37", "72.91", "88.43", "54.19", "93.77"):
        assert cell not in text


def test_strict_mode_rounds_numbers_even_in_a_large_file():
    import pandas as pd
    df = pd.DataFrame({"weight": [61.37 + i * 0.113 for i in range(200)]})
    strict, balanced = _stats(df, "strict")["weight"], _stats(df, "balanced")["weight"]
    assert strict["values_rounded"] is True and strict["min"] == 60.0
    assert "values_rounded" not in balanced and balanced["min"] == 61.37


def test_date_ranges_are_widened_never_exact():
    import pandas as pd
    visits = pd.to_datetime(["2023-03-17"] * 10 + ["2023-08-09"] * 10 + ["2024-02-21"] * 10)
    df = pd.DataFrame({"visit_date": visits, "date_of_birth": visits})
    s = _stats(df)
    assert s["visit_date"]["min"].startswith("2023-03-01") and s["visit_date"]["max"].startswith("2024-02-29")
    assert s["visit_date"]["range_rounded_to"] == "month"
    assert s["date_of_birth"]["min"].startswith("2023-01-01") and s["date_of_birth"]["max"].startswith("2024-12-31")
    assert s["date_of_birth"]["range_rounded_to"] == "year"
    assert _stats(df, "strict")["visit_date"]["range_rounded_to"] == "year"
    small = pd.DataFrame({"visit_date": pd.to_datetime(["2023-03-17", "2023-08-09"])})
    assert _stats(small)["visit_date"]["min"].startswith("2023-01-01")
    for mode in ("strict", "balanced", "permissive"):
        text = str(_stats(df, mode))
        for cell in ("2023-03-17", "2024-02-21"):
            assert cell not in text
