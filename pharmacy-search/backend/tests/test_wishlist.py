from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _register_and_headers():
    import uuid
    email = f"wisher-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Wisher"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _in_stock_product():
    data = client.get("/api/products", params={"in_stock": True, "page_size": 1}).json()
    return data["items"][0]


def test_wishlist_requires_auth():
    r = client.get("/api/wishlist")
    assert r.status_code == 401


def test_add_and_list_wishlist():
    headers = _register_and_headers()
    product = _in_stock_product()

    r = client.post("/api/wishlist", json={"product_id": product["id"]}, headers=headers)
    assert r.status_code == 201
    assert len(r.json()) == 1
    assert r.json()[0]["product_id"] == product["id"]


def test_adding_same_product_twice_does_not_duplicate():
    headers = _register_and_headers()
    product = _in_stock_product()

    client.post("/api/wishlist", json={"product_id": product["id"]}, headers=headers)
    r = client.post("/api/wishlist", json={"product_id": product["id"]}, headers=headers)
    assert len(r.json()) == 1


def test_remove_from_wishlist():
    headers = _register_and_headers()
    product = _in_stock_product()
    client.post("/api/wishlist", json={"product_id": product["id"]}, headers=headers)

    r = client.delete(f"/api/wishlist/{product['id']}", headers=headers)
    assert r.json() == []


def test_move_to_cart_removes_from_wishlist_and_adds_to_cart():
    headers = _register_and_headers()
    product = _in_stock_product()
    client.post("/api/wishlist", json={"product_id": product["id"]}, headers=headers)

    r = client.post(f"/api/wishlist/{product['id']}/move-to-cart", headers=headers)
    assert r.status_code == 200
    assert r.json() == []

    cart = client.get("/api/cart", headers=headers).json()
    assert any(item["product_id"] == product["id"] for item in cart["items"])


def test_wishlists_are_isolated_per_user():
    headers_a = _register_and_headers()
    headers_b = _register_and_headers()
    product = _in_stock_product()

    client.post("/api/wishlist", json={"product_id": product["id"]}, headers=headers_a)

    r = client.get("/api/wishlist", headers=headers_b)
    assert r.json() == []
