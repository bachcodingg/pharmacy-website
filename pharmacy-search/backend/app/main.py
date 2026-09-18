import json
import logging
import sys
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import config, ratelimit
from app.logging_config import configure_logging
from app.catalog import search_catalog
from app.corrector import get_corrector
from app.db import get_connection, init_db
from app import auth, catalog, cart, wishlist, checkout, inventory
from app import admin_orders, admin_users, admin_coupons, admin_corrections, admin_reports

BASE_DIR = config.BASE_DIR
sys.path.insert(0, str(BASE_DIR))

# Before anything else logs: uvicorn installs its own handlers on import, and
# whichever side configures last wins.
configure_logging(config.LOG_LEVEL)
log = logging.getLogger("pharmacy.request")

# Shared with the catalog router, which falls back to it when a browse query
# matches no product name literally.
corrector = get_corrector()

# Under the data directory (the mounted volume in production), not inside the
# image. These files are the input to the learning loop; when they lived in
# the image every machine restart threw them away.
config.ensure_dirs()
QUERY_LOG_PATH = config.QUERY_LOG_PATH
CLICK_LOG_PATH = config.CLICK_LOG_PATH

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


@app.middleware("http")
async def request_logging(request: Request, call_next):
    """One structured line per request.

    Registered after security_headers, which in Starlette means it wraps it -
    so it sees the status actually sent, and an exception raised anywhere
    below it still produces a log line before it propagates.

    The query string is deliberately not logged. Search terms are already
    recorded, with consent-relevant context, in the query log; repeating them
    here would scatter the same personal data across a second system with a
    different retention policy, and a token that ends up in a URL by mistake
    would be captured forever."""
    started = time.perf_counter()
    # Fly stamps every inbound request; reusing its id means a line here can
    # be joined to the edge's own logs instead of living in its own universe.
    request_id = request.headers.get("fly-request-id") or uuid.uuid4().hex
    fields = {
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
    }
    try:
        response = await call_next(request)
    except Exception:
        log.exception("request_failed", extra={
            **fields, "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        })
        raise

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    # The healthcheck runs every 15s forever. At INFO it would be most of the
    # drain's volume and none of its value.
    level = logging.DEBUG if request.url.path == "/api/health" else logging.INFO
    if response.status_code >= 500:
        level = logging.ERROR
    elif response.status_code >= 400:
        level = logging.WARNING
    log.log(level, "request", extra={
        **fields, "status": response.status_code, "duration_ms": duration_ms,
    })
    # Echoed so a user reporting a problem can quote something findable.
    response.headers["X-Request-Id"] = request_id
    return response


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Baseline browser hardening.

    The CSP is deliberately strict about script sources - 'self' only, no
    inline script - which the frontend satisfies because Vite emits external
    bundles. style-src keeps 'unsafe-inline' because the views set inline
    style attributes; tightening that means moving those into the stylesheet.
    img-src allows the Long Châu CDN the catalogue images still point at."""
    response = await call_next(request)
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https://cdn.nhathuoclongchau.com.vn; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'",
    )
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    # Only meaningful over TLS, and Fly terminates TLS with force_https.
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(cart.router)
app.include_router(wishlist.router)
app.include_router(checkout.router)
app.include_router(inventory.router)
app.include_router(admin_orders.router)
app.include_router(admin_users.router)
app.include_router(admin_coupons.router)
app.include_router(admin_corrections.router)
app.include_router(admin_reports.router)


def _clip(value: str, limit: int = config.MAX_LOG_FIELD_LENGTH) -> str:
    """Unauthenticated callers decide what goes in these fields, and the log
    is an append-only file on a volume - so nothing unbounded reaches it."""
    return (value or "")[:limit]


def _append_log(path: Path, entry: dict) -> None:
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        # Analytics must never take the request down with it. A full or
        # read-only volume degrades logging, not searching.
        pass


@app.get("/api/health")
def health():
    return {"status": "ok", "keywords": len(corrector.keywords), "nearmiss": len(corrector.nearmiss)}


@app.get("/api/search")
def search(request: Request, q: str = "", literal: bool = False, session_id: str = ""):
    # The fuzzy fallback runs an O(n*m) edit distance against ~15k vocabulary
    # forms, so the length of q is a cost the caller controls. Cap it.
    q = (q or "")[: config.MAX_QUERY_LENGTH]
    ratelimit.enforce(request, "search", 120, 60)

    result = corrector.correct(q)
    auto_corrected = not literal and result.get("decision") == "auto_correct"
    effective_query = result.get("suggestion") if auto_corrected else q

    # Products come from the product table, not the corrector's JSONL
    # snapshot, so search and the shop agree about what exists, what it
    # costs, and whether it has been withdrawn.
    with get_connection() as conn:
        products = search_catalog(conn, effective_query)
    result["products"] = products

    if literal:
        result["decision"] = "no_change"
    elif not products and result.get("decision") in ("auto_correct", "did_you_mean", "no_change"):
        # The reading was plausible but nothing in the live catalogue answers
        # to it - say so rather than presenting an empty success.
        result["decision"] = "no_results"
    elif products and result.get("decision") == "no_results":
        result["decision"] = "did_you_mean"

    if q:
        _append_log(QUERY_LOG_PATH, {
            "ts": time.time(),
            "session_id": _clip(session_id, 100),
            "query": _clip(q),
            "decision": result.get("decision"),
            "result_count": len(products),
            "latency_ms": result.get("latency_ms"),
        })
    return result


@app.get("/api/suggest")
def suggest(request: Request, q: str = ""):
    q = (q or "")[: config.MAX_QUERY_LENGTH]
    ratelimit.enforce(request, "suggest", 240, 60)
    return {"query": q, "suggestions": corrector.suggest(q)}


@app.post("/api/click")
def click(request: Request, session_id: str, query: str, product: str = ""):
    ratelimit.enforce(request, "click", 120, 60)
    _append_log(CLICK_LOG_PATH, {
        "ts": time.time(),
        "session_id": _clip(session_id, 100),
        "query": _clip(query),
        "product": _clip(product),
    })
    return {"status": "logged"}


# Serves the built frontend (frontend/dist) when it's present, so the API and
# the SPA can ship as one process on one origin - no CORS, no separate static
# host. Mounted last: FastAPI matches the /api/* routes above before falling
# through to this catch-all. html=True serves index.html at "/"; nothing
# below it needs a path-based SPA fallback because the frontend uses a hash
# router (#/browse) - the server only ever sees requests for "/" and static
# asset files, never a route path.
_FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
