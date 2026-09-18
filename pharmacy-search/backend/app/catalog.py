import json
import sqlite3
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.corrector import get_corrector, search_key
from app.db import get_connection, row_to_dict

router = APIRouter(prefix="/api/products", tags=["catalog"])

SORT_OPTIONS = {
    "name": "p.web_name ASC",
    "price_asc": "p.price ASC",
    "price_desc": "p.price DESC",
    "newest": "p.id DESC",
    "top_rated": "(rating.avg_rating IS NULL), rating.avg_rating DESC, rating.rating_count DESC",
    "best_selling": "COALESCE(clicks.count, 0) DESC, rating.rating_count DESC",
}


def _serialize_product(row: dict) -> dict:
    return {
        "id": row["id"],
        "sku": row["sku"],
        "sourceSku": row["source_sku"],
        "webName": row["web_name"],
        "imageUrl": row["image_url"],
        "shortDescription": row["short_description"],
        "category": row["category"],
        "brand": row["brand"],
        "brand_is_estimated": bool(row["brand_is_estimated"]),
        "prescription": bool(row["prescription"]) if row["prescription"] is not None else None,
        "ingredients": json.loads(row["ingredients_json"] or "[]"),
        "price": row["price"],
        "price_unit": row["price_unit"],
        "currency": row["currency"],
        "price_is_estimated": bool(row["price_is_estimated"]),
        "stock": row["stock"],
        "stock_is_estimated": bool(row["stock_is_estimated"]),
        "rating_avg": round(row["rating_avg"], 2) if row["rating_avg"] is not None else None,
        "rating_count": row["rating_count"] or 0,
    }


def _build_filters(q, category, brand, min_price, max_price, min_rating, in_stock):
    clauses = ["p.is_active = 1"]
    params: list = []
    # Match each query word against the folded name (products.search_text)
    # rather than the raw one. A LIKE on web_name compares diacritics
    # literally, so "ban chai" could never reach "Bàn chải ..."; folding both
    # sides puts them in the same alphabet. Words are AND-ed independently so
    # order and the gaps between them stop mattering too - "ban chai rang"
    # finds "Bàn chải đánh răng".
    for word in search_key(q).split():
        # Mirrors _term_matches in the corrector: a one-letter term has to land
        # on a whole word, since as a substring it is in nearly every name.
        if len(word) == 1:
            clauses.append("' ' || p.search_text || ' ' LIKE ?")
            params.append(f"% {word} %")
        else:
            clauses.append("p.search_text LIKE ?")
            params.append(f"%{word}%")
    if category:
        clauses.append("p.category = ?")
        params.append(category)
    if brand:
        clauses.append("p.brand = ?")
        params.append(brand)
    if min_price is not None:
        clauses.append("p.price >= ?")
        params.append(min_price)
    if max_price is not None:
        clauses.append("p.price <= ?")
        params.append(max_price)
    if min_rating is not None:
        clauses.append("rating.avg_rating >= ?")
        params.append(min_rating)
    if in_stock:
        clauses.append("p.stock > 0")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


_JOIN_CLAUSE = """
    LEFT JOIN (
        SELECT product_id, AVG(rating) AS avg_rating, COUNT(*) AS rating_count
        FROM reviews GROUP BY product_id
    ) rating ON rating.product_id = p.id
    LEFT JOIN click_counts clicks ON clicks.product_id = p.id
"""


def _match_exists(conn, where: str, params: list) -> bool:
    return conn.execute(
        f"SELECT 1 FROM products p {_JOIN_CLAUSE} {where} LIMIT 1", params
    ).fetchone() is not None


