"""Zero-result rate and decision mix from real traffic (Step 11 metric #2).

main.py appends one JSONL line per /api/search call to logs/queries.jsonl.
This has no data until the app has actually been used - that's expected, not
a bug: zero-result rate is a production metric, not something you can
synthesize before launch. "Correction precision" (metric #1 - of the
auto-corrections, how often the user didn't re-search) needs a richer log
that links consecutive queries into a session, which main.py does not
currently record; this only reports what's measurable from the log as it
exists today.
"""
import json
import sys
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app import config  # noqa: E402

LOG_PATH = config.QUERY_LOG_PATH


def run() -> dict:
    if not LOG_PATH.exists():
        return {"available": False, "reason": f"no log file at {LOG_PATH} yet - run the app and issue some searches first"}

    decisions = Counter()
    total = 0
    with LOG_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            decisions[entry.get("decision", "unknown")] += 1
            total += 1

    if total == 0:
        return {"available": False, "reason": "log file exists but is empty"}

    return {
        "available": True,
        "total_queries": total,
        "decision_mix": {k: round(v / total, 4) for k, v in decisions.items()},
        "zero_result_rate": round(decisions.get("no_results", 0) / total, 4),
        "note": "correction precision (metric #1) needs session-linked logging, not yet captured",
    }


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(run(), indent=2))
