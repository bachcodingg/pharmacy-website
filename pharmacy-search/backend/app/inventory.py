import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_admin
from app.corrector import search_key
from app.db import get_connection, row_to_dict

router = APIRouter(prefix="/api/admin/products", tags=["inventory"])


def _serialize(row: dict) -> dict:
    return {
        "id": row["id"],
        "sku": row["sku"],
        "webName": row["web_name"],
        "shortDescription": row["short_description"],
        "category": row["category"],
        "brand": row["brand"],
        "price": row["price"],
        "price_unit": row["price_unit"],
        "currency": row["currency"],
        "stock": row["stock"],
        "is_active": bool(row["is_active"]),
        "ingredients": json.loads(row["ingredients_json"] or "[]"),
    }


@router.get("")
def list_products(low_stock_threshold: int | None = None, include_inactive: bool = False, admin: dict = Depends(get_current_admin)):
    clauses = []
    params: list = []
    if not include_inactive:
        clauses.append("is_active = 1")
    if low_stock_threshold is not None:
        clauses.append("stock <= ?")
        params.append(low_stock_threshold)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with get_connection() as conn:
        rows = conn.execute(f"SELECT * FROM products {where} ORDER BY stock ASC, web_name", params).fetchall()
    return [_serialize(row_to_dict(r)) for r in rows]


class CreateProductRequest(BaseModel):
    webName: str
    category: str | None = None
    brand: str | None = None
    shortDescription: str | None = None
    price: int
    price_unit: str | None = None
    stock: int = 0


@router.post("", status_code=201)
def create_product(body: CreateProductRequest, admin: dict = Depends(get_current_admin)):
    sku = _next_manual_sku()
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO products
            (sku, web_name, search_text, short_description, category, brand, brand_is_estimated,
             ingredients_json, price, price_unit, currency, price_is_estimated, stock, stock_is_estimated, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 0, '[]', ?, ?, 'VND', 0, ?, 0, 1)""",
            (sku, body.webName, search_key(body.webName), body.shortDescription, body.category, body.brand,
             body.price, body.price_unit, body.stock),
        )
        row = conn.execute("SELECT * FROM products WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _serialize(row_to_dict(row))


class UpdateProductRequest(BaseModel):
    webName: str | None = None
    category: str | None = None
    brand: str | None = None
    shortDescription: str | None = None
    price: int | None = None
    price_unit: str | None = None


FIELD_MAP = {
    "webName": "web_name",
    "category": "category",
    "brand": "brand",
    "shortDescription": "short_description",
    "price": "price",
    "price_unit": "price_unit",
}


@router.put("/{product_id}")
def update_product(product_id: int, body: UpdateProductRequest, admin: dict = Depends(get_current_admin)):
    updates = {FIELD_MAP[k]: v for k, v in body.model_dump(exclude_unset=True).items()}
    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Product not found")
        if updates:
            # A manual edit overrides whatever crawl-derived price this product had -
            # it's no longer a placeholder once an admin has set it deliberately.
            if "price" in updates:
                updates["price_is_estimated"] = 0
            # search_text is derived from web_name, so it has to be rewritten
            # with it or the product stops answering to its own new name.
            if "web_name" in updates:
                updates["search_text"] = search_key(updates["web_name"])
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(f"UPDATE products SET {set_clause} WHERE id = ?", (*updates.values(), product_id))
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    return _serialize(row_to_dict(row))


class UpdateStockRequest(BaseModel):
    stock: int


@router.put("/{product_id}/stock")
def update_stock(product_id: int, body: UpdateStockRequest, admin: dict = Depends(get_current_admin)):
    if body.stock < 0:
        raise HTTPException(status_code=400, detail="Stock can't be negative")
    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Product not found")
        conn.execute("UPDATE products SET stock = ?, stock_is_estimated = 0 WHERE id = ?", (body.stock, product_id))
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    return _serialize(row_to_dict(row))


@router.delete("/{product_id}")
def deactivate_product(product_id: int, admin: dict = Depends(get_current_admin)):
    """Soft-delete only. Orders already placed reference this product_id by
    foreign key (order_items, reviews, cart_items) - hard-deleting the row
    would either break that history or require cascading deletes that quietly
    erase a customer's past order. Deactivating hides it from the catalog
    without touching anything that already points to it."""
    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Product not found")
        conn.execute("UPDATE products SET is_active = 0 WHERE id = ?", (product_id,))
    return {"status": "deactivated"}


@router.post("/{product_id}/reactivate")
def reactivate_product(product_id: int, admin: dict = Depends(get_current_admin)):
    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Product not found")
        conn.execute("UPDATE products SET is_active = 1 WHERE id = ?", (product_id,))
    return {"status": "activated"}


def _next_manual_sku() -> str:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT sku FROM products WHERE sku LIKE 'MANUAL-%' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    next_n = int(row["sku"].split("-")[1]) + 1 if row else 1
    return f"MANUAL-{next_n:05d}"
