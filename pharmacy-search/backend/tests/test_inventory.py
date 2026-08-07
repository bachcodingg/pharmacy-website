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
    return {"Authorization": f"Bearer {token}"}


def _regular_headers():
    import uuid
    email = f"shopper-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Shopper"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_admin_endpoints_require_admin_not_just_auth():
    headers = _regular_headers()
    r = client.get("/api/admin/products", headers=headers)
    assert r.status_code == 403


def test_admin_endpoints_require_auth_at_all():
    r = client.get("/api/admin/products")
    assert r.status_code == 401


def test_create_product():
    headers = _admin_headers()
    r = client.post("/api/admin/products", json={
        "webName": "Test Product For Inventory", "category": "thuoc", "brand": "TestBrand",
        "price": 42000, "stock": 15,
    }, headers=headers)
    assert r.status_code == 201
    body = r.json()
    assert body["webName"] == "Test Product For Inventory"
    assert body["stock"] == 15
    assert body["sku"].startswith("MANUAL-")

    # New product shows up in the public catalog immediately.
    listed = client.get("/api/products", params={"q": "Test Product For Inventory"}).json()
    assert listed["total"] == 1


def test_update_product_fields():
    headers = _admin_headers()
    created = client.post("/api/admin/products", json={"webName": "Editable Product", "price": 10000, "stock": 5}, headers=headers).json()

    r = client.put(f"/api/admin/products/{created['id']}", json={"price": 25000, "brand": "NewBrand"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["price"] == 25000
    assert r.json()["brand"] == "NewBrand"

    # Public catalog should no longer flag this as an estimated price.
    public = client.get(f"/api/products/{created['id']}").json()
    assert public["price_is_estimated"] is False


def test_update_stock():
    headers = _admin_headers()
    created = client.post("/api/admin/products", json={"webName": "Stock Test Product", "price": 5000, "stock": 3}, headers=headers).json()

    r = client.put(f"/api/admin/products/{created['id']}/stock", json={"stock": 100}, headers=headers)
    assert r.status_code == 200
    assert r.json()["stock"] == 100


def test_update_stock_rejects_negative():
    headers = _admin_headers()
    created = client.post("/api/admin/products", json={"webName": "Negative Stock Product", "price": 5000, "stock": 3}, headers=headers).json()
    r = client.put(f"/api/admin/products/{created['id']}/stock", json={"stock": -5}, headers=headers)
    assert r.status_code == 400


def test_deactivate_hides_from_public_catalog_but_keeps_the_row():
    headers = _admin_headers()
    created = client.post("/api/admin/products", json={"webName": "Deactivate Test Product", "price": 5000, "stock": 3}, headers=headers).json()

    r = client.delete(f"/api/admin/products/{created['id']}", headers=headers)
    assert r.status_code == 200

    public = client.get(f"/api/products/{created['id']}")
    assert public.status_code == 200  # the row still exists

    listed = client.get("/api/products", params={"q": "Deactivate Test Product"}).json()
    assert listed["total"] == 0  # but it's filtered out of catalog browsing

    admin_listed = client.get("/api/admin/products", params={"include_inactive": True}, headers=headers).json()
    assert any(p["id"] == created["id"] for p in admin_listed)


def test_reactivate_product():
    headers = _admin_headers()
    created = client.post("/api/admin/products", json={"webName": "Reactivate Test Product", "price": 5000, "stock": 3}, headers=headers).json()
    client.delete(f"/api/admin/products/{created['id']}", headers=headers)

    r = client.post(f"/api/admin/products/{created['id']}/reactivate", headers=headers)
    assert r.status_code == 200

    listed = client.get("/api/products", params={"q": "Reactivate Test Product"}).json()
    assert listed["total"] == 1


def test_low_stock_filter():
    headers = _admin_headers()
    low = client.post("/api/admin/products", json={"webName": "Low Stock Item", "price": 1000, "stock": 2}, headers=headers).json()
    high = client.post("/api/admin/products", json={"webName": "High Stock Item", "price": 1000, "stock": 500}, headers=headers).json()

    r = client.get("/api/admin/products", params={"low_stock_threshold": 5}, headers=headers)
    ids = [p["id"] for p in r.json()]
    assert low["id"] in ids
    assert high["id"] not in ids
