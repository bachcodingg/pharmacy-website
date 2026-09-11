"""Prescription-only medicines cannot be bought like shampoo.

389 of the 1,894 crawled products carry "prescription": true. Nothing in the
cart or checkout path read that flag: an Rx medicine went from cart to
'placed' with no pharmacist involved at any point. These tests pin the hold
that now sits in the way."""

import uuid

from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app

client = TestClient(app)


def _headers(name="Buyer"):
    email = f"rx-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": name})
    return {"Authorization": f"Bearer {r.json()['token']}"}, email


def _admin_headers():
    headers, email = _headers("Pharmacist")
    with get_connection() as conn:
        conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
    return headers


def _address(headers):
    r = client.post("/api/auth/addresses", json={
        "label": "Home", "recipient_name": "Buyer", "phone": "0900000000",
        "line1": "123 Main St", "city": "Ho Chi Minh City", "is_default": True,
    }, headers=headers)
    return r.json()["id"]


def _product(prescription: bool, min_stock=2):
    data = client.get("/api/products", params={"in_stock": True, "page_size": 200}).json()
    return next(p for p in data["items"] if p["stock"] >= min_stock and bool(p["prescription"]) is prescription)


def _order_rx(headers, quantity=1, reference="RX-2026-0001"):
    address_id = _address(headers)
    product = _product(True)
    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": quantity}, headers=headers)
    body = {"address_id": address_id, "shipping_method": "standard", "payment_method": "cod"}
    if reference is not None:
        body["prescription_reference"] = reference
    return client.post("/api/checkout/place-order", json=body, headers=headers), product


def test_cart_flags_prescription_items():
    headers, _ = _headers()
    product = _product(True)
    r = client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers)
    cart = r.json()
    assert cart["requires_prescription"] is True
    assert product["webName"] in cart["prescription_items"]
    assert cart["items"][0]["prescription"] is True


def test_otc_cart_does_not_require_a_prescription():
    headers, _ = _headers()
    product = _product(False)
    r = client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers)
    assert r.json()["requires_prescription"] is False


def test_rx_order_without_a_prescription_reference_is_refused():
    headers, _ = _headers()
    r, product = _order_rx(headers, reference=None)
    assert r.status_code == 400
    assert product["webName"] in r.json()["detail"]["prescription_items"]


def test_rx_order_is_held_for_review_not_placed():
    headers, _ = _headers()
    r, _ = _order_rx(headers)
    assert r.status_code == 201
    order = r.json()
    assert order["status"] == "awaiting_prescription"
    assert order["requires_prescription"] is True
    assert order["prescription_status"] == "pending_review"


def test_held_order_cannot_be_shipped_without_review():
    headers, _ = _headers()
    order = _order_rx(headers)[0].json()
    admin = _admin_headers()
    r = client.put(f"/api/admin/orders/{order['id']}/status", json={"status": "shipped"}, headers=admin)
    assert r.status_code == 409
    assert "prescription" in r.json()["detail"]


def test_pharmacist_approval_releases_the_order():
    headers, _ = _headers()
    order = _order_rx(headers)[0].json()
    admin = _admin_headers()

    r = client.put(f"/api/admin/orders/{order['id']}/prescription",
                   json={"decision": "approve", "note": "Checked against clinic record"}, headers=admin)
    assert r.status_code == 200
    assert r.json()["prescription_status"] == "approved"
    assert r.json()["status"] == "placed"

    r = client.put(f"/api/admin/orders/{order['id']}/status", json={"status": "shipped"}, headers=admin)
    assert r.status_code == 200


def test_pharmacist_rejection_cancels_and_returns_stock():
    headers, _ = _headers()
    r, product = _order_rx(headers, quantity=2)
    order = r.json()
    after_order = client.get(f"/api/products/{product['id']}").json()["stock"]

    admin = _admin_headers()
    r = client.put(f"/api/admin/orders/{order['id']}/prescription",
                   json={"decision": "reject"}, headers=admin)
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    assert r.json()["prescription_status"] == "rejected"

    restored = client.get(f"/api/products/{product['id']}").json()["stock"]
    assert restored == after_order + 2


def test_a_prescription_is_reviewed_once():
    headers, _ = _headers()
    order = _order_rx(headers)[0].json()
    admin = _admin_headers()
    client.put(f"/api/admin/orders/{order['id']}/prescription", json={"decision": "approve"}, headers=admin)
    r = client.put(f"/api/admin/orders/{order['id']}/prescription", json={"decision": "reject"}, headers=admin)
    assert r.status_code == 409


def test_prescription_review_requires_admin():
    headers, _ = _headers()
    order = _order_rx(headers)[0].json()
    r = client.put(f"/api/admin/orders/{order['id']}/prescription", json={"decision": "approve"}, headers=headers)
    assert r.status_code == 403


def test_review_decision_is_recorded_against_the_reviewing_account():
    headers, _ = _headers()
    order = _order_rx(headers)[0].json()
    admin = _admin_headers()
    client.put(f"/api/admin/orders/{order['id']}/prescription", json={"decision": "approve"}, headers=admin)

    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM admin_audit_log WHERE entity = 'order' AND entity_id = ? AND action = 'prescription_approve'",
            (str(order["id"]),),
        ).fetchone()
    assert row is not None
    assert row["admin_user_id"]
