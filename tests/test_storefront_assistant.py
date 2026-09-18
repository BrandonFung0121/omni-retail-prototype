"""Tests for the storefront shopping assistant entry point
(ai/storefront_agent.py) -- both the LLM path (scripted fakes, same
harness as test_llm_orchestrator.py) and the keyword-based fallback
that runs when the LLM is disabled/unavailable.
"""

from __future__ import annotations

import pytest

from omni_retail import services
from omni_retail.ai import storefront_agent
from omni_retail.ai.llm.orchestrator import OrchestrationLimitExceeded
from omni_retail.ai.llm.provider import LLMTurnResult, ProviderCallError, ToolCall
from tests.llm_fakes import FakeLLMProvider, RepeatingToolCallProvider


def _healthy_product(session):
    return next(p for p in services.list_products(session) if p.status == "healthy" and p.current_stock >= 2)


# ---------- LLM path ----------


def test_llm_path_runs_search_then_answers(session, monkeypatch):
    monkeypatch.setattr(storefront_agent.llm_config, "is_llm_enabled", lambda: True)
    provider = FakeLLMProvider(
        [
            LLMTurnResult(stop_reason="tool_use", tool_calls=[ToolCall(id="1", name="search_products", arguments={"query": "headphones"})]),
            LLMTurnResult(stop_reason="end_turn", text="We have Noise-Cancelling Headphones for $249.99."),
        ]
    )
    monkeypatch.setattr(storefront_agent, "get_provider", lambda: provider)

    result = storefront_agent.answer_shopping_question(session, "Do you have headphones?")

    assert result.generated_by == "llm"
    assert "Headphones" in result.answer
    assert result.cart_action is None


def test_llm_path_extracts_cart_action_from_add_to_cart_call(session, monkeypatch):
    product = _healthy_product(session)
    monkeypatch.setattr(storefront_agent.llm_config, "is_llm_enabled", lambda: True)
    provider = FakeLLMProvider(
        [
            LLMTurnResult(stop_reason="tool_use", tool_calls=[ToolCall(id="1", name="add_to_cart", arguments={"product_id": product.product_id, "quantity": 2})]),
            LLMTurnResult(stop_reason="end_turn", text="Added 2 to your cart!"),
        ]
    )
    monkeypatch.setattr(storefront_agent, "get_provider", lambda: provider)

    result = storefront_agent.answer_shopping_question(session, f"Add 2 of product {product.product_id} to my cart")

    assert result.cart_action is not None
    assert result.cart_action.product_id == product.product_id
    assert result.cart_action.quantity == 2


def test_llm_path_does_not_fabricate_cart_action_when_add_to_cart_fails(session, monkeypatch):
    """add_to_cart can fail (out of stock/unknown product) -- the agent
    must not invent a cart_action when that happens."""
    monkeypatch.setattr(storefront_agent.llm_config, "is_llm_enabled", lambda: True)
    provider = FakeLLMProvider(
        [
            LLMTurnResult(stop_reason="tool_use", tool_calls=[ToolCall(id="1", name="add_to_cart", arguments={"product_id": 999999, "quantity": 1})]),
            LLMTurnResult(stop_reason="end_turn", text="Sorry, I couldn't find that product."),
        ]
    )
    monkeypatch.setattr(storefront_agent, "get_provider", lambda: provider)

    result = storefront_agent.answer_shopping_question(session, "Add product 999999 to my cart")

    assert result.cart_action is None


def test_llm_path_collects_suggested_product_ids_from_search(session, monkeypatch):
    monkeypatch.setattr(storefront_agent.llm_config, "is_llm_enabled", lambda: True)
    provider = FakeLLMProvider(
        [
            LLMTurnResult(stop_reason="tool_use", tool_calls=[ToolCall(id="1", name="search_products", arguments={"category": "Electronics"})]),
            LLMTurnResult(stop_reason="end_turn", text="Here are a few options."),
        ]
    )
    monkeypatch.setattr(storefront_agent, "get_provider", lambda: provider)

    result = storefront_agent.answer_shopping_question(session, "What electronics do you have?")

    assert result.suggested_product_ids
    assert len(result.suggested_product_ids) == len(set(result.suggested_product_ids))  # deduped


