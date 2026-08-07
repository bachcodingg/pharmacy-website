from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _register():
    import uuid
    email = f"reviewer-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Reviewer"})
    return r.json()["token"]


def test_list_products_is_paginated_and_flags_estimated_fields():
    r = client.get("/api/products", params={"page": 1, "page_size": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] > 1000
    assert len(body["items"]) == 5
    first = body["items"][0]
    assert first["price_is_estimated"] is True
    assert first["stock_is_estimated"] is True
    assert first["sku"].startswith("LC-")


def test_get_single_product():
    listed = client.get("/api/products", params={"page_size": 1}).json()["items"][0]
    r = client.get(f"/api/products/{listed['id']}")
    assert r.status_code == 200
    assert r.json()["webName"] == listed["webName"]


def test_get_missing_product_404s():
    r = client.get("/api/products/999999999")
    assert r.status_code == 404


def test_review_requires_auth():
    listed = client.get("/api/products", params={"page_size": 1}).json()["items"][0]
    r = client.post(f"/api/products/{listed['id']}/reviews", json={"rating": 5})
    assert r.status_code == 401


def test_create_review_updates_product_rating():
    listed = client.get("/api/products", params={"page": 2, "page_size": 1}).json()["items"][0]
    token = _register()
    headers = {"Authorization": f"Bearer {token}"}

    r = client.post(f"/api/products/{listed['id']}/reviews", json={"rating": 4, "comment": "Worked well"}, headers=headers)
    assert r.status_code == 201

    r = client.get(f"/api/products/{listed['id']}")
    assert r.json()["rating_avg"] == 4.0
    assert r.json()["rating_count"] == 1

    r = client.get(f"/api/products/{listed['id']}/reviews")
    assert len(r.json()) == 1
    assert r.json()[0]["comment"] == "Worked well"


def test_review_rejects_duplicate_from_same_user():
    listed = client.get("/api/products", params={"page": 3, "page_size": 1}).json()["items"][0]
    token = _register()
    headers = {"Authorization": f"Bearer {token}"}

    r = client.post(f"/api/products/{listed['id']}/reviews", json={"rating": 5}, headers=headers)
    assert r.status_code == 201
    r = client.post(f"/api/products/{listed['id']}/reviews", json={"rating": 3}, headers=headers)
    assert r.status_code == 409


def test_review_rejects_out_of_range_rating():
    listed = client.get("/api/products", params={"page": 4, "page_size": 1}).json()["items"][0]
    token = _register()
    headers = {"Authorization": f"Bearer {token}"}

    r = client.post(f"/api/products/{listed['id']}/reviews", json={"rating": 7}, headers=headers)
    assert r.status_code == 422


def test_search_by_query_and_category():
    r = client.get("/api/products", params={"q": "vitamin", "page_size": 5})
    assert r.status_code == 200
    assert r.json()["total"] > 0

    r = client.get("/api/products", params={"category": "thuoc", "page_size": 5})
    assert r.status_code == 200
    assert all(item["category"] == "thuoc" for item in r.json()["items"])
