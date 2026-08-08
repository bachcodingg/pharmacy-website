import json

from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app
from learning.review import CANDIDATES_PATH, APPROVED_PATH

client = TestClient(app)


def _admin_headers():
    import uuid
    email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Admin"})
    with get_connection() as conn:
        conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _seed_candidate(from_query, to_query, status="pending"):
    existing = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8")) if CANDIDATES_PATH.exists() else []
    existing = [c for c in existing if not (c["from_query"] == from_query and c["to_query"] == to_query)]
    existing.append({
        "from_query": from_query, "to_query": to_query,
        "occurrences": 5, "distinct_sessions": 3, "meets_threshold": True, "status": status,
    })
    CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATES_PATH.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")


def test_admin_corrections_requires_admin():
    r = client.get("/api/admin/corrections")
    assert r.status_code == 401


def test_list_corrections_matches_what_the_cli_reads():
    _seed_candidate("teszt_from", "teszt_to")
    headers = _admin_headers()
    r = client.get("/api/admin/corrections", headers=headers)
    assert r.status_code == 200
    assert any(c["from_query"] == "teszt_from" and c["to_query"] == "teszt_to" for c in r.json())


def test_approve_writes_to_approved_pairs_file():
    _seed_candidate("apprv_from", "apprv_to")
    headers = _admin_headers()

    r = client.post("/api/admin/corrections/approve", json={"from_query": "apprv_from", "to_query": "apprv_to"}, headers=headers)
    assert r.status_code == 200

    approved = json.loads(APPROVED_PATH.read_text(encoding="utf-8"))
    assert any(a["from_query"] == "apprv_from" and a["to_query"] == "apprv_to" for a in approved)

    candidates = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    match = next(c for c in candidates if c["from_query"] == "apprv_from")
    assert match["status"] == "approved"


def test_reject_does_not_write_to_approved_pairs():
    _seed_candidate("rejct_from", "rejct_to")
    headers = _admin_headers()

    r = client.post("/api/admin/corrections/reject", json={"from_query": "rejct_from", "to_query": "rejct_to"}, headers=headers)
    assert r.status_code == 200

    approved = json.loads(APPROVED_PATH.read_text(encoding="utf-8")) if APPROVED_PATH.exists() else []
    assert not any(a["from_query"] == "rejct_from" for a in approved)


def test_approve_unknown_pair_404s():
    headers = _admin_headers()
    r = client.post("/api/admin/corrections/approve", json={"from_query": "nope", "to_query": "nope2"}, headers=headers)
    assert r.status_code == 404
