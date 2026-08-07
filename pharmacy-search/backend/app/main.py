import json
import sys
import time
from pathlib import Path

from fastapi import FastAPI

from app.corrector import Corrector
from app.db import get_connection, init_db
from app import auth, catalog, cart, wishlist, checkout, inventory

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

corrector = Corrector(
    BASE_DIR / "index" / "keywords.json",
    BASE_DIR / "index" / "nearmiss.json",
    BASE_DIR / "data" / "products.jsonl",
)

LOG_DIR = BASE_DIR / "logs"
QUERY_LOG_PATH = LOG_DIR / "queries.jsonl"
CLICK_LOG_PATH = LOG_DIR / "clicks.jsonl"
LOG_DIR.mkdir(parents=True, exist_ok=True)

init_db()
with get_connection() as _conn:
    _needs_migration = _conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"] == 0
if _needs_migration:
    from build.migrate_products import migrate as _migrate_products

    _migrate_products()

# Recomputed on every startup so "best-selling" reflects recent clicks. Cheap
# at this project's scale; a real deployment would run this on a schedule
# instead of on every process start.
from build.aggregate_clicks import aggregate as _aggregate_clicks  # noqa: E402

_aggregate_clicks()

app = FastAPI(title="Pharmacy Search")
app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(cart.router)
app.include_router(wishlist.router)
app.include_router(checkout.router)
app.include_router(inventory.router)


def _append_log(path: Path, entry: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


@app.get("/api/health")
def health():
    return {"status": "ok", "keywords": len(corrector.keywords), "nearmiss": len(corrector.nearmiss)}


@app.get("/api/search")
def search(q: str = "", literal: bool = False, session_id: str = ""):
    result = corrector.correct(q)
    auto_corrected = not literal and result.get("decision") == "auto_correct"
    effective_query = result.get("suggestion") if auto_corrected else q
    result["products"] = corrector.find_products(effective_query)
    if literal:
        result["decision"] = "no_change"
    if q:
        _append_log(QUERY_LOG_PATH, {
            "ts": time.time(),
            "session_id": session_id,
            "query": q,
            "decision": result.get("decision"),
            "result_count": len(result["products"]),
            "latency_ms": result.get("latency_ms"),
        })
    return result


@app.get("/api/suggest")
def suggest(q: str = ""):
    return {"query": q, "suggestions": corrector.suggest(q)}


@app.post("/api/click")
def click(session_id: str, query: str, product: str = ""):
    _append_log(CLICK_LOG_PATH, {
        "ts": time.time(),
        "session_id": session_id,
        "query": query,
        "product": product,
    })
    return {"status": "logged"}
