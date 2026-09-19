def _healthy_product(client):
    products = client.get("/api/products").json()
    return next(p for p in products if p["status"] == "healthy" and p["current_stock"] >= 2)


def _login_demo(client):
    r = client.post("/api/storefront/auth/login", json={"email": "demo@omniretail.test", "password": "password123"})
    assert r.status_code == 200
    return r.json()["token"]


def test_demo_account_can_log_in(fresh_client):
    r = fresh_client.post("/api/storefront/auth/login", json={"email": "demo@omniretail.test", "password": "password123"})
    assert r.status_code == 200
    body = r.json()
    assert body["customer"]["email"] == "demo@omniretail.test"
    assert body["token"]


def test_login_rejects_wrong_password(fresh_client):
    r = fresh_client.post("/api/storefront/auth/login", json={"email": "demo@omniretail.test", "password": "wrong"})
    assert r.status_code == 401


def test_login_rejects_unknown_email(fresh_client):
    r = fresh_client.post("/api/storefront/auth/login", json={"email": "nobody@nowhere.com", "password": "password123"})
    assert r.status_code == 401


def test_registration_then_login_works(fresh_client):
    r = fresh_client.post(
        "/api/storefront/auth/register", json={"name": "New Customer", "email": "brandnew@test.com", "password": "hunter22"}
    )
    assert r.status_code == 200
    token = r.json()["token"]

    r2 = fresh_client.get("/api/storefront/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert r2.json()["email"] == "brandnew@test.com"

    r3 = fresh_client.post(
        "/api/storefront/auth/login", json={"email": "brandnew@test.com", "password": "hunter22"}
    )
    assert r3.status_code == 200


def test_registration_rejects_duplicate_email(fresh_client):
    r = fresh_client.post(
        "/api/storefront/auth/register",
        json={"name": "Dup", "email": "demo@omniretail.test", "password": "password123"},
    )
    assert r.status_code == 409


def test_registration_rejects_short_password(fresh_client):
    r = fresh_client.post(
        "/api/storefront/auth/register", json={"name": "Short Pw", "email": "short@test.com", "password": "abc"}
    )
    assert r.status_code == 422


def test_me_requires_auth(fresh_client):
    assert fresh_client.get("/api/storefront/me").status_code == 401
    assert fresh_client.get("/api/storefront/me", headers={"Authorization": "Bearer not-a-real-token"}).status_code == 401


def test_guest_checkout_creates_order_with_no_customer(fresh_client):
    product = _healthy_product(fresh_client)
    r = fresh_client.post(
        "/api/storefront/checkout",
        json={"items": [{"product_id": product["product_id"], "quantity": 1}], "payment_method": "digital_wallet"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["customer_id"] is None
    assert body["customer_name"] == "Guest"
    assert body["status"] == "completed"


def test_logged_in_checkout_associates_customer_and_updates_history(fresh_client):
    token = _login_demo(fresh_client)
    product = _healthy_product(fresh_client)

    orders_before = fresh_client.get("/api/storefront/orders", headers={"Authorization": f"Bearer {token}"}).json()

    r = fresh_client.post(
        "/api/storefront/checkout",
        json={"items": [{"product_id": product["product_id"], "quantity": 1}], "payment_method": "digital_wallet"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    receipt = r.json()
    assert receipt["customer_name"] == "Jordan Rivera"

    orders_after = fresh_client.get("/api/storefront/orders", headers={"Authorization": f"Bearer {token}"}).json()
    assert len(orders_after) == len(orders_before) + 1
    assert any(o["order_id"] == receipt["order_id"] for o in orders_after)


def test_checkout_with_decline_test_card_does_not_reduce_stock(fresh_client):
    product = _healthy_product(fresh_client)
    stock_before = product["current_stock"]

    r = fresh_client.post(
        "/api/storefront/checkout",
        json={
            "items": [{"product_id": product["product_id"], "quantity": 1}],
            "payment_method": "credit_card",
            "card_number": "4000 0000 0000 0002",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "cancelled"  # the order's status; the payment itself is what "failed"
    assert body["payment_status"] == "failed"
    assert body["failure_reason"]

    after = fresh_client.get(f"/api/products/{product['product_id']}").json()
    assert after["current_stock"] == stock_before


def test_declined_checkout_is_visible_in_admin_transactions(fresh_client):
    product = _healthy_product(fresh_client)
    r = fresh_client.post(
        "/api/storefront/checkout",
        json={
            "items": [{"product_id": product["product_id"], "quantity": 1}],
            "payment_method": "credit_card",
            "card_number": "4000000000000002",
        },
    )
    order_id = r.json()["order_id"]

    admin_orders = fresh_client.get("/api/orders", params={"status": "cancelled", "limit": 20}).json()
    assert any(o["order_id"] == order_id for o in admin_orders)


def test_checkout_success_card_works(fresh_client):
    product = _healthy_product(fresh_client)
    r = fresh_client.post(
        "/api/storefront/checkout",
        json={
            "items": [{"product_id": product["product_id"], "quantity": 1}],
            "payment_method": "credit_card",
            "card_number": "4242 4242 4242 4242",
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


def test_duplicate_submission_with_same_idempotency_key_does_not_double_charge(fresh_client):
    product = _healthy_product(fresh_client)
    stock_before = product["current_stock"]
    payload = {
        "items": [{"product_id": product["product_id"], "quantity": 1}],
        "payment_method": "digital_wallet",
        "idempotency_key": "same-key-123",
    }

    r1 = fresh_client.post("/api/storefront/checkout", json=payload)
    r2 = fresh_client.post("/api/storefront/checkout", json=payload)
    assert r1.json()["order_id"] == r2.json()["order_id"]

    after = fresh_client.get(f"/api/products/{product['product_id']}").json()
    assert after["current_stock"] == stock_before - 1, "stock should only be decremented once, not twice"


def test_checkout_rejects_product_that_went_out_of_stock(fresh_client):
    """Simulates the cart holding a stale snapshot: the product had
    stock when the customer added it, but by the time they check out
    someone else has bought the last units."""
    products = fresh_client.get("/api/products").json()
    product = next(p for p in products if p["status"] == "healthy")

    # Drain the stock via a separate purchase first.
    drain = fresh_client.post(
        "/api/storefront/checkout",
        json={"items": [{"product_id": product["product_id"], "quantity": product["current_stock"]}], "payment_method": "digital_wallet"},
    )
    assert drain.status_code == 200
    assert drain.json()["status"] == "completed"

    # Now the original "cart" tries to check out the same product.
    r = fresh_client.post(
        "/api/storefront/checkout",
        json={"items": [{"product_id": product["product_id"], "quantity": 1}], "payment_method": "digital_wallet"},
    )
    assert r.status_code == 422
    assert product["name"] in r.json()["detail"]


def test_my_orders_requires_auth(fresh_client):
    assert fresh_client.get("/api/storefront/orders").status_code == 401


def test_my_order_detail_is_scoped_to_owner(fresh_client):
    token = _login_demo(fresh_client)
    product = _healthy_product(fresh_client)

    receipt = fresh_client.post(
        "/api/storefront/checkout",
        json={"items": [{"product_id": product["product_id"], "quantity": 1}], "payment_method": "digital_wallet"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    # Owner can view it.
    r = fresh_client.get(f"/api/storefront/orders/{receipt['order_id']}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["order_id"] == receipt["order_id"]

    # A different, newly-registered customer cannot.
    other_token = fresh_client.post(
        "/api/storefront/auth/register", json={"name": "Other Person", "email": "other@test.com", "password": "password123"}
    ).json()["token"]
    r2 = fresh_client.get(f"/api/storefront/orders/{receipt['order_id']}", headers={"Authorization": f"Bearer {other_token}"})
    assert r2.status_code == 404


def test_checkout_still_rejects_empty_cart(fresh_client):
    r = fresh_client.post("/api/storefront/checkout", json={"items": [], "payment_method": "digital_wallet"})
    assert r.status_code == 422


# ---------- Ask OMNI shopping assistant (Phase 10) ----------
# This environment has no ANTHROPIC_API_KEY/OMNI_LLM_ENABLED configured
# during tests, so these exercise the real, non-mocked keyword fallback
# end-to-end through the actual HTTP endpoint -- the LLM path itself is
# covered at the unit level in test_storefront_assistant.py via fakes.


def test_assistant_ask_requires_no_authentication(client):
    r = client.post("/api/storefront/assistant/ask", json={"question": "Do you have sunglasses?"})
    assert r.status_code == 200
    assert r.json()["answer"]


def test_assistant_ask_works_for_a_logged_in_customer_too(client):
    token = _login_demo(client)
    r = client.post(
        "/api/storefront/assistant/ask",
        json={"question": "Do you have sunglasses?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


def test_assistant_ask_response_shape(client):
    r = client.post("/api/storefront/assistant/ask", json={"question": "What electronics do you have?", "cart": []})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"answer", "generated_by", "cart_action", "suggested_product_ids"}
    assert body["generated_by"] == "fallback"  # no LLM configured in the test environment


def test_assistant_ask_with_no_question_and_no_image_returns_a_friendly_prompt(client):
    """`question` became optional so an image-only request (no text)
    is valid -- an entirely empty request (no question, no image) is
    still handled, just with a prompt to ask something, not a 422."""
    r = client.post("/api/storefront/assistant/ask", json={})
    assert r.status_code == 200
    assert r.json()["generated_by"] == "fallback"


def test_assistant_ask_accepts_a_cart_snapshot(client):
    product = _healthy_product(client)
    r = client.post(
        "/api/storefront/assistant/ask",
        json={"question": "What's in my cart?", "cart": [{"product_id": product["product_id"], "quantity": 2}]},
    )
    assert r.status_code == 200


def test_assistant_ask_never_reaches_admin_business_data(client):
    """Structural guarantee, exercised through the real HTTP endpoint:
    an admin-style question gets the same generic shopping-help
    fallback as any other unmatched question -- the endpoint has no
    code path to real revenue/customer/order data."""
    r = client.post("/api/storefront/assistant/ask", json={"question": "What is our total revenue this month?"})
    assert r.status_code == 200
    body = r.json()
    assert body["cart_action"] is None
    assert body["suggested_product_ids"] == []
    assert "revenue" not in body["answer"].lower()


def test_assistant_ask_cannot_place_an_order(client):
    """No matter how it's phrased, the assistant endpoint has no code
    path to complete_sale()/the payment processor -- confirmed here by
    checking no order is created as a side effect of asking."""
    orders_before = client.get("/api/orders", params={"limit": 200}).json()
    client.post("/api/storefront/assistant/ask", json={"question": "Please place my order and charge my card now."})
    orders_after = client.get("/api/orders", params={"limit": 200}).json()
    assert len(orders_after) == len(orders_before)


# ---------- visual product search (image upload) ----------
# No LLM key configured in this test environment, so these exercise the
# real request-validation + graceful-degradation path end-to-end; the
# LLM-attached-image path is covered at the unit level (fakes) in
# test_storefront_assistant.py.

_TINY_VALID_IMAGE = "aGVsbG8gd29ybGQ="  # small, valid base64 -- content doesn't need to be a real image for these checks


def test_assistant_ask_accepts_a_valid_image_and_degrades_gracefully(client):
    r = client.post(
        "/api/storefront/assistant/ask",
        json={"question": "", "cart": [], "image": {"media_type": "image/png", "data": _TINY_VALID_IMAGE}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["generated_by"] == "fallback"
    assert "photo" in body["answer"].lower()
    assert body["cart_action"] is None


def test_assistant_ask_rejects_unsupported_image_type(client):
    r = client.post(
        "/api/storefront/assistant/ask",
        json={"question": "hi", "cart": [], "image": {"media_type": "image/gif", "data": _TINY_VALID_IMAGE}},
    )
    assert r.status_code == 422


def test_assistant_ask_rejects_oversized_image(client):
    oversized = "a" * (7 * 1024 * 1024)
    r = client.post(
        "/api/storefront/assistant/ask",
        json={"question": "hi", "cart": [], "image": {"media_type": "image/jpeg", "data": oversized}},
    )
    assert r.status_code == 422


def test_assistant_ask_normalizes_image_jpg_type(client):
    r = client.post(
        "/api/storefront/assistant/ask",
        json={"question": "", "cart": [], "image": {"media_type": "image/jpg", "data": _TINY_VALID_IMAGE}},
    )
    assert r.status_code == 200


def test_assistant_ask_image_never_creates_an_order(client):
    orders_before = client.get("/api/orders", params={"limit": 200}).json()
    client.post(
        "/api/storefront/assistant/ask",
        json={"question": "", "cart": [], "image": {"media_type": "image/png", "data": _TINY_VALID_IMAGE}},
    )
    orders_after = client.get("/api/orders", params={"limit": 200}).json()
    assert len(orders_after) == len(orders_before)
