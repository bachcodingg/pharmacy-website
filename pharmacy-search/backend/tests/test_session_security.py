"""Credential changes end existing sessions, and responses carry security headers."""

import time
import uuid

from fastapi.testclient import TestClient

from app.db import get_connection, purge_expired_sessions
from app.main import app

client = TestClient(app)


def _account():
    email = f"sess-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "A"})
    return email, r.json()["token"]


def _login(email, password="correcthorse"):
    return client.post("/api/auth/login", json={"email": email, "password": password}).json()["token"]


def _reset_token(email):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT t.token FROM password_reset_tokens t JOIN users u ON u.id = t.user_id "
            "WHERE u.email = ? AND t.used = 0 ORDER BY t.created_at DESC LIMIT 1",
            (email,),
        ).fetchone()
    return row["token"]


def test_changing_the_password_signs_out_other_devices():
    email, first_token = _account()
    second_token = _login(email)  # the "other device"

    r = client.post("/api/auth/change-password",
                    json={"old_password": "correcthorse", "new_password": "brandnewpass1"},
                    headers={"Authorization": f"Bearer {second_token}"})
    assert r.status_code == 200

    # The session that made the change keeps working...
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {second_token}"}).status_code == 200
    # ...and every other one is gone, which is the whole point of changing it.
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {first_token}"}).status_code == 401


def test_resetting_the_password_signs_out_every_session():
    email, token = _account()
    other = _login(email)
    client.post("/api/auth/forgot-password", json={"email": email})
    r = client.post("/api/auth/reset-password",
                    json={"token": _reset_token(email), "new_password": "brandnewpass1"})
    assert r.status_code == 200

    for stale in (token, other):
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {stale}"}).status_code == 401


def test_a_password_change_kills_outstanding_reset_tokens():
    email, token = _account()
    client.post("/api/auth/forgot-password", json={"email": email})
    reset_token = _reset_token(email)

    client.post("/api/auth/change-password",
                json={"old_password": "correcthorse", "new_password": "brandnewpass1"},
                headers={"Authorization": f"Bearer {token}"})

    r = client.post("/api/auth/reset-password", json={"token": reset_token, "new_password": "thirdpassword1"})
    assert r.status_code == 400


def test_requesting_a_second_reset_invalidates_the_first():
    email, _ = _account()
    client.post("/api/auth/forgot-password", json={"email": email})
    first = _reset_token(email)
    client.post("/api/auth/forgot-password", json={"email": email})

    r = client.post("/api/auth/reset-password", json={"token": first, "new_password": "brandnewpass1"})
    assert r.status_code == 400


def test_expired_sessions_are_purged():
    email, token = _account()
    with get_connection() as conn:
        conn.execute("UPDATE sessions SET expires_at = ? WHERE token = ?", (time.time() - 1, token))
    assert purge_expired_sessions() >= 1
    with get_connection() as conn:
        assert conn.execute("SELECT 1 FROM sessions WHERE token = ?", (token,)).fetchone() is None


def test_security_headers_are_present():
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "max-age=" in r.headers["strict-transport-security"]
