"""Tests for the Phase 7 agentic-actions lifecycle.

These mutate the database (create proposals, approve, reject, execute),
so every test here uses fresh_session -- never the shared session
fixture -- following the same convention test_transactions.py
established for complete_sale().
"""

import pytest

from omni_retail.actions import (
    ActionNotApprovedError,
    ActionNotProposedError,
    approve_action,
    create_proposals,
    execute_action,
    reject_action,
)
from omni_retail.actions.executors import MAX_SUPPLIER_QUANTITY
from omni_retail.models import ActionStatus, ActionType, RiskLevel
from omni_retail.models.agent_action import AgentAction


def test_create_proposals_produces_well_formed_actions(fresh_session):
    created = create_proposals(fresh_session)
    assert len(created) > 0

    for action in created:
        assert isinstance(action.action_type, ActionType)
        assert isinstance(action.risk_level, RiskLevel)
        assert action.status == ActionStatus.PROPOSED
        assert action.business_reason
        assert action.supporting_evidence
        assert action.proposed_parameters
        assert action.expected_outcome
        assert action.created_at is not None
        assert action.decided_at is None
        assert action.executed_at is None
        assert action.execution_result is None


def test_win_back_alert_proposes_win_back_offer_with_message_and_email(fresh_session):
    created = create_proposals(fresh_session)
    win_backs = [a for a in created if a.action_type == ActionType.WIN_BACK_OFFER]
    assert win_backs, "seeded data should produce at least one win-back opportunity"

    action = win_backs[0]
    assert action.customer_id is not None
    assert "message" in action.proposed_parameters
    assert "customer_email" in action.proposed_parameters
    assert "offer_percent" in action.proposed_parameters


def test_stock_alert_proposes_restock_with_quantity(fresh_session):
    created = create_proposals(fresh_session)
    restocks = [a for a in created if a.action_type == ActionType.RESTOCK_REQUEST]
    assert restocks, "seeded data should produce at least one stock alert"

    action = restocks[0]
    assert action.product_id is not None
    assert action.proposed_parameters["restock_quantity"] > 0


def test_create_proposals_is_idempotent(fresh_session):
    first = create_proposals(fresh_session)
    second = create_proposals(fresh_session)
    assert len(first) > 0
    assert second == []

    all_actions = fresh_session.query(AgentAction).all()
    assert len(all_actions) == len(first)


def test_create_proposals_reproposes_after_rejection(fresh_session):
    created = create_proposals(fresh_session)
    action = created[0]

    reject_action(fresh_session, action.id, decided_by="Admin", reason="Not now")
    again = create_proposals(fresh_session)

    assert any(a.source_alert_id == action.source_alert_id for a in again)


def test_approve_executes_immediately_and_records_result(fresh_session):
    created = create_proposals(fresh_session)
    action = next(a for a in created if a.action_type == ActionType.WIN_BACK_OFFER)

    result = approve_action(fresh_session, action.id, decided_by="Brandon Fung")

    assert result.status == ActionStatus.EXECUTED
    assert result.decided_by == "Brandon Fung"
    assert result.decided_at is not None
    assert result.executed_at is not None
    assert result.execution_result["outcome"] == "success"
    assert result.execution_result["reference"].startswith("SIM-")


def test_approve_with_edited_parameters_uses_edited_values(fresh_session):
    created = create_proposals(fresh_session)
    action = next(a for a in created if a.action_type == ActionType.WIN_BACK_OFFER)
    edited_email = "override@example.com"

    result = approve_action(
        fresh_session, action.id, decided_by="Brandon Fung", edited_parameters={"customer_email": edited_email}
    )

    assert result.edited_parameters == {"customer_email": edited_email}
    assert edited_email in result.execution_result["detail"]


def test_reject_is_terminal_and_records_reason(fresh_session):
    created = create_proposals(fresh_session)
    action = created[0]

    result = reject_action(fresh_session, action.id, decided_by="Brandon Fung", reason="Too costly")

    assert result.status == ActionStatus.REJECTED
    assert result.decided_by == "Brandon Fung"
    assert result.rejection_reason == "Too costly"
    assert result.executed_at is None
    assert result.execution_result is None


def test_approving_a_rejected_action_raises(fresh_session):
    created = create_proposals(fresh_session)
    action = created[0]
    reject_action(fresh_session, action.id, decided_by="Admin")

    with pytest.raises(ActionNotProposedError):
        approve_action(fresh_session, action.id, decided_by="Admin")


def test_rejecting_an_already_decided_action_raises(fresh_session):
    created = create_proposals(fresh_session)
    action = created[0]
    reject_action(fresh_session, action.id, decided_by="Admin")

    with pytest.raises(ActionNotProposedError):
        reject_action(fresh_session, action.id, decided_by="Admin")


def test_execution_is_prevented_without_approval(fresh_session):
    """The core Phase 7 requirement: the AI must never execute a
    consequential action without explicit human approval. This calls
    execute_action() directly -- bypassing approve_action() entirely --
    to prove the guard is enforced in the service layer itself, not just
    by the API not exposing a button for it."""
    created = create_proposals(fresh_session)
    proposed_action = created[0]

    with pytest.raises(ActionNotApprovedError):
        execute_action(fresh_session, proposed_action.id)

    reject_action(fresh_session, proposed_action.id, decided_by="Admin")
    with pytest.raises(ActionNotApprovedError):
        execute_action(fresh_session, proposed_action.id)


def test_restock_execution_fails_deterministically_over_supplier_cap(fresh_session):
    created = create_proposals(fresh_session)
    action = next(a for a in created if a.action_type == ActionType.RESTOCK_REQUEST)

    result = approve_action(
        fresh_session,
        action.id,
        decided_by="Admin",
        edited_parameters={"restock_quantity": MAX_SUPPLIER_QUANTITY + 1},
    )

    assert result.status == ActionStatus.FAILED
    assert result.execution_result["outcome"] == "failed"
    assert "Supplier cannot fulfill" in result.execution_result["failure_reason"]


def test_failed_execution_still_records_reference_and_timestamp(fresh_session):
    created = create_proposals(fresh_session)
    action = next(a for a in created if a.action_type == ActionType.RESTOCK_REQUEST)

    result = approve_action(
        fresh_session, action.id, decided_by="Admin", edited_parameters={"restock_quantity": -5}
    )

    assert result.status == ActionStatus.FAILED
    assert result.executed_at is not None
