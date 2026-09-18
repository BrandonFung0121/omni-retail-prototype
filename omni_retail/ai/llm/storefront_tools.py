"""Tool schemas + registry for the customer-facing "Ask OMNI" shopping
assistant.

Deliberately a SEPARATE registry from `ai/llm/tools.py` (the admin
one), not a filtered view of it: `search_products`, `get_product_details`,
and `add_to_cart` are the only three tools that exist here. There is no
code path by which the storefront agent can reach `search_customers`,
`get_order`, any business-analytics tool, or `propose_action` -- they
are simply never registered in this module.

Both read tools wrap the exact same `services.list_products()`/
`services.get_product()` that already power the public, unauthenticated
`GET /api/products` and `GET /api/products/{id}` endpoints the
storefront catalogue itself calls -- no new query, no new exposure.
Unlike the admin `get_product` tool, the payload here deliberately
excludes `reorder_threshold`: it's an internal merchandising detail a
customer has no reason to see (the storefront UI never shows it
either), even though it isn't deeply sensitive.

`add_to_cart` never touches the database. The storefront cart is
client-side (`localStorage`) with no server representation at all --
see `transactions/service.py::complete_sale()`, which only ever sees a
cart built fresh from the checkout request. So this tool only
validates the product/quantity and returns a directive; the actual
`storefront/assistant.js` applies it locally through the same
`addToCart()` the catalogue's "Add to Cart" button already uses. This
is also what makes the checkout guardrail structural rather than just
prompted: no tool in this registry has access to `complete_sale()` or
any payment processor, so the assistant cannot place an order no
matter what it's asked.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from omni_retail import services
from omni_retail.ai.llm.tool_kit import ToolSpec, build_schemas
from omni_retail.ai.llm.tool_kit import dispatch as _dispatch

_MAX_SEARCH_RESULTS = 8


def _customer_safe_product(entry) -> dict[str, Any]:
    """The customer-facing view of a `ProductCatalogEntry` -- name,
    category, price, and live stock only. No cost/margin field exists
    on this dataclass to begin with; `reorder_threshold` does, and is
    intentionally dropped here (see module docstring)."""
    return {
        "product_id": entry.product_id,
        "name": entry.name,
        "category": entry.category,
        "selling_price": entry.selling_price,
        "current_stock": entry.current_stock,
        "status": entry.status,
    }


def _handle_search_products(session: Session, arguments: dict[str, Any]) -> Any:
    query = (arguments.get("query") or "").strip().lower()
    category = (arguments.get("category") or "").strip().lower()
    max_price = arguments.get("max_price")
    # The "limit" schema property already enforces 1-_MAX_SEARCH_RESULTS,
    # so any value that reaches here is already in range.
    limit = arguments.get("limit") or _MAX_SEARCH_RESULTS

    catalog = services.list_products(session)
    matches = [
        p
        for p in catalog
        if (not query or query in p.name.lower() or query in p.category.lower())
        and (not category or category in p.category.lower())
        and (max_price is None or p.selling_price <= max_price)
    ]

    return {
        "products": [_customer_safe_product(p) for p in matches[:limit]],
        "count": len(matches),
    }


def _handle_get_product_details(session: Session, arguments: dict[str, Any]) -> Any:
    product = services.get_product(session, product_id=arguments["product_id"])
    if product is None:
        return {"found": False, "product_id": arguments["product_id"]}
    return {"found": True, **_customer_safe_product(product)}


def _handle_add_to_cart(session: Session, arguments: dict[str, Any]) -> Any:
    product_id = arguments["product_id"]
    quantity = arguments.get("quantity", 1)

    product = services.get_product(session, product_id=product_id)
    if product is None:
        return {"added": False, "product_id": product_id, "reason": "No such product."}
    if product.current_stock < quantity:
        return {
            "added": False,
            "product_id": product_id,
            "product_name": product.name,
            "reason": f"Only {product.current_stock} left in stock, cannot add {quantity}.",
        }

    return {
        "added": True,
        "product_id": product.product_id,
        "product_name": product.name,
        "quantity": quantity,
        "unit_price": product.selling_price,
    }


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "search_products": ToolSpec(
        name="search_products",
        description=(
            "Search OMNI's product catalogue by name/category keyword and/or a maximum price. "
            "Use this whenever the customer is browsing or asking 'do you have...'."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text to match against product name or category, e.g. 'headphones'."},
                "category": {"type": "string", "description": "Restrict to one category, e.g. 'Electronics'."},
                "max_price": {"type": "number", "description": "Only return products at or under this price.", "minimum": 0},
                "limit": {"type": "integer", "description": f"Max results (default/{_MAX_SEARCH_RESULTS} max).", "minimum": 1, "maximum": _MAX_SEARCH_RESULTS},
            },
            "required": [],
        },
        handler=_handle_search_products,
        read_only=True,
    ),
    "get_product_details": ToolSpec(
        name="get_product_details",
        description="Get one product's full details and current availability by its id -- use after search_products to answer a specific question about one item, or to check stock.",
        input_schema={
            "type": "object",
            "properties": {"product_id": {"type": "integer", "description": "The product's id."}},
            "required": ["product_id"],
        },
        handler=_handle_get_product_details,
        read_only=True,
    ),
    "add_to_cart": ToolSpec(
        name="add_to_cart",
        description=(
            "Add a specific quantity of one product to the customer's cart. Only call this after the customer "
            "has clearly asked for an item to be added -- never on your own initiative. This does not place an "
            "order or charge anything; the customer still completes checkout themselves."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "product_id": {"type": "integer", "description": "The product's id."},
                "quantity": {"type": "integer", "description": "How many to add (default 1).", "minimum": 1, "maximum": 99},
            },
            "required": ["product_id"],
        },
        handler=_handle_add_to_cart,
        read_only=False,
    ),
}


def get_storefront_tool_schemas() -> list[dict[str, Any]]:
    return build_schemas(TOOL_REGISTRY)


def dispatch_storefront_tool(session: Session, name: str, arguments: dict[str, Any]) -> str:
    return _dispatch(TOOL_REGISTRY, session, name, arguments)
