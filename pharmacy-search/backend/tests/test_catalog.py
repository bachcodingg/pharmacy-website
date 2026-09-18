from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _register():
    import uuid
    email = f"reviewer-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "name": "Reviewer"})
    return r.json()["token"]


def _purchasable_product(index: int):
    """The index-th product a test can actually buy and therefore review.

    Reviews are restricted to buyers (N-08), so these tests can no longer pick
    an arbitrary product off page N - it has to be in stock and over the
    counter, because a prescription item goes to awaiting_prescription instead
    of being placed. Indexed so each test gets its own product and the rating
    assertions stay independent; the stock floor keeps the selection stable as
    earlier tests buy from the same list."""
    data = client.get("/api/products", params={"in_stock": True, "page_size": 200}).json()
    candidates = [p for p in data["items"] if p["stock"] >= 5 and not p["prescription"]]
    return candidates[index]


def _buy(headers, product_id: int) -> dict:
    """Place a cash-on-delivery order for one unit, so the reviewer qualifies."""
    address = client.post("/api/auth/addresses", json={
        "label": "Home", "recipient_name": "Reviewer", "phone": "0900000000",
        "line1": "1 Test St", "city": "Ho Chi Minh City", "is_default": True,
    }, headers=headers).json()
    client.post("/api/cart/items", json={"product_id": product_id, "quantity": 1}, headers=headers)
    r = client.post("/api/checkout/place-order", json={
        "address_id": address["id"], "shipping_method": "standard", "payment_method": "cod",
    }, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _cancel_as_admin(order_id: int) -> None:
    """Only an admin can cancel an order; there is no customer-facing route."""
    import uuid

    from app.db import get_connection

    email = f"cancel-admin-{uuid.uuid4().hex[:8]}@example.com"
    token = client.post("/api/auth/register", json={
        "email": email, "password": "correcthorse", "name": "Admin",
    }).json()["token"]
    with get_connection() as conn:
        conn.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
    r = client.put(f"/api/admin/orders/{order_id}/status", json={"status": "cancelled"},
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text


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
    listed = _purchasable_product(0)
    token = _register()
    headers = {"Authorization": f"Bearer {token}"}
    _buy(headers, listed["id"])

    r = client.post(f"/api/products/{listed['id']}/reviews", json={"rating": 4, "comment": "Worked well"}, headers=headers)
    assert r.status_code == 201

    r = client.get(f"/api/products/{listed['id']}")
    assert r.json()["rating_avg"] == 4.0
    assert r.json()["rating_count"] == 1

    r = client.get(f"/api/products/{listed['id']}/reviews")
    assert len(r.json()) == 1
    assert r.json()[0]["comment"] == "Worked well"


def test_review_rejects_duplicate_from_same_user():
    listed = _purchasable_product(1)
    token = _register()
    headers = {"Authorization": f"Bearer {token}"}
    _buy(headers, listed["id"])

    r = client.post(f"/api/products/{listed['id']}/reviews", json={"rating": 5}, headers=headers)
    assert r.status_code == 201
    r = client.post(f"/api/products/{listed['id']}/reviews", json={"rating": 3}, headers=headers)
    assert r.status_code == 409


def test_review_rejects_out_of_range_rating():
    listed = _purchasable_product(2)
    token = _register()
    headers = {"Authorization": f"Bearer {token}"}
    _buy(headers, listed["id"])

    r = client.post(f"/api/products/{listed['id']}/reviews", json={"rating": 7}, headers=headers)
    assert r.status_code == 422


def test_review_rejects_user_who_never_bought_it():
    """N-08. The gate, stated directly: a signed-in account with no order for
    this product cannot rate it."""
    listed = _purchasable_product(3)
    headers = {"Authorization": f"Bearer {_register()}"}

    r = client.post(f"/api/products/{listed['id']}/reviews", json={"rating": 5}, headers=headers)
    assert r.status_code == 403
    assert "ordered" in r.json()["detail"].lower()
    assert client.get(f"/api/products/{listed['id']}/reviews").json() == []


def test_review_from_a_buyer_is_marked_verified():
    """The badge and the gate read the same predicate, so every review that
    now exists is a verified one."""
    listed = _purchasable_product(4)
    headers = {"Authorization": f"Bearer {_register()}"}
    _buy(headers, listed["id"])

    r = client.post(f"/api/products/{listed['id']}/reviews", json={"rating": 5}, headers=headers)
    assert r.status_code == 201
    assert r.json()["verified_purchase"] == 1


def test_cancelled_order_does_not_earn_a_review():
    """A buyer who cancels has not received the product. Cancellation is also
    the cheap way to fake a purchase if it counted."""
    listed = _purchasable_product(5)
    headers = {"Authorization": f"Bearer {_register()}"}
    order = _buy(headers, listed["id"])
    _cancel_as_admin(order["id"])

    r = client.post(f"/api/products/{listed['id']}/reviews", json={"rating": 5}, headers=headers)
    assert r.status_code == 403


def test_search_by_query_and_category():
    r = client.get("/api/products", params={"q": "vitamin", "page_size": 5})
    assert r.status_code == 200
    assert r.json()["total"] > 0

    r = client.get("/api/products", params={"category": "thuoc", "page_size": 5})
    assert r.status_code == 200
    assert all(item["category"] == "thuoc" for item in r.json()["items"])


def _names(params):
    return [item["webName"] for item in client.get("/api/products", params=params).json()["items"]]


def test_search_matches_names_typed_without_accents():
    # The catalog used to LIKE the raw web_name, so a query typed the way
    # people actually type - no diacritics - could never match a Vietnamese
    # product name.
    accented = client.get("/api/products", params={"q": "bàn chải", "page_size": 20}).json()
    plain = client.get("/api/products", params={"q": "ban chai", "page_size": 20}).json()
    assert accented["total"] > 0
    assert plain["total"] == accented["total"]
    assert plain["corrected_to"] is None  # no correction needed, just folding


def test_search_matches_half_typed_telex():
    r = client.get("/api/products", params={"q": "banf chair", "page_size": 20}).json()
    assert r["total"] > 0
    assert all("chải" in name.lower() for name in [i["webName"] for i in r["items"]])


def test_search_words_match_out_of_order_and_with_gaps():
    r = client.get("/api/products", params={"q": "rang ban chai", "page_size": 20}).json()
    assert r["total"] > 0


def test_single_letter_term_must_match_a_whole_word():
    # "%c%" as a substring is in almost every product name, so the "c" of
    # "vitamin c" has to mean the word C, not the letter.
    broad = client.get("/api/products", params={"q": "vitamin", "page_size": 1}).json()["total"]
    narrow = client.get("/api/products", params={"q": "vitamin c", "page_size": 1}).json()["total"]
    assert 0 < narrow < broad


def test_hyphenated_brand_matches_the_spaced_spelling():
    hyphenated = client.get("/api/products", params={"q": "oral-b", "page_size": 1}).json()["total"]
    spaced = client.get("/api/products", params={"q": "oral b", "page_size": 1}).json()["total"]
    assert hyphenated > 0 and hyphenated == spaced


def test_every_way_of_typing_a_query_returns_the_same_products():
    # Telex, VNI, half-typed, accented or bare - the catalog must not care.
    # These match by folding alone, so corrected_to stays None: the lexicon
    # fallback is a safety net, not what makes Vietnamese input work.
    variants = [
        "thuốc tránh thai",
        "thuoc tranh thai",
        "thuoc tranhs thai",
        "thuoocs traxnh thai",
        "thuoc1 tranh2 thai",
    ]
    results = [client.get("/api/products", params={"q": v, "page_size": 50}).json() for v in variants]
    assert results[0]["total"] > 0
    assert {r["total"] for r in results} == {results[0]["total"]}
    assert all(r["corrected_to"] is None for r in results)
    assert len({tuple(i["id"] for i in r["items"]) for r in results}) == 1


def test_search_falls_back_to_the_spelling_corrector():
    r = client.get("/api/products", params={"q": "vitmain c", "page_size": 5}).json()
    assert r["total"] > 0
    assert r["corrected_to"] is not None


def test_search_reports_no_correction_when_nothing_helps():
    r = client.get("/api/products", params={"q": "qqzzxx", "page_size": 5}).json()
    assert r["total"] == 0
    assert r["corrected_to"] is None


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
    listed = _purchasable_product(6)
    token = _register()
    headers = {"Authorization": f"Bearer {token}"}
    _buy(headers, listed["id"])
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
    listed = _purchasable_product(7)
    token = _register()
    headers = {"Authorization": f"Bearer {token}"}
    _buy(headers, listed["id"])
    client.post(f"/api/products/{listed['id']}/reviews", json={"rating": 5}, headers=headers)

    r = client.get("/api/products", params={"sort": "top_rated", "page_size": 1})
    assert r.json()["items"][0]["rating_avg"] == 5.0


def test_facets_reflect_current_filter():
    all_facets = client.get("/api/products/facets").json()
    scoped_facets = client.get("/api/products/facets", params={"category": "thuoc"}).json()
    assert scoped_facets["price_min"] >= 0
    assert len(scoped_facets["brands"]) <= len(all_facets["brands"])
