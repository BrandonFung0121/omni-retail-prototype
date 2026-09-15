"""Turns an Alert into a proposed business action.

Each alert type maps to exactly one action type -- this is a Phase 7
judgment call, not something the underlying alert data forces: a
customer win-back opportunity always proposes a WIN_BACK_OFFER; a
stock alert always proposes a RESTOCK_REQUEST; every other alert type
(revenue, expenses, traffic, order failures -- none of them tied to a
single customer or product) proposes a generic FOLLOWUP_TASK, whose
execution doubles as "acknowledge this alert" since there is no
persisted alert row to flip a status on directly.

Builders are pure functions: Alert in, ProposalDraft out, no session,
no DB. They read only alert.supporting_data, which every rule in
automation/rules.py already populates for exactly this purpose.
"""

from __future__ import annotations

from typing import Callable, Optional

from omni_retail.actions.models import ProposalDraft
from omni_retail.automation import Alert, AlertType, Severity
from omni_retail.models import ActionType, RiskLevel

# Win-back offers scale with how cold the relationship has gone.
_DEEP_CHURN_DAYS = 60
_DEEP_CHURN_OFFER_PCT = 20
_STANDARD_OFFER_PCT = 10

# Restocking targets three reorder thresholds of headroom above what's
# currently on hand, with a floor of one threshold's worth.
_RESTOCK_TARGET_MULTIPLIER = 3

_SEVERITY_TO_PRIORITY = {
    Severity.CRITICAL: "high",
    Severity.WARNING: "medium",
    Severity.INFO: "low",
}


def _win_back_offer(alert: Alert) -> ProposalDraft:
    data = alert.supporting_data
    customer_name = data["customer_name"]
    days_since = data["days_since_last_order"]
    offer_percent = _DEEP_CHURN_OFFER_PCT if days_since >= _DEEP_CHURN_DAYS else _STANDARD_OFFER_PCT
    message = (
        f"Hi {customer_name}, it's been {days_since} days since your last OMNI Retail order. "
        f"As a valued customer who's spent ${data['total_spent']:,.2f} with us, here's {offer_percent}% "
        f"off your next purchase -- use code WELCOMEBACK{offer_percent} at checkout."
    )
    return ProposalDraft(
        action_type=ActionType.WIN_BACK_OFFER,
        business_reason=alert.description,
        proposed_parameters={
            "offer_percent": offer_percent,
            "message": message,
            "customer_email": data["customer_email"],
        },
        expected_outcome=(
            f"Re-engage {customer_name} and recover a share of their historical order value "
            f"(avg ${data['average_order_value']:,.2f}/order)."
        ),
        risk_level=RiskLevel.MEDIUM if offer_percent >= _DEEP_CHURN_OFFER_PCT else RiskLevel.LOW,
        customer_id=data["customer_id"],
    )


def _restock_request(alert: Alert) -> ProposalDraft:
    data = alert.supporting_data
    current_stock = data["current_stock"]
    reorder_threshold = data["reorder_threshold"]
    quantity = max(reorder_threshold * _RESTOCK_TARGET_MULTIPLIER - current_stock, reorder_threshold)
    return ProposalDraft(
        action_type=ActionType.RESTOCK_REQUEST,
        business_reason=alert.description,
        proposed_parameters={
            "restock_quantity": quantity,
            "product_name": data["product_name"],
        },
        expected_outcome=f"Prevent stockouts and lost sales for {data['product_name']}.",
        risk_level=RiskLevel.HIGH if alert.type == AlertType.OUT_OF_STOCK else RiskLevel.MEDIUM,
        product_id=data["product_id"],
    )


def _followup_task(alert: Alert) -> ProposalDraft:
    return ProposalDraft(
        action_type=ActionType.FOLLOWUP_TASK,
        business_reason=alert.description,
        proposed_parameters={
            "task": alert.recommended_action,
            "priority": _SEVERITY_TO_PRIORITY[alert.severity],
        },
        expected_outcome="Ensure the underlying issue is investigated and addressed by the team, and the alert is acknowledged.",
        risk_level=RiskLevel.HIGH if alert.severity == Severity.CRITICAL else RiskLevel.LOW,
    )


_BUILDERS: dict[AlertType, Callable[[Alert], ProposalDraft]] = {
    AlertType.CUSTOMER_WIN_BACK_OPPORTUNITY: _win_back_offer,
    AlertType.LOW_STOCK: _restock_request,
    AlertType.OUT_OF_STOCK: _restock_request,
    AlertType.REVENUE_DROP: _followup_task,
    AlertType.EXPENSE_SPIKE: _followup_task,
    AlertType.TRAFFIC_CONVERSION_GAP: _followup_task,
    AlertType.ORDER_FAILURE_PATTERN: _followup_task,
}


def build_proposal(alert: Alert) -> Optional[ProposalDraft]:
    builder = _BUILDERS.get(alert.type)
    return builder(alert) if builder else None
