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
    assert isinstance(first["price_is_estimated"], bool)
    assert first["stock_is_estimated"] is True  # stock has no real source at all, always estimated
    assert first["sku"].startswith("LC-")


def test_price_is_estimated_flag_is_not_uniformly_true():
    # Regression guard: before real prices were crawled, every row had
    # price_is_estimated=True. If this ever goes back to "all True", the real
    # price data silently stopped making it into the catalog.
    r = client.get("/api/products", params={"page_size": 100})
    flags = {item["price_is_estimated"] for item in r.json()["items"]}
    assert flags == {True, False}


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


def test_filter_by_brand():
    brand = client.get("/api/products/facets").json()["brands"][0]
    r = client.get("/api/products", params={"brand": brand, "page_size": 50})
    assert r.status_code == 200
    assert r.json()["total"] > 0
    assert all(item["brand"] == brand for item in r.json()["items"])


def test_filter_by_price_range():
    r = client.get("/api/products", params={"min_price": 50000, "max_price": 100000, "page_size": 50})
    assert r.status_code == 200
    assert r.json()["total"] > 0
    for item in r.json()["items"]:
        assert 50000 <= item["price"] <= 100000


def test_filter_by_in_stock():
    r = client.get("/api/products", params={"in_stock": True, "page_size": 50})
    assert r.status_code == 200
    assert all(item["stock"] > 0 for item in r.json()["items"])


def test_filter_by_min_rating_excludes_unrated_products():
    listed = client.get("/api/products", params={"page": 5, "page_size": 1}).json()["items"][0]
    token = _register()
    headers = {"Authorization": f"Bearer {token}"}
    client.post(f"/api/products/{listed['id']}/reviews", json={"rating": 5}, headers=headers)

    r = client.get("/api/products", params={"min_rating": 4, "page_size": 50})
    assert r.status_code == 200
    assert any(item["id"] == listed["id"] for item in r.json()["items"])
    assert all(item["rating_avg"] is not None and item["rating_avg"] >= 4 for item in r.json()["items"])


def test_sort_price_ascending_and_descending():
    r = client.get("/api/products", params={"sort": "price_asc", "page_size": 20})
    prices = [item["price"] for item in r.json()["items"]]
    assert prices == sorted(prices)

    r = client.get("/api/products", params={"sort": "price_desc", "page_size": 20})
    prices = [item["price"] for item in r.json()["items"]]
    assert prices == sorted(prices, reverse=True)


def test_sort_alphabetical():
    r = client.get("/api/products", params={"sort": "name", "page_size": 20})
    names = [item["webName"] for item in r.json()["items"]]
    assert names == sorted(names)


def test_sort_newest_is_most_recently_migrated_first():
    r = client.get("/api/products", params={"sort": "newest", "page_size": 20})
    ids = [item["id"] for item in r.json()["items"]]
    assert ids == sorted(ids, reverse=True)


def test_sort_top_rated_puts_rated_products_first():
    listed = client.get("/api/products", params={"page": 6, "page_size": 1}).json()["items"][0]
    token = _register()
    headers = {"Authorization": f"Bearer {token}"}
    client.post(f"/api/products/{listed['id']}/reviews", json={"rating": 5}, headers=headers)

    r = client.get("/api/products", params={"sort": "top_rated", "page_size": 1})
    assert r.json()["items"][0]["rating_avg"] == 5.0


def test_facets_reflect_current_filter():
    all_facets = client.get("/api/products/facets").json()
    scoped_facets = client.get("/api/products/facets", params={"category": "thuoc"}).json()
    assert scoped_facets["price_min"] >= 0
    assert len(scoped_facets["brands"]) <= len(all_facets["brands"])
