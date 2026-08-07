"""Latency p50/p95/p99 for Corrector.correct(), per Step 11's metric #4.

Samples a mix of exact-match queries, known generator-produced typos, and
gibberish (no-candidate) queries, since the three take different code paths
and a p95 over only one path would be misleading.
"""
import json
import random
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app.corrector import Corrector

KEYWORDS_PATH = BASE_DIR / "index" / "keywords.json"
NEARMISS_PATH = BASE_DIR / "index" / "nearmiss.json"


def run(sample_size: int = 1000) -> dict:
    corrector = Corrector(KEYWORDS_PATH, NEARMISS_PATH)
    keywords = list(corrector.keywords.keys())
    variants = list(corrector.nearmiss.keys())

    random.seed(0)
    queries = (
        random.sample(keywords, min(sample_size // 3, len(keywords)))
        + random.sample(variants, min(sample_size // 3, len(variants)))
        + [f"zzqx{i}zzqx" for i in range(sample_size // 3)]
    )
    random.shuffle(queries)

    latencies = []
    for q in queries:
        result = corrector.correct(q)
        latencies.append(result["latency_ms"])

    latencies.sort()
    n = len(latencies)

    def pct(p):
        return latencies[min(n - 1, int(n * p))]

    return {
        "sample_size": n,
        "p50_ms": round(pct(0.50), 3),
        "p95_ms": round(pct(0.95), 3),
        "p99_ms": round(pct(0.99), 3),
        "max_ms": round(latencies[-1], 3),
    }


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(run(), indent=2))