def _resolve_query(conn, q, category, brand, min_price, max_price, min_rating, in_stock):
    """Return the query to actually search with, plus the correction applied.

    Folding accents handles a differently-spelled word; it does nothing for a
    misspelled one. So when the literal query matches no product we ask the
    spelling corrector for a reading and use it - but only after confirming it
    finds something, otherwise a garbage query would be reported as "corrected"
    to an equally empty result."""
    filters = (category, brand, min_price, max_price, min_rating, in_stock)
    if not q or _match_exists(conn, *_build_filters(q, *filters)):
        return q, None
    suggestion = get_corrector().correct(q).get("suggestion") or ""
    if not suggestion or search_key(suggestion) == search_key(q):
        return q, None
    if not _match_exists(conn, *_build_filters(suggestion, *filters)):
        return q, None
    return suggestion, suggestion


def search_catalog(conn, query: str, limit: int = 10, min_coverage: float = 0.6) -> list:
    """Resolve a (corrected) query against the live product table.

    /api/search used to answer from the corrector's own products.jsonl
    snapshot, loaded once at import. That made the search engine and the shop
    two different datastores: a soft-deleted product still showed up in
    search, admin price and name edits never did, and the results carried no
    id or price - so a search result could not be opened or added to a cart.
    Search now reads the same rows the catalogue does.

    Coverage scoring is kept from the old implementation: a query still
    matches when most of its terms land, so one unresolved token does not zero
    out an otherwise good query."""
    terms = search_key(query).split()
    if not terms:
        return []
    # Mirrors _build_filters: a one-letter term has to hit a whole word.
    score_parts, params = [], []
    for term in terms:
        if len(term) == 1:
            score_parts.append("(CASE WHEN ' ' || p.search_text || ' ' LIKE ? THEN 1 ELSE 0 END)")
            params.append(f"% {term} %")
        else:
            score_parts.append("(CASE WHEN p.search_text LIKE ? THEN 1 ELSE 0 END)")
            params.append(f"%{term}%")
    score_sql = " + ".join(score_parts)
    needed = max(1, int(len(terms) * min_coverage + 0.999))  # ceil

    rows = conn.execute(
        f"""SELECT p.*, rating.avg_rating AS rating_avg, rating.rating_count AS rating_count,
                   ({score_sql}) AS hits
            FROM products p {_JOIN_CLAUSE}
            WHERE p.is_active = 1 AND ({score_sql}) >= ?
            ORDER BY hits DESC, COALESCE(clicks.count, 0) DESC, p.web_name
            LIMIT ?""",
        (*params, *params, needed, limit),
    ).fetchall()

    results = []
    for row in rows:
        product = _serialize_product(row_to_dict(row))
        product["coverage"] = round(row["hits"] / len(terms), 2)
        results.append(product)
    return results


@router.get("")
def list_products(
    q: str = "",
    category: str = "",
    brand: str = "",
    min_price: int | None = None,
    max_price: int | None = None,
    min_rating: float | None = None,
    in_stock: bool = False,
    sort: str = "name",
    page: int = 1,
    page_size: int = 20,
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    offset = (page - 1) * page_size
    order_by = SORT_OPTIONS.get(sort, SORT_OPTIONS["name"])

    with get_connection() as conn:
        effective_q, corrected_to = _resolve_query(
            conn, q, category, brand, min_price, max_price, min_rating, in_stock
        )
        where, params = _build_filters(
            effective_q, category, brand, min_price, max_price, min_rating, in_stock
        )
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM products p {_JOIN_CLAUSE} {where}", params
        ).fetchone()["c"]
        rows = conn.execute(
            f"""SELECT p.*, rating.avg_rating AS rating_avg, rating.rating_count AS rating_count
                FROM products p {_JOIN_CLAUSE} {where}
                ORDER BY {order_by}, p.id
                LIMIT ? OFFSET ?""",
            (*params, page_size, offset),
        ).fetchall()
        items = [_serialize_product(row_to_dict(row)) for row in rows]

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "corrected_to": corrected_to,
    }