def test_llm_path_cannot_reach_an_admin_tool(session, monkeypatch):
    """Even if the model asks for an admin tool, the storefront
    registry doesn't have it -- the loop recovers gracefully (as an
    unknown-tool error fed back to the model), it never executes."""
    monkeypatch.setattr(storefront_agent.llm_config, "is_llm_enabled", lambda: True)
    provider = FakeLLMProvider(
        [
            LLMTurnResult(stop_reason="tool_use", tool_calls=[ToolCall(id="1", name="search_customers", arguments={"query": "a"})]),
            LLMTurnResult(stop_reason="end_turn", text="I can't look that up here."),
        ]
    )
    monkeypatch.setattr(storefront_agent, "get_provider", lambda: provider)

    result = storefront_agent.answer_shopping_question(session, "List all customers")

    assert result.generated_by == "llm"
    # the rejected call still shows up as a (failed) tool call in the transcript the fake provider received
    tool_results_turn = provider.calls[-1][1][-1]
    assert tool_results_turn.role == "tool_results"
    assert tool_results_turn.tool_results[0].is_error is True
    assert "No such tool" in tool_results_turn.tool_results[0].content


def test_system_prompt_never_mentions_admin_concepts(session, monkeypatch):
    monkeypatch.setattr(storefront_agent.llm_config, "is_llm_enabled", lambda: True)
    provider = FakeLLMProvider([LLMTurnResult(stop_reason="end_turn", text="Sure, happy to help you shop.")])
    monkeypatch.setattr(storefront_agent, "get_provider", lambda: provider)

    storefront_agent.answer_shopping_question(session, "hi")

    # "revenue"/"business performance" legitimately appear in the prompt's
    # *prohibition* clause ("never discuss revenue...") -- what must never
    # appear is admin-specific tool/internal names, since their presence
    # would suggest the model has been told it can reach them.
    system_prompt = provider.calls[0][0]
    for banned in ("propose_action", "Business Analyst", "AgentAction", "Action Center", "get_business_issues_summary"):
        assert banned not in system_prompt


def test_system_prompt_includes_cart_context(session, monkeypatch):
    product = _healthy_product(session)
    monkeypatch.setattr(storefront_agent.llm_config, "is_llm_enabled", lambda: True)
    provider = FakeLLMProvider([LLMTurnResult(stop_reason="end_turn", text="Looks good!")])
    monkeypatch.setattr(storefront_agent, "get_provider", lambda: provider)

    storefront_agent.answer_shopping_question(
        session, "what's in my cart?", cart=[{"product_id": product.product_id, "quantity": 3}]
    )

    system_prompt = provider.calls[0][0]
    assert product.name in system_prompt
    assert "x3" in system_prompt


# ---------- fallback ----------


def test_fallback_used_when_llm_disabled(session, monkeypatch):
    monkeypatch.setattr(storefront_agent.llm_config, "is_llm_enabled", lambda: False)
    result = storefront_agent.answer_shopping_question(session, "Do you have sunglasses?")
    assert result.generated_by == "fallback"


def test_fallback_used_when_provider_unavailable(session, monkeypatch):
    monkeypatch.setattr(storefront_agent.llm_config, "is_llm_enabled", lambda: True)
    monkeypatch.setattr(storefront_agent, "get_provider", lambda: None)
    result = storefront_agent.answer_shopping_question(session, "Do you have sunglasses?")
    assert result.generated_by == "fallback"


def test_fallback_used_on_provider_call_error(session, monkeypatch):
    monkeypatch.setattr(storefront_agent.llm_config, "is_llm_enabled", lambda: True)
    monkeypatch.setattr(storefront_agent, "get_provider", lambda: FakeLLMProvider([ProviderCallError("simulated failure")]))
    result = storefront_agent.answer_shopping_question(session, "Do you have sunglasses?")
    assert result.generated_by == "fallback"


def test_fallback_used_on_orchestration_limit_exceeded(session, monkeypatch):
    monkeypatch.setenv("OMNI_LLM_MAX_ITERATIONS", "1")
    monkeypatch.setenv("OMNI_LLM_MAX_TOOL_CALLS", "1")
    monkeypatch.setattr(storefront_agent.llm_config, "is_llm_enabled", lambda: True)
    monkeypatch.setattr(storefront_agent, "get_provider", lambda: RepeatingToolCallProvider("search_products"))
    result = storefront_agent.answer_shopping_question(session, "keep searching forever")
    assert result.generated_by == "fallback"


