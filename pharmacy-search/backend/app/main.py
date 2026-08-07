import json
import time
from pathlib import Path

from fastapi import FastAPI

from app.corrector import Corrector

BASE_DIR = Path(__file__).resolve().parents[1]
corrector = Corrector(
    BASE_DIR / "index" / "keywords.json",
    BASE_DIR / "index" / "nearmiss.json",
    BASE_DIR / "data" / "products.jsonl",
)

LOG_PATH = BASE_DIR / "logs" / "queries.jsonl"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Pharmacy Search")


def _log_query(result: dict) -> None:
    entry = {
        "ts": time.time(),
        "query": result.get("query"),
        "decision": result.get("decision"),
        "latency_ms": result.get("latency_ms"),
    }
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


@app.get("/api/health")
def health():
    return {"status": "ok", "keywords": len(corrector.keywords), "nearmiss": len(corrector.nearmiss)}


@app.get("/api/search")
def search(q: str = "", literal: bool = False):
    result = corrector.correct(q)
    auto_corrected = not literal and result.get("decision") == "auto_correct"
    effective_query = result.get("suggestion") if auto_corrected else q
    result["products"] = corrector.find_products(effective_query)
    if literal:
        result["decision"] = "no_change"
    if q:
        _log_query(result)
    return result


@app.get("/api/suggest")
def suggest(q: str = ""):
    return {"query": q, "suggestions": corrector.suggest(q)}
