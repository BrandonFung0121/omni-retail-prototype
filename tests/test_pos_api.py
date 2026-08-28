def _healthy_product(client):
    products = client.get("/api/products").json()
    return next(p for p in products if p["status"] == "healthy")


def test_get_products_returns_catalog_with_stock(fresh_client):
    response = fresh_client.get("/api/products")
    assert response.status_code == 200
    body = response.json()
    assert len(body) > 0
    assert {"product_id", "name", "selling_price", "current_stock", "status"} <= body[0].keys()


def test_search_customers_endpoint(fresh_client):
    response = fresh_client.get("/api/customers/search", params={"q": "", "limit": 5})
    assert response.status_code == 200
    assert len(response.json()) == 5


def test_checkout_completes_a_sale(fresh_client):
    product = _healthy_product(fresh_client)
    response = fresh_client.post(
        "/api/pos/checkout",
        json={"items": [{"product_id": product["product_id"], "quantity": 2}], "payment_method": "cash"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["customer_name"] == "Guest"
    assert body["total"] == round(product["selling_price"] * 2, 2)
    assert len(body["lines"]) == 1


def test_checkout_then_order_appears_in_transactions_list(fresh_client):
    product = _healthy_product(fresh_client)
    receipt = fresh_client.post(
        "/api/pos/checkout",
        json={"items": [{"product_id": product["product_id"], "quantity": 1}], "payment_method": "cash"},
    ).json()

    orders = fresh_client.get("/api/orders", params={"limit": 5}).json()
    assert any(o["order_id"] == receipt["order_id"] for o in orders)

    detail = fresh_client.get(f"/api/orders/{receipt['order_id']}").json()
    assert detail["total"] == receipt["total"]
    assert len(detail["lines"]) == 1


def test_checkout_then_kpis_reflect_the_sale(fresh_client):
    revenue_before = fresh_client.get("/api/revenue").json()["revenue"]
    product = _healthy_product(fresh_client)
    receipt = fresh_client.post(
        "/api/pos/checkout",
        json={"items": [{"product_id": product["product_id"], "quantity": 1}], "payment_method": "cash"},
    ).json()

    revenue_after = fresh_client.get("/api/revenue").json()["revenue"]
    assert round(revenue_after - revenue_before, 2) == receipt["total"]


def test_checkout_rejects_empty_cart(fresh_client):
    response = fresh_client.post("/api/pos/checkout", json={"items": [], "payment_method": "cash"})
    assert response.status_code == 422
    assert "empty" in response.json()["detail"].lower()


def test_checkout_rejects_insufficient_stock(fresh_client):
    product = _healthy_product(fresh_client)
    response = fresh_client.post(
        "/api/pos/checkout",
        json={"items": [{"product_id": product["product_id"], "quantity": product["current_stock"] + 1}], "payment_method": "cash"},
    )
    assert response.status_code == 422
    assert product["name"] in response.json()["detail"]


def test_checkout_rejects_unknown_product(fresh_client):
    response = fresh_client.post(
        "/api/pos/checkout", json={"items": [{"product_id": 999999, "quantity": 1}], "payment_method": "cash"}
    )
    assert response.status_code == 422


def test_checkout_rejects_invalid_discount(fresh_client):
    product = _healthy_product(fresh_client)
    response = fresh_client.post(
        "/api/pos/checkout",
        json={
            "items": [{"product_id": product["product_id"], "quantity": 1}],
            "payment_method": "cash",
            "discount_type": "percent",
            "discount_value": 150,
        },
    )
    assert response.status_code == 422


def test_checkout_rejects_unknown_customer(fresh_client):
    product = _healthy_product(fresh_client)
    response = fresh_client.post(
        "/api/pos/checkout",
        json={"items": [{"product_id": product["product_id"], "quantity": 1}], "payment_method": "cash", "customer_id": 999999},
    )
    assert response.status_code == 422


def test_get_order_404_for_unknown_id(fresh_client):
    response = fresh_client.get("/api/orders/999999")
    assert response.status_code == 404


def test_orders_endpoint_filters_by_status(fresh_client):
    response = fresh_client.get("/api/orders", params={"status": "cancelled", "limit": 10})
    assert response.status_code == 200
    body = response.json()
    assert len(body) > 0
    assert all(o["status"] == "cancelled" for o in body)
