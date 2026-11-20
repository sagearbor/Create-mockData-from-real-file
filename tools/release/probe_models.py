"""Prove which AI Foundry deployments this app can really use.

For each deployment name given, makes ONE real generation through the app's own
generator (same prompt, same sandbox, cache off) and reports whether rows came back.
A model is only offered to users if it passes here.

    AZURE_OPENAI_ENDPOINT=... python tools/release/probe_models.py gpt-5-nano gpt-5.5 ...

Needs `az login` (LLM_AUTH=identity) or LLM_AUTH=key. Uses a tiny made-up table.
Prints one JSON line per model: ok, rows, seconds, corrections needed, error class.
"""
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.core.cache_manager import CacheManager  # noqa: E402
from src.core.llm_client import build_llm_client  # noqa: E402
from src.core.synthetic_generator import AIGenerationError, SyntheticDataGenerator  # noqa: E402
from src.utils.config import settings  # noqa: E402

METADATA = {
    "structure": {
        "columns": [
            {"name": "visit_id", "dtype": "int64", "python_type": "int"},
            {"name": "visit_date", "dtype": "object", "python_type": "str"},
            {"name": "site", "dtype": "object", "python_type": "str"},
            {"name": "score", "dtype": "float64", "python_type": "float"},
        ],
        "shape": {"rows": 20, "columns": 4},
    },
    "statistics": {
        "visit_id": {"type": "numeric", "min": 1, "max": 500, "mean": 250, "std": 140},
        "site": {"type": "string", "unique_values": 3, "is_categorical": True,
                 "most_common_values": {"North": 8, "South": 7, "East": 5}, "preserve_values": True},
        "score": {"type": "numeric", "min": 0.0, "max": 10.0, "mean": 5.1, "std": 2.2},
    },
}


def main(models):
    client = build_llm_client()
    if client is None:
        sys.exit("AI client could not be built (set AZURE_OPENAI_ENDPOINT; az login)")
    failures = 0
    for model in models:
        settings.azure_openai_chat_deployment = model
        gen = SyntheticDataGenerator(openai_client=client)
        gen.cache_manager = CacheManager(cache_dir=Path(tempfile.mkdtemp(prefix="probe-cache-")))
        started = time.time()
        row = {"model": model, "ok": False}
        try:
            df, info = gen.generate(metadata=METADATA, num_rows=20, use_cached=False)
            row.update(ok=len(df) == 20 and list(df.columns) == [c["name"] for c in METADATA["structure"]["columns"]],
                       rows=len(df), columns=list(df.columns),
                       corrected=bool(info.get("retried_after_failure")),
                       structure_mismatch=bool(info.get("structure_mismatch")))
        except AIGenerationError as err:
            row.update(error_class=err.error_class, reason=err.reason, finish_reason=err.finish_reason,
                       upstream_status=err.upstream_status)
        row["seconds"] = round(time.time() - started, 1)
        failures += not row["ok"]
        print(json.dumps(row), flush=True)
    return failures


if __name__ == "__main__":
    sys.exit(1 if main(sys.argv[1:] or [settings.azure_openai_chat_deployment]) else 0)
