import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_user
from app.cart import _get_cart
from app.db import get_connection, row_to_dict

router = APIRouter(prefix="/api/checkout", tags=["checkout"])

SHIPPING_METHODS = {
    "standard": {"label": "Standard (3-5 days)", "fee": 0},
    "express": {"label": "Express (1-2 days)", "fee": 30000},
}

# Only COD is real. The others are shown so the checkout flow looks and feels
# complete, but selecting one does not charge anyone or contact any payment
# processor - there is no VNPay/Momo/Stripe integration wired up. Building a
# card-entry form here would be actively wrong: real payment processing
# should go through one of those processors, not be simulated in-house.
PAYMENT_METHODS = {
    "cod": {"label": "Cash on delivery", "available": True},
    "vnpay": {"label": "VNPay", "available": False},
    "momo": {"label": "Momo", "available": False},
}


@router.get("/options")
def get_options():
    return {"shipping_methods": SHIPPING_METHODS, "payment_methods": PAYMENT_METHODS}


def _serialize_order(conn, order_row: dict) -> dict:
    items = conn.execute(
        "SELECT * FROM order_items WHERE order_id = ?", (order_row["id"],)
    ).fetchall()
    return {
        "id": order_row["id"],
        "status": order_row["status"],
        "shipping_method": order_row["shipping_method"],
        "shipping_fee": order_row["shipping_fee"],
        "payment_method": order_row["payment_method"],
        "subtotal": order_row["subtotal"],
        "discount_code": order_row["discount_code"],
        "discount_amount": order_row["discount_amount"],
        "total": order_row["total"],
        "created_at": order_row["created_at"],
        "items": [
            {
                "product_id": i["product_id"],
                "webName": i["web_name"],
                "quantity": i["quantity"],
                "unit_price": i["unit_price"],
                "price_was_estimated": bool(i["price_was_estimated"]),
                "line_total": i["line_total"],
            }
            for i in items
        ],
    }


@router.get("/orders")
def list_orders(user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC", (user["id"],)
        ).fetchall()
        return [_serialize_order(conn, row_to_dict(r)) for r in rows]


@router.get("/orders/{order_id}")
def get_order(order_id: int, user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, user["id"])
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Order not found")
        return _serialize_order(conn, row_to_dict(row))


class PlaceOrderRequest(BaseModel):
    address_id: int
    shipping_method: str
    payment_method: str


@router.post("/place-order", status_code=201)
def place_order(body: PlaceOrderRequest, user: dict = Depends(get_current_user)):
    if body.shipping_method not in SHIPPING_METHODS:
        raise HTTPException(status_code=400, detail="Unknown shipping method")
    if body.payment_method not in PAYMENT_METHODS:
        raise HTTPException(status_code=400, detail="Unknown payment method")

    with get_connection() as conn:
        address = conn.execute(
            "SELECT id FROM addresses WHERE id = ? AND user_id = ?", (body.address_id, user["id"])
        ).fetchone()
        if not address:
            raise HTTPException(status_code=404, detail="Shipping address not found")

        cart = _get_cart(conn, user["id"])
        if not cart["items"]:
            raise HTTPException(status_code=400, detail="Your cart is empty")

        # Stock can have moved since items were added to the cart - re-check
        # against current stock right before committing to an order, not just
        # whatever was true when the item was added.
        for line in cart["items"]:
            product = conn.execute("SELECT stock, is_active FROM products WHERE id = ?", (line["product_id"],)).fetchone()
            if not product or not product["is_active"]:
                raise HTTPException(status_code=409, detail=f"{line['webName']} is no longer available")
            if product["stock"] < line["quantity"]:
                raise HTTPException(
                    status_code=409,
                    detail=f"Only {product['stock']} left of {line['webName']} - update your cart quantity",
                )

        shipping_fee = SHIPPING_METHODS[body.shipping_method]["fee"]
        subtotal = cart["subtotal"]
        discount_amount = cart["discount_amount"]
        total = subtotal - discount_amount + shipping_fee
        status = "placed" if body.payment_method == "cod" else "pending_payment"
        now = time.time()

        cursor = conn.execute(
            """INSERT INTO orders
            (user_id, address_id, shipping_method, shipping_fee, payment_method,
             subtotal, discount_code, discount_amount, total, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user["id"], body.address_id, body.shipping_method, shipping_fee, body.payment_method,
                subtotal, cart["discount_code"], discount_amount, total, status, now,
            ),
        )
        order_id = cursor.lastrowid

        for line in cart["items"]:
            conn.execute(
                """INSERT INTO order_items (order_id, product_id, web_name, quantity, unit_price, price_was_estimated, line_total)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (order_id, line["product_id"], line["webName"], line["quantity"], line["price"],
                 int(line["price_is_estimated"]), line["line_total"]),
            )
            conn.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (line["quantity"], line["product_id"]))
            conn.execute("DELETE FROM cart_items WHERE user_id = ? AND product_id = ?", (user["id"], line["product_id"]))

        conn.execute("DELETE FROM cart_discounts WHERE user_id = ?", (user["id"],))

        order_row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        return _serialize_order(conn, row_to_dict(order_row))
