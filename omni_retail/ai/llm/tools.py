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

import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from omni_retail import services
from omni_retail.actions.models import ProposalDraft
from omni_retail.actions.service import create_manual_proposal
from omni_retail.ai.intents import Intent
from omni_retail.ai.retrieval import RETRIEVERS
from omni_retail.ai.synthesis import TemplateAnswerSynthesizer
from omni_retail.models import ActionType, RiskLevel


class ToolError(Exception):
    """Base class for a malformed/unknown tool call -- recoverable:
    the orchestrator feeds the message back to the model as a tool
    error result rather than aborting the run."""


class UnknownToolError(ToolError):
    pass


class ToolArgumentError(ToolError):
    pass


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]
    read_only: bool = True


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    return value


def _synthesis_payload(question: str, intent: Intent, evidence: dict[str, Any]) -> dict[str, Any]:
    result = TemplateAnswerSynthesizer().synthesize(question, intent, evidence)
    return {
        "answer": result.answer,
        "supporting_metrics": result.supporting_metrics,
        "recommended_actions": result.recommended_actions,
        "related_alert_ids": result.related_alert_ids,
    }


def _check_schema(schema: dict[str, Any], arguments: dict[str, Any], tool_name: str) -> None:
    if not isinstance(arguments, dict):
        raise ToolArgumentError(f"{tool_name}: arguments must be a JSON object, got {type(arguments).__name__}.")

    for field_name in schema.get("required", []):
        if field_name not in arguments:
            raise ToolArgumentError(f"{tool_name}: missing required argument {field_name!r}.")

    properties = schema.get("properties", {})
    _type_map = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "object": dict, "array": list}
    for field_name, value in arguments.items():
        prop_schema = properties.get(field_name)
        if prop_schema is None:
            raise ToolArgumentError(f"{tool_name}: unexpected argument {field_name!r}.")
        expected_type = _type_map.get(prop_schema.get("type"))
        # bool is a subclass of int in Python -- exclude it from the "integer"/"number" check
        # so a stray `true` isn't silently accepted as a quantity.
        if expected_type is not None and (
            not isinstance(value, expected_type) or (expected_type in (int, (int, float)) and isinstance(value, bool))
        ):
            raise ToolArgumentError(
                f"{tool_name}: argument {field_name!r} must be of type {prop_schema.get('type')}, got {type(value).__name__}."
            )
        enum_values = prop_schema.get("enum")
        if enum_values is not None and value not in enum_values:
            raise ToolArgumentError(f"{tool_name}: argument {field_name!r} must be one of {enum_values}, got {value!r}.")


def _make_evidence_handler(intent: Intent) -> Callable[..., Any]:
    gather = RETRIEVERS[intent]

    def handler(session: Session, arguments: dict[str, Any], *, question: str, today: Optional[date]) -> Any:
        evidence = gather(session, today)
        return _synthesis_payload(question, intent, evidence)

    return handler


def _handle_search_customers(session: Session, arguments: dict[str, Any], *, question: str, today: Optional[date]) -> Any:
    query = arguments.get("query", "")
    limit = arguments.get("limit", 10)
    return _to_jsonable(services.search_customers(session, query=query, limit=limit))


def _handle_get_order(session: Session, arguments: dict[str, Any], *, question: str, today: Optional[date]) -> Any:
    order = services.get_order(session, order_id=arguments["order_id"])
    if order is None:
        return {"found": False, "order_id": arguments["order_id"]}
    return {"found": True, **_to_jsonable(order)}


def _handle_get_product(session: Session, arguments: dict[str, Any], *, question: str, today: Optional[date]) -> Any:
    product = services.get_product(session, product_id=arguments["product_id"])
    if product is None:
        return {"found": False, "product_id": arguments["product_id"]}
    return {"found": True, **_to_jsonable(product)}


def _handle_propose_action(session: Session, arguments: dict[str, Any], *, question: str, today: Optional[date]) -> Any:
    try:
        action_type = ActionType(arguments["action_type"])
        risk_level = RiskLevel(arguments["risk_level"])
    except ValueError as exc:
        raise ToolArgumentError(f"propose_action: {exc}") from exc

    draft = ProposalDraft(
        action_type=action_type,
        business_reason=arguments["business_reason"],
        proposed_parameters=arguments.get("proposed_parameters") or {},
        expected_outcome=arguments["expected_outcome"],
        risk_level=risk_level,
        customer_id=arguments.get("customer_id"),
        product_id=arguments.get("product_id"),
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


_EMPTY_SCHEMA = {"type": "object", "properties": {}, "required": []}

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
            "limit": {"type": "integer", "description": "Max results to return (default 10)."},
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
    return [{"name": spec.name, "description": spec.description, "input_schema": spec.input_schema} for spec in TOOL_REGISTRY.values()]


def dispatch_tool(session: Session, name: str, arguments: dict[str, Any], *, question: str, today: Optional[date]) -> str:
    """Runs one tool call and returns its JSON-serialized result.

    Raises `UnknownToolError`/`ToolArgumentError` for a bad request from
    the model -- the orchestrator catches exactly these two and feeds
    them back as a tool error result. Any other exception (a genuine
    bug in a handler or the underlying service) is left to propagate,
    on purpose: it must not be mistaken for "the model asked for
    something invalid.\""""
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        raise UnknownToolError(f"No such tool {name!r}. Available tools: {', '.join(sorted(TOOL_REGISTRY))}.")

    _check_schema(spec.input_schema, arguments, name)
    result = spec.handler(session, arguments, question=question, today=today)
    return json.dumps(result, default=str)
