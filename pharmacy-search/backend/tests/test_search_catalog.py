"""/api/search answers from the product table, not a snapshot of it.

Search used to read the corrector's own products.jsonl, loaded once at
import. The search engine and the shop were therefore two different
datastores: withdrawn products kept appearing, admin edits never did, and a
result carried no id or price, so it could not be opened or bought."""

import uuid

from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app

client = TestClient(app)


def _admin():
    email = f"s-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "A"})
    with get_connection() as conn:
        conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_search_results_are_shoppable():
    r = client.get("/api/search", params={"q": "kem danh rang"})
    assert r.status_code == 200
    products = r.json()["products"]
    assert products, "expected the corrected query to find products"
    first = products[0]
    # Everything the old snapshot-backed result was missing.
    for field in ("id", "price", "currency", "stock", "prescription"):
        assert field in first, f"search result has no {field}"
    # The id resolves against the catalogue, so the card can link to it.
    assert client.get(f"/api/products/{first['id']}").status_code == 200


def test_search_reflects_an_admin_rename():
    admin = _admin()
    token = uuid.uuid4().hex[:8]
    created = client.post("/api/admin/products", json={
        "webName": f"Zzyrax {token}", "category": "cham-soc-ca-nhan", "price": 1000, "stock": 5,
    }, headers=admin).json()

    found = client.get("/api/search", params={"q": f"zzyrax {token}"}).json()["products"]
    assert any(p["id"] == created["id"] for p in found)

    client.put(f"/api/admin/products/{created['id']}", json={"webName": f"Qqwrex {token}"}, headers=admin)
    assert not client.get("/api/search", params={"q": f"zzyrax {token}"}).json()["products"]
    renamed = client.get("/api/search", params={"q": f"qqwrex {token}"}).json()["products"]
    assert any(p["id"] == created["id"] for p in renamed)


def test_withdrawn_products_disappear_from_search():
    admin = _admin()
    token = uuid.uuid4().hex[:8]
    created = client.post("/api/admin/products", json={
        "webName": f"Wibblex {token}", "category": "cham-soc-ca-nhan", "price": 1000, "stock": 5,
    }, headers=admin).json()
    assert client.get("/api/search", params={"q": f"wibblex {token}"}).json()["products"]

    client.delete(f"/api/admin/products/{created['id']}", headers=admin)
    result = client.get("/api/search", params={"q": f"wibblex {token}"}).json()
    assert result["products"] == []
    assert result["decision"] == "no_results"


def test_search_price_matches_the_catalogue_price():
    admin = _admin()
    token = uuid.uuid4().hex[:8]
    created = client.post("/api/admin/products", json={
        "webName": f"Pricetest {token}", "category": "cham-soc-ca-nhan", "price": 12000, "stock": 5,
    }, headers=admin).json()
    client.put(f"/api/admin/products/{created['id']}", json={"price": 99000}, headers=admin)

    found = client.get("/api/search", params={"q": f"pricetest {token}"}).json()["products"]
    assert found[0]["price"] == 99000


def test_overlong_queries_are_truncated_not_served_whole():
    r = client.get("/api/search", params={"q": "a" * 5000})
    assert r.status_code == 200
    assert len(r.json()["query"]) <= 200


def test_search_still_corrects_typos():
    r = client.get("/api/search", params={"q": "kem danh rangg"})
    assert r.status_code == 200
    assert r.json()["decision"] in ("auto_correct", "did_you_mean")
