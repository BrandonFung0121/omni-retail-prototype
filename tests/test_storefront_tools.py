"""Tests for the customer-facing storefront tool registry
(ai/llm/storefront_tools.py) -- separate from and structurally unable
to reach the admin registry (ai/llm/tools.py).
"""

from __future__ import annotations

import json

import pytest

from omni_retail import services
from omni_retail.ai.llm.storefront_tools import (
    TOOL_REGISTRY,
    dispatch_storefront_tool,
    get_storefront_tool_schemas,
)
from omni_retail.ai.llm.tool_kit import ToolArgumentError, UnknownToolError


def _healthy_product_id(session):
    return next(p.product_id for p in services.list_products(session) if p.status == "healthy" and p.current_stock >= 2)


def _out_of_stock_product_id(session):
    return next(p.product_id for p in services.list_products(session) if p.status == "out_of_stock")


def test_registry_contains_only_the_three_customer_safe_tools():
    assert set(TOOL_REGISTRY) == {"search_products", "get_product_details", "add_to_cart"}


def test_schemas_are_json_serializable_and_named():
    schemas = get_storefront_tool_schemas()
    names = {s["name"] for s in schemas}
    assert names == {"search_products", "get_product_details", "add_to_cart"}
    for schema in schemas:
        assert "input_schema" in schema and "description" in schema


@pytest.mark.parametrize("admin_tool", ["search_customers", "get_order", "get_business_issues_summary", "propose_action", "get_revenue_explanation"])
def test_admin_only_tools_are_unreachable(session, admin_tool):
    with pytest.raises(UnknownToolError):
        dispatch_storefront_tool(session, admin_tool, {})


def test_search_products_filters_by_query(session):
    payload = json.loads(dispatch_storefront_tool(session, "search_products", {"query": "headphones"}))
    assert payload["count"] >= 1
    assert all("headphones" in p["name"].lower() or "headphones" in p["category"].lower() for p in payload["products"])


def test_search_products_filters_by_max_price(session):
    payload = json.loads(dispatch_storefront_tool(session, "search_products", {"max_price": 20}))
    assert payload["products"]
    assert all(p["selling_price"] <= 20 for p in payload["products"])


def test_search_products_filters_by_category(session):
    payload = json.loads(dispatch_storefront_tool(session, "search_products", {"category": "Electronics"}))
    assert payload["products"]
    assert all(p["category"] == "Electronics" for p in payload["products"])


def test_search_products_limit_argument_cannot_exceed_registry_max(session):
    with pytest.raises(ToolArgumentError):
        dispatch_storefront_tool(session, "search_products", {"limit": 99})


def test_search_products_defaults_to_registry_max_results(session):
    payload = json.loads(dispatch_storefront_tool(session, "search_products", {}))
    assert len(payload["products"]) <= 8


def test_search_products_result_excludes_cost_and_reorder_threshold(session):
    payload = json.loads(dispatch_storefront_tool(session, "search_products", {}))
    for product in payload["products"]:
        assert "cost" not in product
        assert "reorder_threshold" not in product


def test_get_product_details_found(session):
    product_id = _healthy_product_id(session)
    payload = json.loads(dispatch_storefront_tool(session, "get_product_details", {"product_id": product_id}))
    assert payload["found"] is True
    assert payload["product_id"] == product_id
    assert "cost" not in payload
    assert "reorder_threshold" not in payload


def test_get_product_details_not_found(session):
    payload = json.loads(dispatch_storefront_tool(session, "get_product_details", {"product_id": 999999}))
    assert payload == {"found": False, "product_id": 999999}


def test_get_product_details_requires_product_id(session):
    with pytest.raises(ToolArgumentError):
        dispatch_storefront_tool(session, "get_product_details", {})


def test_add_to_cart_succeeds_for_in_stock_product(session):
    product_id = _healthy_product_id(session)
    payload = json.loads(dispatch_storefront_tool(session, "add_to_cart", {"product_id": product_id, "quantity": 2}))
    assert payload["added"] is True
    assert payload["product_id"] == product_id
    assert payload["quantity"] == 2
    assert "unit_price" in payload


def test_add_to_cart_defaults_quantity_to_one(session):
    product_id = _healthy_product_id(session)
    payload = json.loads(dispatch_storefront_tool(session, "add_to_cart", {"product_id": product_id}))
    assert payload["quantity"] == 1


def test_add_to_cart_rejects_insufficient_stock(session):
    product = next(p for p in services.list_products(session) if p.status == "low_stock")
    payload = json.loads(
        dispatch_storefront_tool(session, "add_to_cart", {"product_id": product.product_id, "quantity": product.current_stock + 1})
    )
    assert payload["added"] is False
    assert "stock" in payload["reason"].lower()


def test_add_to_cart_rejects_out_of_stock_product(session):
    product_id = _out_of_stock_product_id(session)
    payload = json.loads(dispatch_storefront_tool(session, "add_to_cart", {"product_id": product_id, "quantity": 1}))
    assert payload["added"] is False


def test_add_to_cart_rejects_unknown_product(session):
    payload = json.loads(dispatch_storefront_tool(session, "add_to_cart", {"product_id": 999999, "quantity": 1}))
    assert payload["added"] is False


def test_add_to_cart_rejects_zero_quantity(session):
    product_id = _healthy_product_id(session)
    with pytest.raises(ToolArgumentError):
        dispatch_storefront_tool(session, "add_to_cart", {"product_id": product_id, "quantity": 0})


def test_add_to_cart_never_writes_to_the_database(session):
    """The storefront cart is client-side (localStorage); this tool
    must never touch Order/Inventory -- it only validates and returns
    a directive. Confirmed here by checking stock is unchanged."""
    product_id = _healthy_product_id(session)
    before = services.get_product(session, product_id).current_stock
    dispatch_storefront_tool(session, "add_to_cart", {"product_id": product_id, "quantity": 1})
    after = services.get_product(session, product_id).current_stock
    assert before == after
