from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_admin
from app.checkout import _serialize_order
from app.db import get_connection, row_to_dict

router = APIRouter(prefix="/api/admin/orders", tags=["admin-orders"])

ALLOWED_STATUSES = {"placed", "pending_payment", "shipped", "delivered", "cancelled"}


@router.get("")
def list_orders(status: str = "", admin: dict = Depends(get_current_admin)):
    clauses = []
    params: list = []
    if status:
        clauses.append("o.status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with get_connection() as conn:
        rows = conn.execute(
            f"""SELECT o.*, users.name AS customer_name, users.email AS customer_email
                FROM orders o JOIN users ON users.id = o.user_id
                {where} ORDER BY o.created_at DESC""",
            params,
        ).fetchall()
        result = []
        for row in rows:
            d = row_to_dict(row)
            order = _serialize_order(conn, d)
            order["customer_name"] = d["customer_name"]
            order["customer_email"] = d["customer_email"]
            result.append(order)
    return result


class UpdateStatusRequest(BaseModel):
    status: str


@router.put("/{order_id}/status")
def update_order_status(order_id: int, body: UpdateStatusRequest, admin: dict = Depends(get_current_admin)):
    if body.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail=f"Status must be one of {sorted(ALLOWED_STATUSES)}")
    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Order not found")
        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (body.status, order_id))
        row = conn.execute(
            """SELECT o.*, users.name AS customer_name, users.email AS customer_email
               FROM orders o JOIN users ON users.id = o.user_id WHERE o.id = ?""",
            (order_id,),
        ).fetchone()
        d = row_to_dict(row)
        order = _serialize_order(conn, d)
        order["customer_name"] = d["customer_name"]
        order["customer_email"] = d["customer_email"]
    return order
