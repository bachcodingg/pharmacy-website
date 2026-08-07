from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _register_and_headers():
    import uuid
    email = f"shopper-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Shopper"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _in_stock_product():
    data = client.get("/api/products", params={"in_stock": True, "page_size": 1}).json()
    return data["items"][0]


def test_cart_requires_auth():
    r = client.get("/api/cart")
    assert r.status_code == 401


def test_add_item_and_view_cart():
    headers = _register_and_headers()
    product = _in_stock_product()

    r = client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 2}, headers=headers)
    assert r.status_code == 201
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["quantity"] == 2
    assert body["subtotal"] == product["price"] * 2
    assert body["total"] == body["subtotal"]


def test_adding_same_product_twice_increments_quantity():
    headers = _register_and_headers()
    product = _in_stock_product()

    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers)
    r = client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers)
    assert len(r.json()["items"]) == 1
    assert r.json()["items"][0]["quantity"] == 2


def test_cannot_add_out_of_stock_product():
    headers = _register_and_headers()
    data = client.get("/api/products", params={"page_size": 200}).json()
    out_of_stock = next((p for p in data["items"] if p["stock"] == 0), None)
    if out_of_stock is None:
        return  # nothing out of stock in this sample, nothing to assert
    r = client.post("/api/cart/items", json={"product_id": out_of_stock["id"], "quantity": 1}, headers=headers)
    assert r.status_code == 400


def test_quantity_is_capped_at_available_stock():
    headers = _register_and_headers()
    product = _in_stock_product()
    r = client.post("/api/cart/items", json={"product_id": product["id"], "quantity": product["stock"] + 50}, headers=headers)
    assert r.json()["items"][0]["quantity"] == product["stock"]


def test_update_quantity():
    headers = _register_and_headers()
    product = _in_stock_product()
    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers)

    r = client.put(f"/api/cart/items/{product['id']}", json={"quantity": 3}, headers=headers)
    assert r.status_code == 200
    assert r.json()["items"][0]["quantity"] == min(3, product["stock"])


def test_remove_item():
    headers = _register_and_headers()
    product = _in_stock_product()
    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers)

    r = client.delete(f"/api/cart/items/{product['id']}", headers=headers)
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_save_for_later_and_move_back():
    headers = _register_and_headers()
    product = _in_stock_product()
    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers)

    r = client.post(f"/api/cart/items/{product['id']}/save-for-later", headers=headers)
    assert r.json()["items"] == []
    assert len(r.json()["saved_for_later"]) == 1
    # saved-for-later items don't count toward the subtotal
    assert r.json()["subtotal"] == 0

    r = client.post(f"/api/cart/items/{product['id']}/move-to-cart", headers=headers)
    assert len(r.json()["items"]) == 1
    assert r.json()["saved_for_later"] == []


def test_apply_percent_discount_code():
    headers = _register_and_headers()
    product = _in_stock_product()
    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers)

    r = client.post("/api/cart/discount", json={"code": "welcome10"}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["discount_code"] == "WELCOME10"
    assert body["discount_amount"] == body["subtotal"] // 10
    assert body["total"] == body["subtotal"] - body["discount_amount"]


def test_apply_fixed_discount_code():
    headers = _register_and_headers()
    product = _in_stock_product()
    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers)

    r = client.post("/api/cart/discount", json={"code": "SAVE20K"}, headers=headers)
    body = r.json()
    assert body["discount_amount"] == min(20000, body["subtotal"])


def test_invalid_discount_code_rejected():
    headers = _register_and_headers()
    r = client.post("/api/cart/discount", json={"code": "NOTAREALCODE"}, headers=headers)
    assert r.status_code == 404


def test_remove_discount_code():
    headers = _register_and_headers()
    product = _in_stock_product()
    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers)
    client.post("/api/cart/discount", json={"code": "WELCOME10"}, headers=headers)

    r = client.delete("/api/cart/discount", headers=headers)
    assert r.json()["discount_code"] is None
    assert r.json()["discount_amount"] == 0


def test_carts_are_isolated_per_user():
    headers_a = _register_and_headers()
    headers_b = _register_and_headers()
    product = _in_stock_product()

    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers_a)

    r = client.get("/api/cart", headers=headers_b)
    assert r.json()["items"] == []
