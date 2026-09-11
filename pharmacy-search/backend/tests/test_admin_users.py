from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app

client = TestClient(app)


def _admin_headers():
    import uuid
    email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Admin"})
    user_id = None
    with get_connection() as conn:
        conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
        user_id = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()["id"]
    return {"Authorization": f"Bearer {r.json()['token']}"}, user_id


def _regular_headers():
    import uuid
    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Regular"})
    user_id = None
    with get_connection() as conn:
        user_id = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()["id"]
    return {"Authorization": f"Bearer {r.json()['token']}"}, user_id


def test_admin_users_requires_admin():
    headers, _ = _regular_headers()
    r = client.get("/api/admin/users", headers=headers)
    assert r.status_code == 403


def test_list_users_includes_order_count():
    admin_headers, _ = _admin_headers()
    r = client.get("/api/admin/users", headers=admin_headers)
    assert r.status_code == 200
    assert all("order_count" in u for u in r.json())


def test_promote_user_to_admin():
    admin_headers, _ = _admin_headers()
    regular_headers, regular_id = _regular_headers()

    r = client.put(f"/api/admin/users/{regular_id}/admin", json={"is_admin": True}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["is_admin"] is True

    # the newly promoted user can now use admin endpoints themselves
    r = client.get("/api/admin/users", headers=regular_headers)
    assert r.status_code == 200


def test_admin_cannot_demote_self():
    admin_headers, admin_id = _admin_headers()
    r = client.put(f"/api/admin/users/{admin_id}/admin", json={"is_admin": False}, headers=admin_headers)
    assert r.status_code == 400


def test_admin_can_demote_someone_else():
    admin_headers, _ = _admin_headers()
    other_admin_headers, other_admin_id = _admin_headers()

    r = client.put(f"/api/admin/users/{other_admin_id}/admin", json={"is_admin": False}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["is_admin"] is False

    # 401, not 403: revoking admin now also drops that account's sessions, so
    # the old token stops being a session at all rather than becoming a
    # session without the right. Either way the door is shut.
    r = client.get("/api/admin/users", headers=other_admin_headers)
    assert r.status_code == 401
