"""Build tests/e2e/zephyr-manifest.json from the browser tests' own docstrings.

Each test function in tests/e2e documents its objective, precondition, numbered steps
and expected result; the module-level REQUIREMENTS dict names the requirements it
checks. This turns that into the manifest `zs record` (the DCRI zephyr skill) reads,
so the Zephyr test cases say exactly what the code does. Case keys that Zephyr has
already written back into the manifest are kept.

    python tools/release/build_zephyr_manifest.py <commit>
"""
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "e2e" / "zephyr-manifest.json"
TRACK = json.loads((ROOT / "docs" / "release-1.0" / "tracking.json").read_text())
ISSUE_IDS = {v["key"]: int(v["id"]) for v in TRACK["issues"].values()}

# The Jira issue each test mainly verifies (default: the site-test story).
ISSUE_FOR = {
    "test_E2E_07": "ADP-43", "test_E2E_01": "ADP-43",
    "test_E2E_08": "ADP-58", "test_E2E_17": "ADP-58",
    "test_E2E_09": "ADP-64", "test_E2E_12": "ADP-61", "test_E2E_13": "ADP-62",
    "test_E2E_15": "ADP-42", "test_E2E_16": "ADP-46", "test_E2E_18": "ADP-68",
}
DEFAULT_ISSUE = "ADP-44"


def _flat(text):
    return re.sub(r"\s+", " ", text).strip()


def _sections(doc):
    parts = re.split(r"\n\s*\n(?=(?:Objective|Precondition|Steps|Expected result)\b[^\n:]*:)", doc)
    out = {"title": _flat(parts[0])}
    for part in parts[1:]:
        label, body = part.split(":", 1)
        # "Steps (each is one request ...)" -> key "steps"
        key = re.match(r"(Objective|Precondition|Steps|Expected result)", label.strip()).group(1).lower()
        out[key] = body.strip()
    return out


def _steps(text, expected):
    items = [_flat(s) for s in re.split(r"(?m)^\s*\d+\.\s+", text) if s.strip()]
    steps = [{"action": item, "data": "Made-up data created by the test", "expected": ""} for item in items]
    if steps:
        steps[-1]["expected"] = _flat(expected)
    return steps


def main(commit):
    previous = {}
    if OUT.exists():
        for t in json.loads(OUT.read_text()).get("tests", []):
            previous[t["id"]] = t
    tests = []
    for path in sorted((ROOT / "tests" / "e2e").glob("test_e2e_*.py")):
        tree = ast.parse(path.read_text())
        reqs = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "REQUIREMENTS":
                reqs = ast.literal_eval(node.value)
        for node in tree.body:
            if not (isinstance(node, ast.FunctionDef) and node.name.startswith("test_E2E_")):
                continue
            s = _sections(ast.get_docstring(node) or "")
            test_id = f"tests.e2e.{path.stem}.{node.name}"
            issue = ISSUE_FOR.get(node.name[:11], DEFAULT_ISSUE)
            entry = dict(previous.get(test_id, {}))
            entry.update({
                "id": test_id,
                "name": "Mock Data Generator (browser): " + s["title"].rstrip("."),
                "objective": _flat(s.get("objective", "")) + " Requirements: " + ", ".join(reqs.get(node.name, [])) + ".",
                "precondition": _flat(s.get("precondition", "")),
                "steps": _steps(s.get("steps", ""), s.get("expected result", "")),
                "issue": issue,
                "source": f"tests/e2e/{path.name}::{node.name}",
            })
            tests.append(entry)
    used = sorted({t["issue"] for t in tests})
    manifest = {
        "project": "ADP",
        "folder": "Mock Data Generator 1.0/Browser tests on the deployed site",
        "source_repo": "sagearbor/Create-mockData-from-real-file",
        "commit": commit,
        "run_command": "MDG_BASE_URL=<site address> pytest tests/e2e -m e2e --junitxml=results-e2e.xml",
        "environment": "Deployed development site (VPN only), real AI model, Chromium driven by Playwright, made-up data created by the tests",
        "issue_ids": {k: ISSUE_IDS[k] for k in used},
        "cycle_issues": ["ADP-44"],
        "tests": tests,
    }
    OUT.write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"{len(tests)} tests -> {OUT.relative_to(ROOT)}; issues {used}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "unknown")
