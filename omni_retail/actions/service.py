"""The one place in this codebase that writes to agent_actions.

Mirrors transactions/service.py's shape: plain functions that take a
session and return or raise, with no HTTP or UI knowledge, so the API
router is a thin wrapper and any other caller (a script, a future
scheduled job) reuses the exact same lifecycle.

Lifecycle: PROPOSED -> APPROVED -> EXECUTED | FAILED, or
PROPOSED -> REJECTED (terminal). execute_action() refuses to run on
anything but an APPROVED action -- that guard is what actually
guarantees "the AI never executes a consequential action without
explicit human approval," and it lives here so it can't be bypassed by
a caller that skips the API layer.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from omni_retail.actions.executors import EXECUTORS, ExecutionOutcome
from omni_retail.actions.models import ActionNotApprovedError, ActionNotProposedError, ProposalDraft
from omni_retail.actions.proposals import build_proposal
from omni_retail.automation import run_all_rules
from omni_retail.models import ActionStatus
from omni_retail.models.agent_action import AgentAction


def create_proposals(session: Session, today: Optional[date] = None) -> list[AgentAction]:
    """Runs the rule engine and persists a proposal for any open alert that
    doesn't already have one. Idempotent: calling this repeatedly never
    creates a duplicate proposal for the same alert, unless a prior
    proposal for it was rejected -- the business condition may have
    changed since, so a rejected alert is eligible to be re-proposed."""
    alerts = run_all_rules(session, today=today)

    existing = session.execute(
        select(AgentAction.action_type, AgentAction.source_alert_id).where(
            AgentAction.status != ActionStatus.REJECTED
        )
    ).all()
    existing_keys = {(action_type, alert_id) for action_type, alert_id in existing}

    now = datetime.now()
    created: list[AgentAction] = []
    for alert in alerts:
        draft = build_proposal(alert)
        if draft is None:
            continue
        key = (draft.action_type, alert.id)
        if key in existing_keys:
            continue

        action = AgentAction(
            action_type=draft.action_type,
            source_alert_id=alert.id,
            customer_id=draft.customer_id,
            product_id=draft.product_id,
            business_reason=draft.business_reason,
            supporting_evidence=alert.supporting_data,
            proposed_parameters=draft.proposed_parameters,
            expected_outcome=draft.expected_outcome,
            risk_level=draft.risk_level,
            status=ActionStatus.PROPOSED,
            created_at=now,
        )
        session.add(action)
        created.append(action)
        existing_keys.add(key)

    if created:
        session.commit()
        for action in created:
            session.refresh(action)
    return created


def create_manual_proposal(
    session: Session,
    draft: ProposalDraft,
    source_alert_id: Optional[str] = None,
) -> AgentAction:
    """Persists a single PROPOSED action from a hand-built ProposalDraft,
    rather than one derived from run_all_rules(). This is the only
    entry point ai/llm/tools.py's `propose_action` tool is wired to --
    `status=PROPOSED` is hardcoded here, not a parameter, so an
    LLM-originated proposal is subject to exactly the same
    approve_action()/execute_action() gate as a rule-engine-originated
    one, enforced regardless of which path created the row."""
    action = AgentAction(
        action_type=draft.action_type,
        source_alert_id=source_alert_id,
        customer_id=draft.customer_id,
        product_id=draft.product_id,
        business_reason=draft.business_reason,
        supporting_evidence={},
        proposed_parameters=draft.proposed_parameters,
        expected_outcome=draft.expected_outcome,
        risk_level=draft.risk_level,
        status=ActionStatus.PROPOSED,
        created_at=datetime.now(),
    )
    session.add(action)
    session.commit()
    session.refresh(action)
    return action


def _get_action_or_raise(session: Session, action_id: int) -> AgentAction:
    action = session.get(AgentAction, action_id)
    if action is None:
        raise LookupError(f"No agent action with id {action_id}.")
    return action


def approve_action(
    session: Session,
    action_id: int,
    decided_by: str,
    edited_parameters: Optional[dict[str, Any]] = None,
) -> AgentAction:
    """Approves a proposed action, then immediately executes it.

    Approval and execution are kept as two distinct calls (this function
    delegates to execute_action() rather than inlining it) so a later
    version of this prototype could queue execution asynchronously
    without changing what "approved" means or re-litigating the
    approval gate.
    """
    action = _get_action_or_raise(session, action_id)
    if action.status != ActionStatus.PROPOSED:
        raise ActionNotProposedError(
            f"Action {action_id} is {action.status.value}, not proposed -- it cannot be approved."
        )

    action.status = ActionStatus.APPROVED
    action.decided_at = datetime.now()
    action.decided_by = decided_by
    if edited_parameters:
        action.edited_parameters = edited_parameters
    session.commit()

    return execute_action(session, action_id)


def reject_action(
    session: Session, action_id: int, decided_by: str, reason: Optional[str] = None
) -> AgentAction:
    action = _get_action_or_raise(session, action_id)
    if action.status != ActionStatus.PROPOSED:
        raise ActionNotProposedError(
            f"Action {action_id} is {action.status.value}, not proposed -- it cannot be rejected."
        )

    action.status = ActionStatus.REJECTED
    action.decided_at = datetime.now()
    action.decided_by = decided_by
    action.rejection_reason = reason
    session.commit()
    return action


def execute_action(session: Session, action_id: int) -> AgentAction:
    """Runs the simulated integration for an approved action.

    Raises ActionNotApprovedError for anything else, regardless of how
    it's called -- direct tests call this function on a PROPOSED or
    REJECTED action specifically to prove the guard holds independent
    of the API layer.
    """
    action = _get_action_or_raise(session, action_id)
    if action.status != ActionStatus.APPROVED:
        raise ActionNotApprovedError(
            f"Action {action_id} is {action.status.value}, not approved -- it cannot be executed."
        )

    parameters = dict(action.proposed_parameters or {})
    parameters.update(action.edited_parameters or {})

    executor = EXECUTORS[action.action_type]
    try:
        result = executor.execute(action, parameters)
    except Exception as exc:
        # An executor is expected to report failure via ExecutionResult,
        # not raise -- but a genuinely broken integration shouldn't be
        # able to leave an action stuck in APPROVED limbo either.
        action.status = ActionStatus.FAILED
        action.executed_at = datetime.now()
        action.execution_result = {"outcome": ExecutionOutcome.FAILED, "failure_reason": str(exc)}
        session.commit()
        return action

    action.executed_at = datetime.now()
    if result.outcome == ExecutionOutcome.SUCCESS:
        action.status = ActionStatus.EXECUTED
        action.execution_result = {
            "outcome": result.outcome,
            "reference": result.reference,
            "detail": result.detail,
        }
    else:
        action.status = ActionStatus.FAILED
        action.execution_result = {
            "outcome": result.outcome,
            "reference": result.reference,
            "failure_reason": result.failure_reason,
        }
    session.commit()
    return action
