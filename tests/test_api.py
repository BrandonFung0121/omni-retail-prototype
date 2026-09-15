from omni_retail import services


def test_kpi_summary_matches_service_layer(client, session):
    response = client.get("/api/kpis/summary")
    assert response.status_code == 200
    body = response.json()

    assert body["revenue"] == services.revenue(session)
    assert body["orders"] == services.order_count(session)
    assert body["average_order_value"] == services.average_order_value(session)
    assert body["estimated_profit"] == services.estimated_profit(session)


def test_revenue_endpoint(client, session):
    response = client.get("/api/revenue")
    assert response.status_code == 200
    assert response.json() == {"revenue": services.revenue(session)}


def test_revenue_trend_endpoint_returns_sorted_days(client):
    response = client.get("/api/revenue/trend")
    assert response.status_code == 200
    points = response.json()
    assert len(points) > 0
    days = [p["day"] for p in points]
    assert days == sorted(days)


def test_order_count_and_average_value_endpoints(client, session):
    count_response = client.get("/api/orders/count")
    aov_response = client.get("/api/orders/average-value")
    assert count_response.json() == {"orders": services.order_count(session)}
    assert aov_response.json() == {"average_order_value": services.average_order_value(session)}


def test_top_products_endpoint(client):
    response = client.get("/api/products/top", params={"limit": 5, "by": "revenue"})
    assert response.status_code == 200
    products = response.json()
    assert 0 < len(products) <= 5
    revenues = [p["revenue"] for p in products]
    assert revenues == sorted(revenues, reverse=True)


def test_top_products_rejects_invalid_by_value(client):
    response = client.get("/api/products/top", params={"by": "not-a-real-option"})
    assert response.status_code == 422


def test_high_value_customers_endpoint(client):
    response = client.get("/api/customers/high-value", params={"limit": 5})
    assert response.status_code == 200
    customers = response.json()
    assert 0 < len(customers) <= 5
    spends = [c["total_spent"] for c in customers]
    assert spends == sorted(spends, reverse=True)


def test_inventory_status_endpoint_flags_low_and_out_of_stock(client):
    response = client.get("/api/inventory/status")
    assert response.status_code == 200
    body = response.json()
    assert body["low_stock"] > 0
    assert body["out_of_stock"] > 0
    assert len(body["low_stock_items"]) == body["low_stock"] + body["out_of_stock"]
    statuses = {item["status"] for item in body["low_stock_items"]}
    assert statuses <= {"low_stock", "out_of_stock"}


def test_expenses_endpoint_totals_match_categories(client):
    response = client.get("/api/expenses")
    assert response.status_code == 200
    body = response.json()
    assert round(sum(body["by_category"].values()), 2) == body["total"]


def test_estimated_profit_endpoint(client, session):
    response = client.get("/api/profit/estimated")
    assert response.status_code == 200
    body = response.json()
    assert body["estimated_profit"] == services.estimated_profit(session)
    assert round(body["revenue"] - body["cost_of_goods_sold"] - body["expenses"], 2) == body["estimated_profit"]


def test_website_traffic_endpoint(client):
    response = client.get("/api/website/traffic")
    assert response.status_code == 200
    body = response.json()
    assert body["visitors"] > 0
    assert 0 <= body["conversion_rate"] <= 100


def test_website_traffic_trend_endpoint(client):
    response = client.get("/api/website/traffic/trend")
    assert response.status_code == 200
    points = response.json()
    assert len(points) > 0


def test_conversion_rate_endpoint(client):
    response = client.get("/api/website/conversion-rate")
    assert response.status_code == 200
    body = response.json()
    assert 0 <= body["conversion_rate"] <= 100


def test_date_range_filters_are_applied(client):
    full = client.get("/api/revenue").json()["revenue"]
    narrow = client.get("/api/revenue", params={"start": "2999-01-01", "end": "2999-01-02"}).json()["revenue"]
    assert narrow == 0.0
    assert full > 0.0


def test_alerts_endpoint_matches_engine(client, session):
    from omni_retail.automation import run_all_rules

    response = client.get("/api/alerts")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(run_all_rules(session))
    assert body == sorted(body, key=lambda a: {"critical": 2, "warning": 1, "info": 0}[a["severity"]], reverse=True)
    for alert in body:
        assert alert["id"]
        assert alert["type"]
        assert alert["severity"] in {"critical", "warning", "info"}
        assert alert["supporting_data"]


def test_alerts_endpoint_filters_by_severity(client):
    response = client.get("/api/alerts", params={"severity": "critical"})
    assert response.status_code == 200
    body = response.json()
    assert len(body) > 0
    assert all(a["severity"] == "critical" for a in body)


def test_alerts_endpoint_filters_by_type(client):
    response = client.get("/api/alerts", params={"type": "low_stock"})
    assert response.status_code == 200
    body = response.json()
    assert len(body) > 0
    assert all(a["type"] == "low_stock" for a in body)


def test_alerts_summary_endpoint(client):
    alerts = client.get("/api/alerts").json()
    summary = client.get("/api/alerts/summary").json()

    assert summary["total"] == len(alerts)
    assert summary["critical"] == sum(1 for a in alerts if a["severity"] == "critical")
    assert summary["warning"] == sum(1 for a in alerts if a["severity"] == "warning")
    assert summary["info"] == sum(1 for a in alerts if a["severity"] == "info")
    assert sum(summary["by_type"].values()) == summary["total"]