@router.get("/facets")
def get_facets(q: str = "", category: str = ""):
    """Distinct brands and price bounds for the current filter context, so the
    filter UI can offer only choices that actually return results."""
    with get_connection() as conn:
        # Same correction as the listing, so the filter panel offers the brands
        # of the products actually on screen instead of going empty on a typo.
        effective_q, _ = _resolve_query(conn, q, category, "", None, None, None, False)
        where, params = _build_filters(effective_q, category, "", None, None, None, False)
        brands = conn.execute(
            f"SELECT DISTINCT p.brand FROM products p {_JOIN_CLAUSE} {where} "
            f"{'AND' if where else 'WHERE'} p.brand IS NOT NULL ORDER BY p.brand",
            params,
        ).fetchall()
        bounds = conn.execute(
            f"SELECT MIN(p.price) AS min_price, MAX(p.price) AS max_price FROM products p {_JOIN_CLAUSE} {where}",
            params,
        ).fetchone()
    return {
        "brands": [r["brand"] for r in brands],
        "price_min": bounds["min_price"],
        "price_max": bounds["max_price"],
    }


@router.get("/{product_id}")
def get_product(product_id: int):
    with get_connection() as conn:
        row = conn.execute(
            f"""SELECT p.*, rating.avg_rating AS rating_avg, rating.rating_count AS rating_count
                FROM products p {_JOIN_CLAUSE} WHERE p.id = ?""",
            (product_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Product not found")
    return _serialize_product(row_to_dict(row))


class ReviewRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


@router.get("/{product_id}/reviews")
def list_reviews(product_id: int):
    with get_connection() as conn:
        product = conn.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        rows = conn.execute(
            "SELECT reviews.*, users.name AS user_name FROM reviews "
            "JOIN users ON users.id = reviews.user_id "
            "WHERE product_id = ? ORDER BY created_at DESC",
            (product_id,),
        ).fetchall()
    return [row_to_dict(r) for r in rows]


def _has_purchased(conn, product_id: int, user_id: int) -> bool:
    """Whether this user has ordered this product, cancelled orders aside.

    One definition, used both to gate the review and to stamp
    verified_purchase on it. Two copies of this predicate would eventually
    disagree, and the disagreement would show up as a review that the gate
    let through and the badge calls unverified."""
    return conn.execute(
        """SELECT 1 FROM order_items oi JOIN orders o ON o.id = oi.order_id
           WHERE oi.product_id = ? AND o.user_id = ? AND o.status != 'cancelled' LIMIT 1""",
        (product_id, user_id),
    ).fetchone() is not None


@router.post("/{product_id}/reviews", status_code=201)
def create_review(product_id: int, body: ReviewRequest, user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        product = conn.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        existing = conn.execute(
            "SELECT id FROM reviews WHERE product_id = ? AND user_id = ?", (product_id, user["id"])
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="You've already reviewed this product")
        # N-08: reviews are for buyers. Anyone with an email address could
        # previously rate any product, which is the whole business model of a
        # review-farming operation - and on a pharmacy, ratings on medicines
        # are advice. The verified_purchase column already recorded who had
        # actually bought the thing; this makes it the gate rather than a
        # decoration next to the star rating.
        purchased = _has_purchased(conn, product_id, user["id"])
        if not purchased:
            raise HTTPException(
                status_code=403,
                detail="You can only review a product you have ordered",
            )
        try:
            cursor = conn.execute(
                "INSERT INTO reviews (product_id, user_id, rating, comment, created_at, verified_purchase) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (product_id, user["id"], body.rating, body.comment, time.time(), int(purchased)),
            )
        except sqlite3.IntegrityError:
            # The unique index is the real guard; the SELECT above is just the
            # fast path that produces a nicer message.
            raise HTTPException(status_code=409, detail="You've already reviewed this product")
        row = conn.execute("SELECT reviews.*, users.name AS user_name FROM reviews JOIN users ON users.id = reviews.user_id WHERE reviews.id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_dict(row)
