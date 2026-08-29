"""Plain data shapes for the agentic-actions layer.

ProposalDraft is what proposals.py builds from an Alert -- everything
service.create_proposals() needs to persist an AgentAction row, but
with no DB/session knowledge of its own (same split as
transactions/models.py's Cart vs. transactions/service.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from omni_retail.models import ActionType, RiskLevel


@dataclass
class ProposalDraft:
    action_type: ActionType
    business_reason: str
    proposed_parameters: dict[str, Any]
    expected_outcome: str
    risk_level: RiskLevel
    customer_id: Optional[int] = None
    product_id: Optional[int] = None


class ActionError(Exception):
    """Base class for agentic-action lifecycle errors."""


class ActionNotProposedError(ActionError):
    """Raised when approve/reject is attempted on a non-proposed action."""


class ActionNotApprovedError(ActionError):
    """Raised when execution is attempted on a non-approved action.

    This is the concrete enforcement of "the AI must never execute a
    consequential action without explicit human approval" -- it lives in
    the service layer so it holds regardless of caller, not just for
    requests that happen to go through the API.
    """
