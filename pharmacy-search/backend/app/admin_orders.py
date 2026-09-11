from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import get_current_admin
from app.checkout import STATUS_AWAITING_PRESCRIPTION, _serialize_order
from app.db import get_connection, record_admin_action, row_to_dict, write_transaction

router = APIRouter(prefix="/api/admin/orders", tags=["admin-orders"])

ALLOWED_STATUSES = {
    "placed",
    "pending_payment",
    STATUS_AWAITING_PRESCRIPTION,
    "shipped",
    "delivered",
    "cancelled",
}

# Status used to be a free-form assignment from the allowed set, so an order
# could go from delivered back to pending_payment, or straight from
# awaiting_prescription to shipped - dispensing an Rx medicine that no
# pharmacist had approved. The lifecycle is now explicit.
STATUS_TRANSITIONS: dict[str, set[str]] = {
    "pending_payment": {"placed", "cancelled"},
    STATUS_AWAITING_PRESCRIPTION: {"cancelled"},  # only the prescription review can clear this
    "placed": {"shipped", "cancelled"},
    "shipped": {"delivered", "cancelled"},
    "delivered": set(),
    "cancelled": set(),
}

# Once an order leaves these states its stock has already been returned, so a
# later transition must not return it twice.
STOCK_HELD_STATUSES = {"placed", "pending_payment", STATUS_AWAITING_PRESCRIPTION, "shipped"}


def _restore_stock(conn, order_id: int) -> None:
    """Put an order's units back into inventory.

    Cancelling used to just rewrite the status. The stock that checkout
    decremented stayed decremented, so every cancellation quietly destroyed
    inventory that was never sold."""
    for item in conn.execute(
        "SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order_id,)
    ).fetchall():
        conn.execute(
            "UPDATE products SET stock = COALESCE(stock, 0) + ? WHERE id = ?",
            (item["quantity"], item["product_id"]),
        )


def _load_order(conn, order_id: int) -> dict:
    row = conn.execute(
        """SELECT o.*, users.name AS customer_name, users.email AS customer_email
           FROM orders o JOIN users ON users.id = o.user_id WHERE o.id = ?""",
        (order_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Order not found")
    d = row_to_dict(row)
    order = _serialize_order(conn, d)
    order["customer_name"] = d["customer_name"]
    order["customer_email"] = d["customer_email"]
    return order


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
    with write_transaction() as conn:
        existing = conn.execute("SELECT id, status FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Order not found")
        current = existing["status"]
        if body.status == current:
            return _load_order(conn, order_id)
        allowed = STATUS_TRANSITIONS.get(current, set())
        if body.status not in allowed:
            detail = f"An order in '{current}' cannot move to '{body.status}'"
            if current == STATUS_AWAITING_PRESCRIPTION:
                detail += " - approve the prescription first"
            raise HTTPException(status_code=409, detail=detail)

        if body.status == "cancelled" and current in STOCK_HELD_STATUSES:
            _restore_stock(conn, order_id)

        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (body.status, order_id))
        record_admin_action(conn, admin["id"], "order_status_change", "order", order_id,
                            {"from": current, "to": body.status})
        return _load_order(conn, order_id)


class PrescriptionDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    note: str | None = Field(default=None, max_length=500)


@router.put("/{order_id}/prescription")
def review_prescription(order_id: int, body: PrescriptionDecisionRequest, admin: dict = Depends(get_current_admin)):
    """The pharmacist review gate for prescription-only medicines.

    Approving releases the order into the normal flow; rejecting cancels it
    and returns the stock. Both are recorded in admin_audit_log against the
    reviewing account, because "who approved dispensing this" is a question a
    pharmacy has to be able to answer later."""
    with write_transaction() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Order not found")
        if not row["requires_prescription"]:
            raise HTTPException(status_code=400, detail="This order has no prescription items to review")
        if row["prescription_status"] != "pending_review":
            raise HTTPException(
                status_code=409,
                detail=f"This prescription was already {row['prescription_status']}",
            )

        if body.decision == "approve":
            new_status = "placed" if row["payment_method"] == "cod" else "pending_payment"
            conn.execute(
                "UPDATE orders SET prescription_status = 'approved', status = ? WHERE id = ?",
                (new_status, order_id),
            )
        else:
            _restore_stock(conn, order_id)
            conn.execute(
                "UPDATE orders SET prescription_status = 'rejected', status = 'cancelled' WHERE id = ?",
                (order_id,),
            )
        record_admin_action(conn, admin["id"], f"prescription_{body.decision}", "order", order_id,
                            {"note": body.note, "reference": row["prescription_reference"]})
        return _load_order(conn, order_id)
