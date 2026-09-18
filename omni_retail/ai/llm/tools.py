"""Tool schemas + registry the LLM orchestrator is allowed to call.

Every read-only tool wraps an existing `ai/retrieval.py` gatherer and
runs it straight through the existing `TemplateAnswerSynthesizer` --
the exact same deterministic evidence-gathering and JSON-safe
summarization Phase 4 already uses and already tests
(`json.dumps(response.supporting_metrics)` in test_ai_agent.py covers
every intent branch). No analytics or business logic is duplicated
here: this module only describes each capability as a JSON-schema tool
and dispatches to the real function.

`propose_action` is the one write-shaped tool, and it is deliberately
narrow: it can only call `actions.service.create_manual_proposal()`,
which can only construct an `AgentAction` with `status=PROPOSED` (that
status is hardcoded there, not a caller-supplied parameter). There is
no tool here for approving or executing an action -- `approve_action`
and `execute_action` are simply never registered, so no model output
can express "approve #42" in the first place. See
`actions/service.py::create_manual_proposal` for the second,
independent layer of enforcement (the APPROVED-only guard on
`execute_action`).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from omni_retail import services
from omni_retail.actions.models import ProposalDraft
from omni_retail.actions.service import create_manual_proposal
from omni_retail.ai.intents import Intent
from omni_retail.ai.llm.tool_kit import (
    _EMPTY_SCHEMA,
    ToolArgumentError,
    ToolSpec,
    UnknownToolError,
    build_schemas,
    to_jsonable,
)
from omni_retail.ai.llm.tool_kit import dispatch as _dispatch
from omni_retail.ai.retrieval import RETRIEVERS
from omni_retail.ai.synthesis import TemplateAnswerSynthesizer
from omni_retail.models import ActionType, Customer, RiskLevel


def _synthesis_payload(question: str, intent: Intent, evidence: dict[str, Any]) -> dict[str, Any]:
    result = TemplateAnswerSynthesizer().synthesize(question, intent, evidence)
    return {
        "answer": result.answer,
        "supporting_metrics": result.supporting_metrics,
        "recommended_actions": result.recommended_actions,
        "related_alert_ids": result.related_alert_ids,
    }


def _make_evidence_handler(intent: Intent) -> Callable[..., Any]:
    gather = RETRIEVERS[intent]

    def handler(session: Session, arguments: dict[str, Any], *, question: str, today: Optional[date]) -> Any:
        evidence = gather(session, today)
        return _synthesis_payload(question, intent, evidence)

    return handler


def _handle_search_customers(session: Session, arguments: dict[str, Any], *, question: str, today: Optional[date]) -> Any:
    query = arguments.get("query", "")
    limit = arguments.get("limit", 10)
    return to_jsonable(services.search_customers(session, query=query, limit=limit))


def _handle_get_order(session: Session, arguments: dict[str, Any], *, question: str, today: Optional[date]) -> Any:
    order = services.get_order(session, order_id=arguments["order_id"])
    if order is None:
        return {"found": False, "order_id": arguments["order_id"]}
    return {"found": True, **to_jsonable(order)}


def _handle_get_product(session: Session, arguments: dict[str, Any], *, question: str, today: Optional[date]) -> Any:
    product = services.get_product(session, product_id=arguments["product_id"])
    if product is None:
        return {"found": False, "product_id": arguments["product_id"]}
    return {"found": True, **to_jsonable(product)}


def _handle_propose_action(session: Session, arguments: dict[str, Any], *, question: str, today: Optional[date]) -> Any:
    try:
        action_type = ActionType(arguments["action_type"])
        risk_level = RiskLevel(arguments["risk_level"])
    except ValueError as exc:
        raise ToolArgumentError(f"propose_action: {exc}") from exc

    # Reject a nonexistent customer/product before any AgentAction row is
    # created -- a bad id from the model must never persist a dangling
    # reference. product_id reuses the existing get_product() lookup (no
    # new business logic); there's no equivalent service-layer function for
    # a single customer by id, so this is a direct, read-only existence
    # check, not a duplicated computation.
    customer_id = arguments.get("customer_id")
    if customer_id is not None and session.get(Customer, customer_id) is None:
        raise ToolArgumentError(f"propose_action: no customer with id {customer_id}.")

    product_id = arguments.get("product_id")
    if product_id is not None and services.get_product(session, product_id) is None:
        raise ToolArgumentError(f"propose_action: no product with id {product_id}.")

    draft = ProposalDraft(
        action_type=action_type,
        business_reason=arguments["business_reason"],
        proposed_parameters=arguments.get("proposed_parameters") or {},
        expected_outcome=arguments["expected_outcome"],
        risk_level=risk_level,
        customer_id=customer_id,
        product_id=product_id,
    )
    action = create_manual_proposal(session, draft)
    return {
        "action_id": action.id,
        "status": action.status.value,
        "action_type": action.action_type.value,
        "risk_level": action.risk_level.value,
        "note": (
            "Created as PROPOSED only. It now requires human review and explicit "
            "approval in the Agent Actions panel before anything is executed -- "
            "you cannot approve or execute actions yourself."
        ),
    }


_EVIDENCE_TOOLS: dict[str, tuple[Intent, str]] = {
    "get_revenue_explanation": (Intent.REVENUE_EXPLANATION, "Explain how revenue changed over the current reporting period vs. the prior one, including the biggest gaining/declining products and any related alert."),
    "get_product_performance": (Intent.PRODUCT_PERFORMANCE, "Get the best- and worst-selling products over the current reporting period, and flag any top seller that's also low/out of stock."),
    "get_restock_priority": (Intent.RESTOCK_PRIORITY, "Get products that need restocking right now, in priority order, with out-of-stock and low-stock counts."),
    "get_top_customers": (Intent.TOP_CUSTOMERS, "Get the most valuable customers by total spend, flagging any who are also at risk of churning."),
    "get_churn_risk": (Intent.CHURN_RISK, "Get high-value customers who haven't ordered recently and may be churning."),
    "get_expense_anomalies": (Intent.EXPENSE_ANOMALIES, "Get this month's expenses by category and flag any category with an unusual spike vs. last month."),
    "get_traffic_conversion": (Intent.TRAFFIC_CONVERSION, "Get website visitor and conversion-rate trends for the current period vs. the prior one."),
    "get_business_issues_summary": (Intent.BUSINESS_ISSUES_SUMMARY, "Get every currently open business issue/alert across revenue, inventory, expenses, traffic, orders, and customers, ranked by severity."),
}

TOOL_REGISTRY: dict[str, ToolSpec] = {
    name: ToolSpec(name=name, description=description, input_schema=_EMPTY_SCHEMA, handler=_make_evidence_handler(intent), read_only=True)
    for name, (intent, description) in _EVIDENCE_TOOLS.items()
}

TOOL_REGISTRY["search_customers"] = ToolSpec(
    name="search_customers",
    description="Search customers by name or email substring (for looking up a specific customer by name).",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Name or email substring to search for. Empty returns the first customers alphabetically."},
            "limit": {"type": "integer", "description": "Max results to return (default 10, maximum 50).", "minimum": 1, "maximum": 50},
        },
        "required": [],
    },
    handler=_handle_search_customers,
    read_only=True,
)

TOOL_REGISTRY["get_order"] = ToolSpec(
    name="get_order",
    description="Get full line-item detail for one order by its id.",
    input_schema={"type": "object", "properties": {"order_id": {"type": "integer", "description": "The order's id."}}, "required": ["order_id"]},
    handler=_handle_get_order,
    read_only=True,
)

TOOL_REGISTRY["get_product"] = ToolSpec(
    name="get_product",
    description="Get one product's catalog details and live stock by its id.",
    input_schema={"type": "object", "properties": {"product_id": {"type": "integer", "description": "The product's id."}}, "required": ["product_id"]},
    handler=_handle_get_product,
    read_only=True,
)

TOOL_REGISTRY["propose_action"] = ToolSpec(
    name="propose_action",
    description=(
        "Propose a business action for human review -- e.g. a customer win-back offer, a restock request, "
        "or a generic follow-up task. This ONLY creates a PROPOSED record for a human to review in the Agent "
        "Actions panel; it never sends anything, changes inventory, or executes on its own. Use this instead of "
        "just describing a recommendation in your answer whenever the user asks you to take action or follow up."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "action_type": {"type": "string", "enum": [t.value for t in ActionType], "description": "The kind of action being proposed."},
            "business_reason": {"type": "string", "description": "Why this action is being proposed, grounded in tool results."},
            "proposed_parameters": {"type": "object", "description": "Action-specific parameters, e.g. {\"offer_percent\": 10, \"message\": \"...\", \"customer_email\": \"...\"} for a win_back_offer."},
            "expected_outcome": {"type": "string", "description": "What approving this action is expected to achieve."},
            "risk_level": {"type": "string", "enum": [r.value for r in RiskLevel], "description": "How much business risk this action carries if approved."},
            "customer_id": {"type": "integer", "description": "The related customer's id, if any."},
            "product_id": {"type": "integer", "description": "The related product's id, if any."},
        },
        "required": ["action_type", "business_reason", "expected_outcome", "risk_level"],
    },
    handler=_handle_propose_action,
    read_only=False,
)


def get_tool_schemas() -> list[dict[str, Any]]:
    return build_schemas(TOOL_REGISTRY)


def dispatch_tool(session: Session, name: str, arguments: dict[str, Any], *, question: str, today: Optional[date]) -> str:
    """Runs one tool call against the admin `TOOL_REGISTRY` and returns
    its JSON-serialized result. See `tool_kit.dispatch` for the shared
    mechanics -- this wrapper only fixes the admin-specific `question`/
    `today` handler context so every existing caller/test keeps this
    exact signature."""
    return _dispatch(TOOL_REGISTRY, session, name, arguments, question=question, today=today)
