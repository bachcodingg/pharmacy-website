import json
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.db import get_connection, row_to_dict

router = APIRouter(prefix="/api/products", tags=["catalog"])


def _serialize_product(row: dict, rating_avg, rating_count: int) -> dict:
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
        "rating_avg": round(rating_avg, 2) if rating_avg is not None else None,
        "rating_count": rating_count,
    }


@router.get("")
def list_products(q: str = "", category: str = "", page: int = 1, page_size: int = 20):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    offset = (page - 1) * page_size

    clauses = []
    params: list = []
    if q:
        clauses.append("web_name LIKE ?")
        params.append(f"%{q}%")
    if category:
        clauses.append("category = ?")
        params.append(category)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with get_connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS c FROM products {where}", params).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM products {where} ORDER BY id LIMIT ? OFFSET ?", (*params, page_size, offset)
        ).fetchall()
        items = []
        for row in rows:
            d = row_to_dict(row)
            agg = conn.execute(
                "SELECT AVG(rating) AS avg_rating, COUNT(*) AS n FROM reviews WHERE product_id = ?", (d["id"],)
            ).fetchone()
            items.append(_serialize_product(d, agg["avg_rating"], agg["n"]))

    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.get("/{product_id}")
def get_product(product_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Product not found")
        d = row_to_dict(row)
        agg = conn.execute(
            "SELECT AVG(rating) AS avg_rating, COUNT(*) AS n FROM reviews WHERE product_id = ?", (product_id,)
        ).fetchone()
    return _serialize_product(d, agg["avg_rating"], agg["n"])


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
