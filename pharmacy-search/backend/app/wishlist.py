import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_user
from app.db import get_connection, row_to_dict

router = APIRouter(prefix="/api/wishlist", tags=["wishlist"])


def _serialize(row: dict) -> dict:
    return {
        "product_id": row["product_id"],
        "webName": row["web_name"],
        "sku": row["sku"],
        "imageUrl": row["image_url"],
        "price": row["price"],
        "price_unit": row["price_unit"],
        "price_is_estimated": bool(row["price_is_estimated"]),
        "currency": row["currency"],
        "stock": row["stock"],
    }


def _get_wishlist(conn, user_id: int) -> list:
    rows = conn.execute(
        """SELECT wishlist_items.*, products.web_name, products.sku, products.price, products.price_unit,
                  products.price_is_estimated, products.currency, products.stock, products.image_url
           FROM wishlist_items JOIN products ON products.id = wishlist_items.product_id
           WHERE wishlist_items.user_id = ? ORDER BY wishlist_items.added_at DESC""",
        (user_id,),
    ).fetchall()
    return [_serialize(row_to_dict(r)) for r in rows]


@router.get("")
def list_wishlist(user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        return _get_wishlist(conn, user["id"])


class WishlistItemRequest(BaseModel):
    product_id: int


@router.post("", status_code=201)
def add_to_wishlist(body: WishlistItemRequest, user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        product = conn.execute("SELECT id FROM products WHERE id = ?", (body.product_id,)).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        conn.execute(
            "INSERT INTO wishlist_items (user_id, product_id, added_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, product_id) DO NOTHING",
            (user["id"], body.product_id, time.time()),
        )
        return _get_wishlist(conn, user["id"])


@router.delete("/{product_id}")
def remove_from_wishlist(product_id: int, user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        conn.execute("DELETE FROM wishlist_items WHERE user_id = ? AND product_id = ?", (user["id"], product_id))
        return _get_wishlist(conn, user["id"])


@router.post("/{product_id}/move-to-cart")
def move_to_cart(product_id: int, user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        item = conn.execute(
            "SELECT id FROM wishlist_items WHERE user_id = ? AND product_id = ?", (user["id"], product_id)
        ).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Item not in wishlist")
        product = conn.execute("SELECT id, stock FROM products WHERE id = ?", (product_id,)).fetchone()
        if product["stock"] is not None and product["stock"] <= 0:
            raise HTTPException(status_code=400, detail="This product is out of stock")

        existing_cart_item = conn.execute(
            "SELECT * FROM cart_items WHERE user_id = ? AND product_id = ?", (user["id"], product_id)
        ).fetchone()
        if existing_cart_item:
            new_quantity = existing_cart_item["quantity"] + 1
            if product["stock"] is not None:
                new_quantity = min(new_quantity, product["stock"])
            conn.execute(
                "UPDATE cart_items SET quantity = ?, saved_for_later = 0 WHERE id = ?",
                (new_quantity, existing_cart_item["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO cart_items (user_id, product_id, quantity, saved_for_later, added_at) VALUES (?, ?, 1, 0, ?)",
                (user["id"], product_id, time.time()),
            )
        conn.execute("DELETE FROM wishlist_items WHERE id = ?", (item["id"],))
        return _get_wishlist(conn, user["id"])
