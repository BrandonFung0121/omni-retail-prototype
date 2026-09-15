"""Tests for the LLM tool registry/schemas/dispatch (ai/llm/tools.py).

Read-only tools reuse `session`/`fresh_session` the same way the rest
of the suite does; the one write-shaped tool (`propose_action`) always
uses `fresh_session` since it mutates the database.
"""

from __future__ import annotations

import json

import pytest

from omni_retail.actions import ActionNotApprovedError, approve_action, execute_action
from omni_retail.ai.llm.tools import (
    TOOL_REGISTRY,
    ToolArgumentError,
    UnknownToolError,
    dispatch_tool,
    get_tool_schemas,
)
from omni_retail.models import ActionStatus
from omni_retail.models.agent_action import AgentAction


def test_registry_never_exposes_approve_or_execute():
    assert "approve_action" not in TOOL_REGISTRY
    assert "execute_action" not in TOOL_REGISTRY


def test_get_tool_schemas_shape():
    schemas = get_tool_schemas()
    names = {s["name"] for s in schemas}
    assert names == set(TOOL_REGISTRY)
    for schema in schemas:
        assert schema["description"]
        assert schema["input_schema"]["type"] == "object"


@pytest.mark.parametrize(
    "tool_name",
    [
        "get_revenue_explanation",
        "get_product_performance",
        "get_restock_priority",
        "get_top_customers",
        "get_churn_risk",
        "get_expense_anomalies",
        "get_traffic_conversion",
        "get_business_issues_summary",
    ],
)
def test_evidence_tool_dispatch_returns_grounded_json(session, tool_name):
    payload = dispatch_tool(session, tool_name, {}, question="test question", today=None)
    data = json.loads(payload)
    assert data["answer"]
    json.dumps(data["supporting_metrics"])  # must already be JSON-safe


def test_dispatch_unknown_tool_raises_unknown_tool_error(session):
    with pytest.raises(UnknownToolError):
        dispatch_tool(session, "delete_everything", {}, question="q", today=None)


def test_dispatch_wrong_argument_type_raises_tool_argument_error(session):
    with pytest.raises(ToolArgumentError):
        dispatch_tool(session, "get_order", {"order_id": "not-a-number"}, question="q", today=None)


def test_dispatch_missing_required_argument_raises_tool_argument_error(session):
    with pytest.raises(ToolArgumentError):
        dispatch_tool(session, "get_order", {}, question="q", today=None)


def test_dispatch_unexpected_argument_raises_tool_argument_error(session):
    with pytest.raises(ToolArgumentError):
        dispatch_tool(session, "search_customers", {"bogus_field": 1}, question="q", today=None)


def test_search_customers_tool(session):
    payload = dispatch_tool(session, "search_customers", {"query": "", "limit": 3}, question="q", today=None)
    data = json.loads(payload)
    assert isinstance(data, list)
    assert len(data) <= 3
    if data:
        assert {"customer_id", "name", "email"} <= set(data[0])


def test_search_customers_limit_over_maximum_is_rejected(session):
    with pytest.raises(ToolArgumentError):
        dispatch_tool(session, "search_customers", {"limit": 51}, question="q", today=None)


def test_search_customers_limit_at_maximum_is_allowed(session):
    payload = dispatch_tool(session, "search_customers", {"limit": 50}, question="q", today=None)
    assert isinstance(json.loads(payload), list)


def test_search_customers_limit_below_minimum_is_rejected(session):
    with pytest.raises(ToolArgumentError):
        dispatch_tool(session, "search_customers", {"limit": 0}, question="q", today=None)


def test_get_order_tool_not_found(session):
    payload = dispatch_tool(session, "get_order", {"order_id": 999999999}, question="q", today=None)
    data = json.loads(payload)
    assert data == {"found": False, "order_id": 999999999}


def test_get_product_tool_found(session):
    from omni_retail import services

    products = services.list_products(session)
    assert products, "seeded data should include products"
    product_id = products[0].product_id

    payload = dispatch_tool(session, "get_product", {"product_id": product_id}, question="q", today=None)
    data = json.loads(payload)
    assert data["found"] is True
    assert data["product_id"] == product_id


