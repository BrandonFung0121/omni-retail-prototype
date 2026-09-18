"""Entry point for the customer-facing "Ask OMNI" shopping assistant.

Mirrors `ai/agent.py`'s shape (LLM path with a safe fallback when it's
unavailable) but is otherwise an independent, customer-scoped sibling:

- Its own tool registry (`ai/llm/storefront_tools.py`) -- search,
  product details, add-to-cart only. It structurally cannot reach any
  admin tool (business analytics, other customers, order lookup by
  id, propose_action) because those tools simply aren't registered
  here, not because of a runtime filter over a shared list.
- Its own system prompt, scoped to shopping only.
- No deterministic fallback pipeline: building a second
  intent/retrieval/synthesis stack just for shopping would duplicate
  the admin Phase 4 architecture for no real benefit. Instead, when
  the LLM is disabled/unavailable, `_fallback_answer()` below does a
  small, intentionally limited keyword search over the same
  `services.list_products()` -- product search, product details, and
  stock lookup only. No cart reasoning, no comparisons, no
  fabricated advice; it says plainly that it's a simplified mode.

Reuses the shared bounded tool-calling loop from `ai/llm/orchestrator.py`
and the exact same `LLMProvider`/`get_provider()`/`config` used by the
admin agent -- no second provider, no second config surface.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

from omni_retail import services
from omni_retail.ai.llm import config as llm_config
from omni_retail.ai.llm import get_provider
from omni_retail.ai.llm.orchestrator import OrchestrationLimitExceeded, run_tool_loop
from omni_retail.ai.llm.provider import ConversationTurn, LLMProviderError
from omni_retail.ai.llm.storefront_tools import dispatch_storefront_tool, get_storefront_tool_schemas

logger = logging.getLogger(__name__)

STOREFRONT_EXAMPLE_QUESTIONS = [
    "Do you have wireless headphones under $50?",
    "Is the Noise-Cancelling Headphones in stock?",
    "Which one is better for travelling?",
]

_BASE_SYSTEM_PROMPT = (
    "You are 'Ask OMNI', a friendly shopping assistant on the OMNI Retail storefront. "
    "You help customers search the product catalogue, check availability, understand product "
    "details, and add items to their cart. Use ONLY the provided tools for any factual claim "
    "about a product's name, price, or stock -- never invent or guess one. "
    "You may only discuss OMNI Retail's product catalogue and this customer's own cart. "
    "You must never discuss revenue, business performance, other customers, employees, internal "
    "operations, or anything about the admin/management side of the business -- if asked, say "
    "that's outside what you can help with here and offer to help with shopping instead. "
    "You can never place an order, confirm a purchase, or process a payment -- only the customer "
    "can do that, by completing checkout themselves; never claim to have done it for them. "
    "Call add_to_cart only after the customer clearly asks for an item to be added -- never on "
    "your own initiative. Keep answers short, warm, and conversational."
)

_MAX_ITERATIONS_CAP = 4
_MAX_TOOL_CALLS_CAP = 6
_MAX_SUGGESTED_PRODUCTS = 6


@dataclass
class CartAction:
    product_id: int
    product_name: str
    quantity: int
    unit_price: float


@dataclass
class StorefrontAgentResponse:
    answer: str
    generated_by: str  # "llm" | "fallback"
    cart_action: Optional[CartAction] = None
    suggested_product_ids: list[int] = field(default_factory=list)


def answer_shopping_question(
    session: Session,
    question: str,
    cart: Optional[list[dict[str, Any]]] = None,
) -> StorefrontAgentResponse:
    question = (question or "").strip()
    cart = cart or []

    if not question:
        return StorefrontAgentResponse(
            answer="Ask me to find a product, check what's in stock, or help you pick between a couple of options.",
            generated_by="fallback",
        )

    if llm_config.is_llm_enabled():
        provider = get_provider()
        if provider is not None:
            try:
                return _answer_with_llm(provider, session, question, cart)
            except (LLMProviderError, OrchestrationLimitExceeded) as exc:
                logger.warning(
                    "Storefront LLM path unavailable for question %r (%s: %s); falling back to keyword search.",
                    question,
                    type(exc).__name__,
                    exc,
                )

    return _fallback_answer(session, question)


def _answer_with_llm(provider, session: Session, question: str, cart: list[dict[str, Any]]) -> StorefrontAgentResponse:
    system_prompt = _build_system_prompt(session, cart)
    transcript = [ConversationTurn(role="user", text=question)]

    result = run_tool_loop(
        provider,
        transcript,
        system_prompt=system_prompt,
        tool_schemas=get_storefront_tool_schemas(),
        dispatch=lambda name, arguments: dispatch_storefront_tool(session, name, arguments),
        max_iterations=min(llm_config.max_iterations(), _MAX_ITERATIONS_CAP),
        max_tool_calls=min(llm_config.max_tool_calls(), _MAX_TOOL_CALLS_CAP),
    )

    cart_action = _extract_cart_action(result.tool_calls)
    suggested_ids = _extract_suggested_product_ids(result.tool_calls)

    return StorefrontAgentResponse(
        answer=result.text or "I couldn't quite find that -- try rephrasing, or ask me to search by category.",
        generated_by="llm",
        cart_action=cart_action,
        suggested_product_ids=suggested_ids,
    )


def _build_system_prompt(session: Session, cart: list[dict[str, Any]]) -> str:
    if not cart:
        return _BASE_SYSTEM_PROMPT + "\n\nThe customer's cart is currently empty."

    lines = []
    for item in cart[:20]:  # a customer's own cart is never large; this just bounds a malformed request
        product = services.get_product(session, product_id=item.get("product_id"))
        if product is None:
            continue
        quantity = item.get("quantity", 1)
        lines.append(f"- {product.name} x{quantity} (${product.selling_price:.2f} each)")

    if not lines:
        return _BASE_SYSTEM_PROMPT + "\n\nThe customer's cart is currently empty."

    return _BASE_SYSTEM_PROMPT + "\n\nThe customer's current cart contains:\n" + "\n".join(lines)


def _extract_cart_action(tool_calls) -> Optional[CartAction]:
    for record in reversed(tool_calls):
        if record.tool != "add_to_cart" or not record.ok:
            continue
        try:
            payload = json.loads(record.result)
        except (TypeError, ValueError):
            continue
        if payload.get("added"):
            return CartAction(
                product_id=payload["product_id"],
                product_name=payload["product_name"],
                quantity=payload["quantity"],
                unit_price=payload["unit_price"],
            )
        return None  # most recent add_to_cart call failed (e.g. out of stock) -- no action, not a fabricated one
    return None


def _extract_suggested_product_ids(tool_calls) -> list[int]:
    ids: list[int] = []
    for record in tool_calls:
        if record.tool not in ("search_products", "get_product_details") or not record.ok:
            continue
        try:
            payload = json.loads(record.result)
        except (TypeError, ValueError):
            continue
        if record.tool == "search_products":
            candidates = [p["product_id"] for p in payload.get("products", [])]
        elif payload.get("found"):
            candidates = [payload["product_id"]]
        else:
            candidates = []
        for pid in candidates:
            if pid not in ids:
                ids.append(pid)
    return ids[:_MAX_SUGGESTED_PRODUCTS]


# ---------- fallback: intentionally minimal keyword search, no LLM ----------

_PRICE_CEILING_RE = re.compile(r"(?:under|below|less than|cheaper than|up to)\D{0,6}?(\d+(?:\.\d+)?)", re.IGNORECASE)
_STOCK_KEYWORDS = ("in stock", "available", "how many", "left in stock", "out of stock")
_BROWSE_KEYWORDS = ("what products", "what do you have", "what do you sell", "show me", "browse", "catalog", "catalogue")
_CART_INTENT_KEYWORDS = ("add", "cart", "buy it", "purchase")


def _fallback_answer(session: Session, question: str) -> StorefrontAgentResponse:
    """No LLM reasoning here on purpose -- just enough to keep basic
    product search/details/availability working when the AI Shopping
    Assistant isn't configured. Never returns a cart_action: adding to
    cart and comparisons require actual judgment, which this path
    explicitly does not attempt -- see the cart-intent note appended
    below instead of silently doing nothing."""
    catalog = services.list_products(session)
    text = question.lower()

    named_match = _match_named_product(catalog, text)
    if named_match is not None:
        return _fallback_product_detail(named_match, cart_intent=any(k in text for k in _CART_INTENT_KEYWORDS))

    if any(k in text for k in _BROWSE_KEYWORDS):
        return _fallback_search_results(catalog[:6])

    price_match = _PRICE_CEILING_RE.search(text)
    max_price = float(price_match.group(1)) if price_match else None

    category_match = next((c for c in _categories(catalog) if c.lower() in text), None)

    query_words = [w for w in re.findall(r"[a-z]+", text) if len(w) > 2]
    keyword_matches = [
        p for p in catalog if any(w in p.name.lower() for w in query_words) or any(w in p.category.lower() for w in query_words)
    ]

    if max_price is not None or category_match or keyword_matches:
        if category_match:
            results = [p for p in catalog if p.category.lower() == category_match.lower()]
        elif keyword_matches:
            results = keyword_matches
        else:
            results = catalog
        if max_price is not None:
            results = [p for p in results if p.selling_price <= max_price]
        return _fallback_search_results(results[:6])

    if any(k in text for k in _STOCK_KEYWORDS):
        return StorefrontAgentResponse(
            answer="Tell me which product you'd like to check -- for example, \"Is the Wireless Earbuds Pro in stock?\"",
            generated_by="fallback",
        )

    categories = ", ".join(sorted(_categories(catalog)))
    return StorefrontAgentResponse(
        answer=(
            "I'm running in simplified mode right now, so I can help with product search and availability "
            f"-- try a category ({categories}), a price ('under $50'), or a product name."
        ),
        generated_by="fallback",
    )


def _categories(catalog) -> set[str]:
    return {p.category for p in catalog}


def _match_named_product(catalog, text: str):
    for product in catalog:
        name_words = [w for w in re.findall(r"[a-z]+", product.name.lower()) if len(w) > 3]
        if name_words and all(w in text for w in name_words):
            return product
    return None


def _fallback_product_detail(product, cart_intent: bool = False) -> StorefrontAgentResponse:
    stock_line = {
        "healthy": f"In stock ({product.current_stock} available).",
        "low_stock": f"Low stock -- only {product.current_stock} left.",
        "out_of_stock": "Currently out of stock.",
    }.get(product.status, f"{product.current_stock} in stock.")

    answer = f"{product.name} ({product.category}) -- ${product.selling_price:.2f}. {stock_line}"
    if cart_intent:
        answer += " I can't add items to your cart in simplified mode -- use the Add to Cart button below or on the product page."

    return StorefrontAgentResponse(
        answer=answer,
        generated_by="fallback",
        suggested_product_ids=[product.product_id],
    )


def _fallback_search_results(results) -> StorefrontAgentResponse:
    if not results:
        return StorefrontAgentResponse(
            answer="I couldn't find anything matching that in simplified mode -- try a broader term or a category name.",
            generated_by="fallback",
        )

    listing = "; ".join(f"{p.name} (${p.selling_price:.2f}, {p.status.replace('_', ' ')})" for p in results)
    return StorefrontAgentResponse(
        answer=f"Here's what I found: {listing}.",
        generated_by="fallback",
        suggested_product_ids=[p.product_id for p in results],
    )
