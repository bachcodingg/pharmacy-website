"""Human-typed test set (Step 11 metric: 'ask several people to type 100 drug
names quickly'). This repo cannot recruit and time actual humans, so this
module only provides the format and the runner - it does not fabricate data
pretending to be human-typed, since that would defeat the entire point of
this step (generated typos have a different error distribution than real
ones: hesitations, doubled letters, half-remembered spellings).

To collect real data: give people a list of ~100 drug/product names from
index/keywords.json, have them type each quickly from memory or dictation
into eval/human_typed.tsv as `<what they typed>\t<the keyword they meant>`.
"""
import csv
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app.corrector import Corrector

TSV_PATH = BASE_DIR / "eval" / "human_typed.tsv"
KEYWORDS_PATH = BASE_DIR / "index" / "keywords.json"
NEARMISS_PATH = BASE_DIR / "index" / "nearmiss.json"


def load_cases():
    if not TSV_PATH.exists():
        return []
    with TSV_PATH.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    return [(r["query"], r["expected_keyword"]) for r in rows if r.get("query") and r.get("expected_keyword")]


def run() -> dict:
    cases = load_cases()
    if not cases:
        return {
            "available": False,
            "reason": f"{TSV_PATH} has no rows yet - see this module's docstring for how to collect them",
        }

    corrector = Corrector(KEYWORDS_PATH, NEARMISS_PATH, BASE_DIR / "data" / "products.jsonl")
    correct = 0
    for query, expected in cases:
        result = corrector.correct(query)
        got = result.get("suggestion") or (result.get("candidates") or [{}])[0].get("keyword")
        if got == expected:
            correct += 1

    return {"available": True, "total_cases": len(cases), "accuracy": round(correct / len(cases), 4)}


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(run(), indent=2))
