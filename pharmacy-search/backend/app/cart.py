import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.db import get_connection, row_to_dict

router = APIRouter(prefix="/api/cart", tags=["cart"])


def _serialize_line(row: dict) -> dict:
    quantity = row["quantity"]
    price = row["price"]
    return {
        "product_id": row["product_id"],
        "webName": row["web_name"],
        "sku": row["sku"],
        "imageUrl": row["image_url"],
        "price": price,
        "price_unit": row["price_unit"],
        "price_is_estimated": bool(row["price_is_estimated"]),
        "currency": row["currency"],
        "stock": row["stock"],
        "quantity": quantity,
        "line_total": price * quantity,
        "saved_for_later": bool(row["saved_for_later"]),
        # Surfaced per line so the cart can mark which items are the reason
        # checkout will ask for a prescription.
        "prescription": bool(row["prescription"]) if row["prescription"] is not None else None,
    }


def _compute_discount(subtotal: int, code_row) -> int:
    if not code_row:
        return 0
    if code_row["kind"] == "percent":
        return (subtotal * code_row["value"]) // 100
    return min(code_row["value"], subtotal)


def _get_cart(conn, user_id: int) -> dict:
    # is_active = 1 matters: a soft-deleted product used to keep rendering in
    # the cart and counting toward the subtotal, and checkout then rejected the
    # whole order over a line the shopper could not see was the problem.
    rows = conn.execute(
        """SELECT cart_items.*, products.web_name, products.sku, products.price, products.price_unit,
                  products.price_is_estimated, products.currency, products.stock, products.image_url,
                  products.prescription
           FROM cart_items JOIN products ON products.id = cart_items.product_id
           WHERE cart_items.user_id = ? AND products.is_active = 1
           ORDER BY cart_items.added_at""",
        (user_id,),
    ).fetchall()

    lines = [_serialize_line(row_to_dict(r)) for r in rows]
    active = [l for l in lines if not l["saved_for_later"]]
    saved = [l for l in lines if l["saved_for_later"]]
    subtotal = sum(l["line_total"] for l in active)

    discount_row = conn.execute(
        """SELECT discount_codes.* FROM cart_discounts
           JOIN discount_codes ON discount_codes.code = cart_discounts.code
           WHERE cart_discounts.user_id = ? AND discount_codes.active = 1""",
        (user_id,),
    ).fetchone()
    discount_amount = _compute_discount(subtotal, discount_row)

    return {
        "items": active,
        "saved_for_later": saved,
        "subtotal": subtotal,
        "discount_code": discount_row["code"] if discount_row else None,
        "discount_amount": discount_amount,
        "total": subtotal - discount_amount,
        "currency": "VND",
        "requires_prescription": any(l["prescription"] for l in active),
        "prescription_items": [l["webName"] for l in active if l["prescription"]],
    }


@router.get("")
def get_cart(user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        return _get_cart(conn, user["id"])


class AddItemRequest(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1)


@router.post("/items", status_code=201)
def add_item(body: AddItemRequest, user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        product = conn.execute(
            "SELECT id, stock FROM products WHERE id = ? AND is_active = 1", (body.product_id,)
        ).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        if product["stock"] is not None and product["stock"] <= 0:
            raise HTTPException(status_code=400, detail="This product is out of stock")

        existing = conn.execute(
            "SELECT * FROM cart_items WHERE user_id = ? AND product_id = ?", (user["id"], body.product_id)
        ).fetchone()
        new_quantity = (existing["quantity"] if existing else 0) + body.quantity
        if product["stock"] is not None:
            new_quantity = min(new_quantity, product["stock"])

        if existing:
            conn.execute(
                "UPDATE cart_items SET quantity = ?, saved_for_later = 0 WHERE id = ?",
                (new_quantity, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO cart_items (user_id, product_id, quantity, saved_for_later, added_at) VALUES (?, ?, ?, 0, ?)",
                (user["id"], body.product_id, new_quantity, time.time()),
            )
        return _get_cart(conn, user["id"])


class UpdateQuantityRequest(BaseModel):
    quantity: int = Field(ge=1)


@router.put("/items/{product_id}")
def update_quantity(product_id: int, body: UpdateQuantityRequest, user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        item = conn.execute(
            "SELECT cart_items.*, products.stock FROM cart_items JOIN products ON products.id = cart_items.product_id "
            "WHERE cart_items.user_id = ? AND cart_items.product_id = ?",
            (user["id"], product_id),
        ).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Item not in cart")
        quantity = body.quantity
        if item["stock"] is not None:
            quantity = min(quantity, item["stock"])
        conn.execute("UPDATE cart_items SET quantity = ? WHERE id = ?", (quantity, item["id"]))
        return _get_cart(conn, user["id"])


@router.delete("/items/{product_id}")
def remove_item(product_id: int, user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        conn.execute("DELETE FROM cart_items WHERE user_id = ? AND product_id = ?", (user["id"], product_id))
        return _get_cart(conn, user["id"])


@router.post("/items/{product_id}/save-for-later")
def save_for_later(product_id: int, user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        item = conn.execute(
            "SELECT id FROM cart_items WHERE user_id = ? AND product_id = ?", (user["id"], product_id)
        ).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Item not in cart")
        conn.execute("UPDATE cart_items SET saved_for_later = 1 WHERE id = ?", (item["id"],))
        return _get_cart(conn, user["id"])


@router.post("/items/{product_id}/move-to-cart")
def move_to_cart(product_id: int, user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        item = conn.execute(
            "SELECT id FROM cart_items WHERE user_id = ? AND product_id = ?", (user["id"], product_id)
        ).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        conn.execute("UPDATE cart_items SET saved_for_later = 0 WHERE id = ?", (item["id"],))
        return _get_cart(conn, user["id"])


class DiscountRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)


@router.post("/discount")
def apply_discount(body: DiscountRequest, user: dict = Depends(get_current_user)):
    code = body.code.strip().upper()
    with get_connection() as conn:
        code_row = conn.execute(
            "SELECT * FROM discount_codes WHERE code = ? AND active = 1", (code,)
        ).fetchone()
        if not code_row:
            raise HTTPException(status_code=404, detail="That discount code isn't valid")
        conn.execute(
            "INSERT INTO cart_discounts (user_id, code) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET code = excluded.code",
            (user["id"], code),
        )
        return _get_cart(conn, user["id"])


@router.delete("/discount")
def remove_discount(user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        conn.execute("DELETE FROM cart_discounts WHERE user_id = ?", (user["id"],))
        return _get_cart(conn, user["id"])