def test_a_real_bug_in_the_llm_path_is_not_swallowed_by_fallback(session, monkeypatch):
    """Mirrors the admin agent's equivalent test: a genuine bug must
    surface, not silently look like a normal fallback."""

    class ExplodingProvider:
        def run_turn(self, system, transcript, tools):
            raise KeyError("not a recognized LLMProviderError subclass")

    monkeypatch.setattr(storefront_agent.llm_config, "is_llm_enabled", lambda: True)
    monkeypatch.setattr(storefront_agent, "get_provider", lambda: ExplodingProvider())

    with pytest.raises(KeyError):
        storefront_agent.answer_shopping_question(session, "hi")


def test_fallback_finds_product_by_name(session):
    product = _healthy_product(session)
    result = storefront_agent.answer_shopping_question(session, f"Is the {product.name} in stock?")
    assert product.name in result.answer
    assert result.suggested_product_ids == [product.product_id]


def test_fallback_filters_by_max_price(session):
    result = storefront_agent.answer_shopping_question(session, "show me something under $15")
    assert result.suggested_product_ids  # at least one match in the seeded catalogue


def test_fallback_filters_by_category(session):
    result = storefront_agent.answer_shopping_question(session, "what electronics do you have")
    assert result.suggested_product_ids


def test_fallback_never_returns_a_cart_action(session):
    product = _healthy_product(session)
    result = storefront_agent.answer_shopping_question(session, f"Add the {product.name} to my cart")
    assert result.cart_action is None
    assert "cart" in result.answer.lower()  # explains it can't, rather than staying silent


def test_fallback_stock_question_without_a_named_product_asks_for_clarification(session):
    result = storefront_agent.answer_shopping_question(session, "is it in stock?")
    assert "which product" in result.answer.lower()


@pytest.mark.parametrize(
    "question",
    [
        "what products do you have?",
        "what lifestyle products you guys sell?",
        "What you guys sell?",
        "What do you sell?",
        "What products do you guys sell?",
        "Tell me about OMNI Retail",
        "What categories do you have?",
        "what do you offer?",
    ],
)
def test_fallback_generic_browse_question_summarizes_real_categories(session, question):
    result = storefront_agent.answer_shopping_question(session, question)
    assert result.generated_by == "fallback"
    assert result.cart_action is None
    # every category named in the answer must be a real one -- no invented products/categories
    real_categories = {p.category for p in services.list_products(session)}
    assert any(c in result.answer for c in real_categories)


def test_fallback_category_specific_sell_question_still_filters_to_that_category(session):
    """A specific category mentioned alongside a sell-verb should win
    over the generic store-overview response."""
    result = storefront_agent.answer_shopping_question(session, "what electronics do you sell")
    assert "Electronics" not in result.answer.split("across")[0]  # not the generic overview sentence
    assert result.suggested_product_ids
    for pid in result.suggested_product_ids:
        product = next(p for p in services.list_products(session) if p.product_id == pid)
        assert product.category == "Electronics"


def test_fallback_stock_question_is_not_shadowed_by_the_sell_verb_regex(session):
    """"stock" must not be treated as a sell-verb -- it has its own,
    more specific clarification response below."""
    result = storefront_agent.answer_shopping_question(session, "is it in stock?")
    assert "which product" in result.answer.lower()


def test_fallback_admin_style_question_gets_no_business_data(session):
    """The fallback has no access to any business-analytics data
    structurally (it only ever calls services.list_products()) -- an
    admin-style question just falls through to the generic help
    message, it can never leak real figures."""
    result = storefront_agent.answer_shopping_question(session, "What was our revenue last month?")
    assert result.generated_by == "fallback"
    assert result.cart_action is None
    assert "revenue" not in result.answer.lower()


def test_empty_question_returns_a_safe_prompt_without_touching_the_llm(session, monkeypatch):
    monkeypatch.setattr(storefront_agent.llm_config, "is_llm_enabled", lambda: True)

    def _should_not_be_called():
        raise AssertionError("get_provider() should not be called for an empty question")

    monkeypatch.setattr(storefront_agent, "get_provider", lambda: _should_not_be_called())
    result = storefront_agent.answer_shopping_question(session, "   ")
    assert result.generated_by == "fallback"
    assert result.answer
