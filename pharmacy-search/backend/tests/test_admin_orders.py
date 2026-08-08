from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app

client = TestClient(app)


def _admin_headers():
    import uuid
    email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Admin"})
    token = r.json()["token"]
    with get_connection() as conn:
        conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _shopper_with_order():
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
    order = client.post("/api/checkout/place-order", json={
        "address_id": address["id"], "shipping_method": "standard", "payment_method": "cod",
    }, headers=headers).json()
    return headers, order


def test_admin_orders_requires_admin():
    r = client.get("/api/admin/orders")
    assert r.status_code == 401


def test_list_all_orders_includes_customer_info():
    admin_headers = _admin_headers()
    _, order = _shopper_with_order()

    r = client.get("/api/admin/orders", headers=admin_headers)
    assert r.status_code == 200
    match = next(o for o in r.json() if o["id"] == order["id"])
    assert match["customer_email"]
    assert match["customer_name"]


def test_filter_orders_by_status():
    admin_headers = _admin_headers()
    _, order = _shopper_with_order()

    r = client.get("/api/admin/orders", params={"status": "placed"}, headers=admin_headers)
    assert any(o["id"] == order["id"] for o in r.json())

    r = client.get("/api/admin/orders", params={"status": "cancelled"}, headers=admin_headers)
    assert not any(o["id"] == order["id"] for o in r.json())


def test_update_order_status():
    admin_headers = _admin_headers()
    _, order = _shopper_with_order()

    r = client.put(f"/api/admin/orders/{order['id']}/status", json={"status": "shipped"}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "shipped"


def test_update_order_status_rejects_unknown_status():
    admin_headers = _admin_headers()
    _, order = _shopper_with_order()

    r = client.put(f"/api/admin/orders/{order['id']}/status", json={"status": "teleported"}, headers=admin_headers)
    assert r.status_code == 400


def test_nonadmin_cannot_update_order_status():
    shopper_headers, order = _shopper_with_order()
    r = client.put(f"/api/admin/orders/{order['id']}/status", json={"status": "shipped"}, headers=shopper_headers)
    assert r.status_code == 403
