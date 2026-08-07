from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _register_and_headers():
    import uuid
    email = f"buyer-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Buyer"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _in_stock_product(min_stock=2):
    data = client.get("/api/products", params={"in_stock": True, "page_size": 200}).json()
    return next(p for p in data["items"] if p["stock"] >= min_stock)


def _address(headers):
    r = client.post("/api/auth/addresses", json={
        "label": "Home", "recipient_name": "Buyer", "phone": "0900000000",
        "line1": "123 Main St", "city": "Ho Chi Minh City", "is_default": True,
    }, headers=headers)
    return r.json()["id"]


def test_checkout_requires_auth():
    r = client.post("/api/checkout/place-order", json={"address_id": 1, "shipping_method": "standard", "payment_method": "cod"})
    assert r.status_code == 401


def test_place_order_requires_nonempty_cart():
    headers = _register_and_headers()
    address_id = _address(headers)
    r = client.post("/api/checkout/place-order", json={"address_id": address_id, "shipping_method": "standard", "payment_method": "cod"}, headers=headers)
    assert r.status_code == 400


def test_place_order_requires_valid_address():
    headers = _register_and_headers()
    product = _in_stock_product()
    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers)
    r = client.post("/api/checkout/place-order", json={"address_id": 999999, "shipping_method": "standard", "payment_method": "cod"}, headers=headers)
    assert r.status_code == 404


def test_place_order_cod_success_decrements_stock_and_clears_cart():
    headers = _register_and_headers()
    address_id = _address(headers)
    product = _in_stock_product()
    starting_stock = product["stock"]

    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 2}, headers=headers)
    r = client.post("/api/checkout/place-order", json={
        "address_id": address_id, "shipping_method": "standard", "payment_method": "cod",
    }, headers=headers)
    assert r.status_code == 201
    order = r.json()
    assert order["status"] == "placed"
    assert order["items"][0]["quantity"] == 2
    assert order["shipping_fee"] == 0
    assert order["total"] == order["subtotal"]

    updated_product = client.get(f"/api/products/{product['id']}").json()
    assert updated_product["stock"] == starting_stock - 2

    cart = client.get("/api/cart", headers=headers).json()
    assert cart["items"] == []


def test_place_order_with_express_shipping_adds_fee():
    headers = _register_and_headers()
    address_id = _address(headers)
    product = _in_stock_product()
    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers)

    r = client.post("/api/checkout/place-order", json={
        "address_id": address_id, "shipping_method": "express", "payment_method": "cod",
    }, headers=headers)
    order = r.json()
    assert order["shipping_fee"] == 30000
    assert order["total"] == order["subtotal"] + 30000


def test_place_order_with_discount_code_applies_to_total():
    headers = _register_and_headers()
    address_id = _address(headers)
    product = _in_stock_product()
    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers)
    client.post("/api/cart/discount", json={"code": "WELCOME10"}, headers=headers)

    r = client.post("/api/checkout/place-order", json={
        "address_id": address_id, "shipping_method": "standard", "payment_method": "cod",
    }, headers=headers)
    order = r.json()
    assert order["discount_code"] == "WELCOME10"
    assert order["discount_amount"] == order["subtotal"] // 10
    assert order["total"] == order["subtotal"] - order["discount_amount"]


def test_place_order_with_unavailable_payment_method_is_pending_not_placed():
    headers = _register_and_headers()
    address_id = _address(headers)
    product = _in_stock_product()
    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers)

    r = client.post("/api/checkout/place-order", json={
        "address_id": address_id, "shipping_method": "standard", "payment_method": "vnpay",
    }, headers=headers)
    assert r.status_code == 201
    assert r.json()["status"] == "pending_payment"


def test_place_order_rejects_quantity_beyond_current_stock():
    headers = _register_and_headers()
    address_id = _address(headers)
    product = _in_stock_product()

    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers)
    # Sneak the stock down after the item was already added to the cart.
    admin_headers = _admin_headers()
    client.put(f"/api/admin/products/{product['id']}/stock", json={"stock": 0}, headers=admin_headers)

    r = client.post("/api/checkout/place-order", json={
        "address_id": address_id, "shipping_method": "standard", "payment_method": "cod",
    }, headers=headers)
    assert r.status_code == 409


def test_order_appears_in_order_history_with_items():
    headers = _register_and_headers()
    address_id = _address(headers)
    product = _in_stock_product()
    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers)
    placed = client.post("/api/checkout/place-order", json={
        "address_id": address_id, "shipping_method": "standard", "payment_method": "cod",
    }, headers=headers).json()

    r = client.get("/api/checkout/orders", headers=headers)
    assert r.status_code == 200
    assert any(o["id"] == placed["id"] for o in r.json())

    r = client.get(f"/api/checkout/orders/{placed['id']}", headers=headers)
    assert r.status_code == 200
    assert r.json()["items"][0]["product_id"] == product["id"]


def test_orders_are_isolated_per_user():
    headers_a = _register_and_headers()
    headers_b = _register_and_headers()
    address_id = _address(headers_a)
    product = _in_stock_product()
    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers_a)
    placed = client.post("/api/checkout/place-order", json={
        "address_id": address_id, "shipping_method": "standard", "payment_method": "cod",
    }, headers=headers_a).json()

    r = client.get(f"/api/checkout/orders/{placed['id']}", headers=headers_b)
    assert r.status_code == 404


def _admin_headers():
    import uuid
    from app.db import get_connection
    email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Admin"})
    token = r.json()["token"]
    with get_connection() as conn:
        conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
    return {"Authorization": f"Bearer {token}"}
