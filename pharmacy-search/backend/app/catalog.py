import json
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import get_current_user
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
    if q:
        clauses.append("p.web_name LIKE ?")
        params.append(f"%{q}%")
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

    where, params = _build_filters(q, category, brand, min_price, max_price, min_rating, in_stock)

    with get_connection() as conn:
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

    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.get("/facets")
def get_facets(q: str = "", category: str = ""):
    """Distinct brands and price bounds for the current filter context, so the
    filter UI can offer only choices that actually return results."""
    where, params = _build_filters(q, category, "", None, None, None, False)
    with get_connection() as conn:
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
    comment: str | None = None


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
        cursor = conn.execute(
            "INSERT INTO reviews (product_id, user_id, rating, comment, created_at) VALUES (?, ?, ?, ?, ?)",
            (product_id, user["id"], body.rating, body.comment, time.time()),
        )
        row = conn.execute("SELECT reviews.*, users.name AS user_name FROM reviews JOIN users ON users.id = reviews.user_id WHERE reviews.id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_dict(row)
