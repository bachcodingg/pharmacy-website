"""Stock accounting under interleaved checkouts and cancellations.

place_order used to read stock, validate it, then decrement unconditionally.
Two orders that interleaved between the read and the write both passed
validation and both subtracted - stock went negative and inventory that did
not exist had been sold."""

import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app

client = TestClient(app)


def _buyer():
    email = f"race-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Buyer"})
    headers = {"Authorization": f"Bearer {r.json()['token']}"}
    client.post("/api/auth/addresses", json={
        "label": "Home", "recipient_name": "Buyer", "phone": "0900000000",
        "line1": "1 Main St", "city": "Ho Chi Minh City", "is_default": True,
    }, headers=headers)
    return headers


def _admin():
    email = f"adm-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Admin"})
    with get_connection() as conn:
        conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _fresh_product(stock: int):
    """A product created for this test only, so a shared catalogue row being
    bought by another test cannot make this one flap."""
    admin = _admin()
    r = client.post("/api/admin/products", json={
        "webName": f"Test Product {uuid.uuid4().hex[:6]}",
        "category": "cham-soc-ca-nhan", "price": 50000, "stock": stock,
    }, headers=admin)
    return r.json()["id"]


def _place(headers, product_id, quantity=1):
    client.post("/api/cart/items", json={"product_id": product_id, "quantity": quantity}, headers=headers)
    address_id = client.get("/api/auth/addresses", headers=headers).json()[0]["id"]
    return client.post("/api/checkout/place-order", json={
        "address_id": address_id, "shipping_method": "standard", "payment_method": "cod",
    }, headers=headers)


def test_one_unit_cannot_be_sold_twice_concurrently():
    product_id = _fresh_product(stock=1)
    buyers = [_buyer() for _ in range(6)]
    # Every buyer has the single remaining unit in their cart before any of
    # them checks out - the exact interleaving the old code got wrong.
    for headers in buyers:
        client.post("/api/cart/items", json={"product_id": product_id, "quantity": 1}, headers=headers)

    def checkout(headers):
        address_id = client.get("/api/auth/addresses", headers=headers).json()[0]["id"]
        return client.post("/api/checkout/place-order", json={
            "address_id": address_id, "shipping_method": "standard", "payment_method": "cod",
        }, headers=headers).status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        codes = list(pool.map(checkout, buyers))

    assert codes.count(201) == 1, f"expected exactly one sale, got {codes}"
    assert all(c in (201, 409) for c in codes), codes
    assert client.get(f"/api/products/{product_id}").json()["stock"] == 0


def test_stock_never_goes_negative_under_load():
    product_id = _fresh_product(stock=3)
    buyers = [_buyer() for _ in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda h: _place(h, product_id).status_code, buyers))

    stock = client.get(f"/api/products/{product_id}").json()["stock"]
    assert stock >= 0
    assert stock == 3 - codes.count(201)


def test_cancelling_an_order_returns_its_stock():
    product_id = _fresh_product(stock=10)
    headers = _buyer()
    order = _place(headers, product_id, quantity=3).json()
    assert client.get(f"/api/products/{product_id}").json()["stock"] == 7

    admin = _admin()
    r = client.put(f"/api/admin/orders/{order['id']}/status", json={"status": "cancelled"}, headers=admin)
    assert r.status_code == 200
    assert client.get(f"/api/products/{product_id}").json()["stock"] == 10


def test_cancelling_twice_does_not_return_stock_twice():
    product_id = _fresh_product(stock=10)
    headers = _buyer()
    order = _place(headers, product_id, quantity=2).json()
    admin = _admin()
    client.put(f"/api/admin/orders/{order['id']}/status", json={"status": "cancelled"}, headers=admin)
    r = client.put(f"/api/admin/orders/{order['id']}/status", json={"status": "cancelled"}, headers=admin)
    assert r.status_code == 200  # idempotent, not a second credit
    assert client.get(f"/api/products/{product_id}").json()["stock"] == 10


def test_delivered_orders_cannot_walk_backwards():
    product_id = _fresh_product(stock=5)
    headers = _buyer()
    order = _place(headers, product_id).json()
    admin = _admin()
    client.put(f"/api/admin/orders/{order['id']}/status", json={"status": "shipped"}, headers=admin)
    client.put(f"/api/admin/orders/{order['id']}/status", json={"status": "delivered"}, headers=admin)
    r = client.put(f"/api/admin/orders/{order['id']}/status", json={"status": "pending_payment"}, headers=admin)
    assert r.status_code == 409


def test_status_changes_are_audited():
    product_id = _fresh_product(stock=5)
    headers = _buyer()
    order = _place(headers, product_id).json()
    admin = _admin()
    client.put(f"/api/admin/orders/{order['id']}/status", json={"status": "shipped"}, headers=admin)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT detail_json FROM admin_audit_log WHERE entity = 'order' AND entity_id = ? "
            "AND action = 'order_status_change'",
            (str(order["id"]),),
        ).fetchone()
    assert row is not None and "shipped" in row["detail_json"]
