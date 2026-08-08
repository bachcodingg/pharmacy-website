from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app

client = TestClient(app)


def _admin_headers():
    import uuid
    email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Admin"})
    with get_connection() as conn:
        conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _place_order():
    import uuid
    email = f"shopper-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Shopper"})
    headers = {"Authorization": f"Bearer {r.json()['token']}"}
    address = client.post("/api/auth/addresses", json={
        "label": "Home", "recipient_name": "Shopper", "phone": "0900000000",
        "line1": "1 Main St", "city": "HCMC", "is_default": True,
    }, headers=headers).json()
    product = next(p for p in client.get("/api/products", params={"in_stock": True, "page_size": 200}).json()["items"] if p["stock"] >= 1)
    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers)
    return client.post("/api/checkout/place-order", json={
        "address_id": address["id"], "shipping_method": "standard", "payment_method": "cod",
    }, headers=headers).json(), product


def test_reports_require_admin():
    r = client.get("/api/admin/reports/summary")
    assert r.status_code == 401


def test_summary_reflects_a_placed_order():
    headers = _admin_headers()
    before = client.get("/api/admin/reports/summary", headers=headers).json()

    order, _ = _place_order()

    after = client.get("/api/admin/reports/summary", headers=headers).json()
    assert after["order_count"] == before["order_count"] + 1
    assert after["revenue"] == before["revenue"] + order["total"]


def test_pending_payment_order_excluded_from_revenue():
    headers = _admin_headers()
    import uuid
    email = f"shopper-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Shopper"})
    shopper_headers = {"Authorization": f"Bearer {r.json()['token']}"}
    address = client.post("/api/auth/addresses", json={
        "label": "Home", "recipient_name": "Shopper", "phone": "0900000000",
        "line1": "1 Main St", "city": "HCMC", "is_default": True,
    }, headers=shopper_headers).json()
    product = next(p for p in client.get("/api/products", params={"in_stock": True, "page_size": 200}).json()["items"] if p["stock"] >= 1)
    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=shopper_headers)

    before = client.get("/api/admin/reports/summary", headers=headers).json()
    client.post("/api/checkout/place-order", json={
        "address_id": address["id"], "shipping_method": "standard", "payment_method": "vnpay",
    }, headers=shopper_headers)
    after = client.get("/api/admin/reports/summary", headers=headers).json()

    assert after["revenue"] == before["revenue"]  # unconnected payment method - no real revenue
    assert after["pending_payment_count"] == before["pending_payment_count"] + 1


def test_sales_by_day_includes_todays_order():
    headers = _admin_headers()
    order, _ = _place_order()

    r = client.get("/api/admin/reports/sales-by-day", params={"days": 7}, headers=headers)
    assert r.status_code == 200
    total = sum(day["revenue"] for day in r.json())
    assert total >= order["total"]


def test_top_products_reflects_purchase():
    headers = _admin_headers()
    order, product = _place_order()

    r = client.get("/api/admin/reports/top-products", headers=headers)
    assert r.status_code == 200
    assert any(p["webName"] == product["webName"] for p in r.json())
