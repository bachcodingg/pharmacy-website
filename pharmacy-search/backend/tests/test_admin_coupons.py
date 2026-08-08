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


def test_admin_coupons_requires_admin():
    r = client.get("/api/admin/coupons")
    assert r.status_code == 401


def test_seeded_coupons_are_listed():
    headers = _admin_headers()
    r = client.get("/api/admin/coupons", headers=headers)
    codes = [c["code"] for c in r.json()]
    assert "WELCOME10" in codes
    assert "SAVE20K" in codes


def test_create_percent_coupon():
    headers = _admin_headers()
    r = client.post("/api/admin/coupons", json={"code": "test15", "kind": "percent", "value": 15}, headers=headers)
    assert r.status_code == 201
    assert r.json()["code"] == "TEST15"  # normalized to uppercase


def test_create_coupon_rejects_percent_over_100():
    headers = _admin_headers()
    r = client.post("/api/admin/coupons", json={"code": "TOOBIG", "kind": "percent", "value": 150}, headers=headers)
    assert r.status_code == 400


def test_create_coupon_rejects_duplicate_code():
    headers = _admin_headers()
    client.post("/api/admin/coupons", json={"code": "DUPE1", "kind": "fixed", "value": 5000}, headers=headers)
    r = client.post("/api/admin/coupons", json={"code": "DUPE1", "kind": "fixed", "value": 9000}, headers=headers)
    assert r.status_code == 409


def test_deactivate_coupon_blocks_it_from_being_applied():
    headers = _admin_headers()
    client.post("/api/admin/coupons", json={"code": "TOGGLEME", "kind": "fixed", "value": 1000}, headers=headers)
    r = client.put("/api/admin/coupons/TOGGLEME", json={"active": False}, headers=headers)
    assert r.status_code == 200
    assert r.json()["active"] is False

    import uuid
    shopper_email = f"shopper-{uuid.uuid4().hex[:8]}@example.com"
    shopper = client.post("/api/auth/register", json={"email": shopper_email, "password": "correcthorse", "name": "Shopper"}).json()
    shopper_headers = {"Authorization": f"Bearer {shopper['token']}"}

    r = client.post("/api/cart/discount", json={"code": "TOGGLEME"}, headers=shopper_headers)
    assert r.status_code == 404