def test_propose_action_tool_creates_only_a_proposed_row(fresh_session):
    payload = dispatch_tool(
        fresh_session,
        "propose_action",
        {
            "action_type": "followup_task",
            "business_reason": "LLM noticed something worth a human look.",
            "expected_outcome": "The team investigates and resolves it.",
            "risk_level": "low",
        },
        question="q",
        today=None,
    )
    data = json.loads(payload)
    assert data["status"] == "proposed"

    action = fresh_session.get(AgentAction, data["action_id"])
    assert action.status == ActionStatus.PROPOSED
    assert action.business_reason == "LLM noticed something worth a human look."


def test_propose_action_invalid_enum_value_is_rejected(fresh_session):
    with pytest.raises(ToolArgumentError):
        dispatch_tool(
            fresh_session,
            "propose_action",
            {
                "action_type": "delete_customer",  # not a real ActionType
                "business_reason": "x",
                "expected_outcome": "y",
                "risk_level": "low",
            },
            question="q",
            today=None,
        )


def test_propose_action_with_valid_customer_and_product_id_succeeds(fresh_session):
    from omni_retail import services

    customers = services.search_customers(fresh_session, limit=1)
    products = services.list_products(fresh_session)
    assert customers and products, "seeded data should include a customer and a product"

    payload = dispatch_tool(
        fresh_session,
        "propose_action",
        {
            "action_type": "followup_task",
            "business_reason": "Grounded in real records.",
            "expected_outcome": "Resolved.",
            "risk_level": "low",
            "customer_id": customers[0].customer_id,
            "product_id": products[0].product_id,
        },
        question="q",
        today=None,
    )
    data = json.loads(payload)
    action = fresh_session.get(AgentAction, data["action_id"])
    assert action.status == ActionStatus.PROPOSED
    assert action.customer_id == customers[0].customer_id
    assert action.product_id == products[0].product_id


def test_propose_action_invalid_customer_id_is_rejected_and_creates_no_action(fresh_session):
    before = fresh_session.query(AgentAction).count()

    with pytest.raises(ToolArgumentError):
        dispatch_tool(
            fresh_session,
            "propose_action",
            {
                "action_type": "followup_task",
                "business_reason": "x",
                "expected_outcome": "y",
                "risk_level": "low",
                "customer_id": 999999999,
            },
            question="q",
            today=None,
        )

    assert fresh_session.query(AgentAction).count() == before


def test_propose_action_invalid_product_id_is_rejected_and_creates_no_action(fresh_session):
    before = fresh_session.query(AgentAction).count()

    with pytest.raises(ToolArgumentError):
        dispatch_tool(
            fresh_session,
            "propose_action",
            {
                "action_type": "restock_request",
                "business_reason": "x",
                "expected_outcome": "y",
                "risk_level": "low",
                "product_id": 999999999,
            },
            question="q",
            today=None,
        )

    assert fresh_session.query(AgentAction).count() == before


def test_llm_proposed_action_still_requires_human_approval_before_execution(fresh_session):
    """The structural proof of the Phase 7 safety rule: an LLM-originated
    proposal is subject to the exact same approve/execute gate as a
    rule-engine-originated one -- execute_action() refuses anything that
    isn't APPROVED, regardless of how the PROPOSED row was created."""
    payload = dispatch_tool(
        fresh_session,
        "propose_action",
        {
            "action_type": "followup_task",
            "business_reason": "Needs a human look.",
            "expected_outcome": "Resolved by the team.",
            "risk_level": "low",
        },
        question="q",
        today=None,
    )
    action_id = json.loads(payload)["action_id"]

    with pytest.raises(ActionNotApprovedError):
        execute_action(fresh_session, action_id)

    approved = approve_action(fresh_session, action_id, decided_by="Tester")
    assert approved.status in (ActionStatus.EXECUTED, ActionStatus.FAILED)
