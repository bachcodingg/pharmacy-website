"""Auth routes are no longer an unlimited guessing gallery.

PBKDF2 at 390k iterations costs ~100ms of CPU per attempt, so an unlimited
login endpoint was both a credential-stuffing target and a cheap way to
saturate the one shared machine it runs on."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app import config, ratelimit
from app.auth import LOGIN_RATE_LIMIT, REGISTER_RATE_LIMIT
from app.main import app

client = TestClient(app)


@pytest.fixture
def limiter_on(monkeypatch):
    # conftest disables limiting for the rest of the suite; these tests are
    # the ones that need it on.
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", True)
    ratelimit.reset_all()
    yield
    ratelimit.reset_all()


def test_repeated_failed_logins_are_throttled(limiter_on):
    email = f"lock-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "A"})
    ratelimit.reset_all()

    codes = [
        client.post("/api/auth/login", json={"email": email, "password": "wrongpassword"}).status_code
        for _ in range(LOGIN_RATE_LIMIT[0] + 3)
    ]
    assert codes[0] == 401
    assert 429 in codes
    assert codes[-1] == 429


def test_throttled_response_says_when_to_retry(limiter_on):
    email = f"retry-{uuid.uuid4().hex[:8]}@example.com"
    for _ in range(LOGIN_RATE_LIMIT[0] + 1):
        r = client.post("/api/auth/login", json={"email": email, "password": "nope-nope"})
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0


def test_registration_is_throttled(limiter_on):
    codes = []
    for _ in range(REGISTER_RATE_LIMIT[0] + 2):
        email = f"flood-{uuid.uuid4().hex[:8]}@example.com"
        codes.append(
            client.post("/api/auth/register",
                        json={"email": email, "password": "correcthorse", "name": "A"}).status_code
        )
    assert codes[0] == 201
    assert codes[-1] == 429


def test_forgot_password_is_throttled(limiter_on):
    codes = [
        client.post("/api/auth/forgot-password", json={"email": "someone@example.com"}).status_code
        for _ in range(8)
    ]
    assert 429 in codes


def test_a_correct_login_still_works_below_the_limit(limiter_on):
    email = f"fine-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "A"})
    ratelimit.reset_all()
    for _ in range(3):
        client.post("/api/auth/login", json={"email": email, "password": "wrongpassword"})
    r = client.post("/api/auth/login", json={"email": email, "password": "correcthorse"})
    assert r.status_code == 200


def test_limiter_windows_are_per_bucket():
    limiter = ratelimit.SlidingWindowLimiter()
    assert limiter.check("a", limit=2, window_seconds=60) == 0.0
    assert limiter.check("a", limit=2, window_seconds=60) == 0.0
    assert limiter.check("a", limit=2, window_seconds=60) > 0.0
    # A different key is unaffected by the first one's exhaustion.
    assert limiter.check("b", limit=2, window_seconds=60) == 0.0


def test_limiter_prunes_idle_buckets():
    limiter = ratelimit.SlidingWindowLimiter()
    limiter.check("stale", limit=5, window_seconds=1)
    limiter.prune(older_than=-1)  # everything counts as idle
    assert limiter._hits == {}
