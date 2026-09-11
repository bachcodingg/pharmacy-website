from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _unique_email():
    import uuid
    return f"user-{uuid.uuid4().hex[:8]}@example.com"


def test_register_then_me():
    email = _unique_email()
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Alice"})
    assert r.status_code == 201
    token = r.json()["token"]

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == email


def test_register_rejects_duplicate_email():
    email = _unique_email()
    client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Alice"})
    r = client.post("/api/auth/register", json={"email": email, "password": "different1", "name": "Bob"})
    assert r.status_code == 409


def test_register_rejects_short_password():
    r = client.post("/api/auth/register", json={"email": _unique_email(), "password": "short", "name": "Alice"})
    assert r.status_code == 400


def test_login_with_correct_and_wrong_password():
    email = _unique_email()
    client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Alice"})

    r = client.post("/api/auth/login", json={"email": email, "password": "correcthorse"})
    assert r.status_code == 200
    assert "token" in r.json()

    r = client.post("/api/auth/login", json={"email": email, "password": "wrongpassword"})
    assert r.status_code == 401


def test_protected_endpoint_requires_token():
    r = client.get("/api/auth/me")
    assert r.status_code == 401

    r = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_logout_invalidates_session():
    email = _unique_email()
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Alice"})
    token = r.json()["token"]

    r = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_update_profile():
    email = _unique_email()
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Alice"})
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = client.put("/api/auth/me", json={"name": "Alice Updated"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Alice Updated"


def test_change_password_requires_correct_old_password():
    email = _unique_email()
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Alice"})
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = client.post("/api/auth/change-password", json={"old_password": "wrong", "new_password": "newpassword1"}, headers=headers)
    assert r.status_code == 401

    r = client.post("/api/auth/change-password", json={"old_password": "correcthorse", "new_password": "newpassword1"}, headers=headers)
    assert r.status_code == 200

    r = client.post("/api/auth/login", json={"email": email, "password": "newpassword1"})
    assert r.status_code == 200


def test_forgot_password_does_not_leak_whether_email_exists():
    r1 = client.post("/api/auth/forgot-password", json={"email": _unique_email()})
    r2 = client.post("/api/auth/forgot-password", json={"email": _unique_email()})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["status"] == r2.json()["status"]


def _reset_token_from_db(email):
    """Read the token out of storage instead of the response body.

    The endpoint deliberately does not return it - see F-01. A test that
    needed it in the response was the reason it stayed there."""
    from app.db import get_connection

    with get_connection() as conn:
        row = conn.execute(
            "SELECT t.token FROM password_reset_tokens t JOIN users u ON u.id = t.user_id "
            "WHERE u.email = ? AND t.used = 0 ORDER BY t.created_at DESC LIMIT 1",
            (email,),
        ).fetchone()
    return row["token"] if row else None


def test_forgot_password_never_returns_the_token():
    email = _unique_email()
    client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Alice"})
    r = client.post("/api/auth/forgot-password", json={"email": email})
    assert r.status_code == 200
    assert "dev_only_reset_token" not in r.json()
    assert r.json() == {"status": "if_the_email_exists_a_reset_link_was_sent"}
    # The token exists, it is just not handed to the caller.
    assert _reset_token_from_db(email)


def test_forgot_password_then_reset_password_flow():
    email = _unique_email()
    client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Alice"})

    client.post("/api/auth/forgot-password", json={"email": email})
    token = _reset_token_from_db(email)

    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "brandnewpass1"})
    assert r.status_code == 200

    r = client.post("/api/auth/login", json={"email": email, "password": "brandnewpass1"})
    assert r.status_code == 200

    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "anotherpass1"})
    assert r.status_code == 400


def test_address_crud():
    email = _unique_email()
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Alice"})
    headers = {"Authorization": f"Bearer {r.json()['token']}"}

    r = client.post("/api/auth/addresses", json={
        "label": "Home", "recipient_name": "Alice", "phone": "0900000000",
        "line1": "123 Main St", "city": "Ho Chi Minh City", "is_default": True,
    }, headers=headers)
    assert r.status_code == 201
    address_id = r.json()["id"]

    r = client.get("/api/auth/addresses", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 1

    r = client.delete(f"/api/auth/addresses/{address_id}", headers=headers)
    assert r.status_code == 200

    r = client.get("/api/auth/addresses", headers=headers)
    assert len(r.json()) == 0


def test_orders_list_starts_empty():
    # Order history now lives at /api/checkout/orders (see test_checkout.py for
    # the full placed-order flow) - this just confirms a fresh account starts
    # with no history there.
    email = _unique_email()
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Alice"})
    headers = {"Authorization": f"Bearer {r.json()['token']}"}

    r = client.get("/api/checkout/orders", headers=headers)
    assert r.status_code == 200
    assert r.json() == []
