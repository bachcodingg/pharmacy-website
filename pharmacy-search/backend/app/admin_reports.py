import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from app.auth import get_current_admin
from app.db import get_connection

router = APIRouter(prefix="/api/admin/reports", tags=["admin-reports"])

# Only orders that actually completed count as revenue. pending_payment orders
# picked a payment method that isn't connected to anything (see checkout.py) -
# counting them as sales would overstate revenue with money that was never
# collected. cancelled orders are excluded for the same reason.
REVENUE_STATUSES = ("placed", "shipped", "delivered")


@router.get("/summary")
def summary(admin: dict = Depends(get_current_admin)):
    placeholders = ",".join("?" for _ in REVENUE_STATUSES)
    with get_connection() as conn:
        revenue_row = conn.execute(
            f"""SELECT COALESCE(SUM(total), 0) AS revenue, COUNT(*) AS order_count
                FROM orders WHERE status IN ({placeholders})""",
            REVENUE_STATUSES,
        ).fetchone()
        customer_count = conn.execute(
            f"""SELECT COUNT(DISTINCT user_id) AS c FROM orders WHERE status IN ({placeholders})""",
            REVENUE_STATUSES,
        ).fetchone()["c"]
        user_count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        low_stock_count = conn.execute(
            "SELECT COUNT(*) AS c FROM products WHERE is_active = 1 AND stock <= 10"
        ).fetchone()["c"]
        pending_payment_count = conn.execute(
            "SELECT COUNT(*) AS c FROM orders WHERE status = 'pending_payment'"
        ).fetchone()["c"]

    candidates_path = _candidates_path()
    pending_corrections = 0
    if candidates_path.exists():
        candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
        pending_corrections = sum(1 for c in candidates if c.get("status") == "pending" and c.get("meets_threshold"))

    order_count = revenue_row["order_count"]
    revenue = revenue_row["revenue"]
    return {
        "revenue": revenue,
        "order_count": order_count,
        "avg_order_value": round(revenue / order_count) if order_count else 0,
        "customer_count": customer_count,
        "user_count": user_count,
        "low_stock_count": low_stock_count,
        "pending_payment_count": pending_payment_count,
        "pending_corrections_count": pending_corrections,
    }


@router.get("/sales-by-day")
def sales_by_day(days: int = 14, admin: dict = Depends(get_current_admin)):
    days = min(max(days, 1), 90)
    placeholders = ",".join("?" for _ in REVENUE_STATUSES)

    # Bucket by actual UTC calendar date, not by raw elapsed-seconds offset from
    # now - the latter drifts away from midnight boundaries by whatever the
    # current time-of-day happens to be, and "today" ends up not corresponding
    # to any bucket at all.
    today = datetime.now(timezone.utc).date()
    first_day = today - timedelta(days=days - 1)
    start_ts = datetime.combine(first_day, datetime.min.time(), tzinfo=timezone.utc).timestamp()

    with get_connection() as conn:
        rows = conn.execute(
            f"""SELECT created_at, total FROM orders
                WHERE status IN ({placeholders}) AND created_at >= ?""",
            (*REVENUE_STATUSES, start_ts),
        ).fetchall()

    buckets = {}
    for i in range(days):
        label = (first_day + timedelta(days=i)).isoformat()
        buckets[label] = 0

    for row in rows:
        label = datetime.fromtimestamp(row["created_at"], tz=timezone.utc).date().isoformat()
        if label in buckets:
            buckets[label] += row["total"]

    return [{"date": date, "revenue": revenue} for date, revenue in sorted(buckets.items())]


@router.get("/top-products")
def top_products(limit: int = 10, admin: dict = Depends(get_current_admin)):
    placeholders = ",".join("?" for _ in REVENUE_STATUSES)
    with get_connection() as conn:
        rows = conn.execute(
            f"""SELECT order_items.web_name, SUM(order_items.quantity) AS units_sold,
                       SUM(order_items.line_total) AS revenue
                FROM order_items
                JOIN orders ON orders.id = order_items.order_id
                WHERE orders.status IN ({placeholders})
                GROUP BY order_items.product_id
                ORDER BY revenue DESC
                LIMIT ?""",
            (*REVENUE_STATUSES, limit),
        ).fetchall()
    return [{"webName": r["web_name"], "units_sold": r["units_sold"], "revenue": r["revenue"]} for r in rows]


def _candidates_path():
    from pathlib import Path
    return Path(__file__).resolve().parents[1] / "learning" / "candidate_pairs.json"
