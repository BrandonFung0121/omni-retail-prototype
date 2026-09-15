"""Simulated external-integration executors.

execute_action() in service.py depends only on the ActionExecutor
interface, never on a concrete executor directly -- the same seam as
payments/processor.py's PaymentProcessor for card charges. Swapping in
a real email provider, CRM, or supplier/ERP API later means writing a
class that implements `execute()` and registering it in EXECUTORS; no
change to the approval workflow, the API, or the dashboard.

No real email is sent and no real purchase order is submitted anywhere
in this prototype -- every executor below only returns a structured
result that gets stored on the AgentAction row itself.
"""

from __future__ import annotations

import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from omni_retail.models import ActionType
from omni_retail.models.agent_action import AgentAction

# A supplier can't be assumed to fulfill an arbitrarily large single
# order. This gives the restock executor a realistic, deterministic
# failure mode -- useful for demonstrating (and testing) the
# executed/failed distinction without any real randomness.
MAX_SUPPLIER_QUANTITY = 500


class ExecutionOutcome:
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class ExecutionResult:
    outcome: str
    reference: str
    detail: str
    failure_reason: Optional[str] = None


class ActionExecutor(ABC):
    @abstractmethod
    def execute(self, action: AgentAction, parameters: dict[str, Any]) -> ExecutionResult: ...


class SimulatedEmailExecutor(ActionExecutor):
    """Stands in for a real email/CRM send for win-back offers."""

    def execute(self, action: AgentAction, parameters: dict[str, Any]) -> ExecutionResult:
        recipient = parameters.get("customer_email") or "unknown recipient"
        return ExecutionResult(
            outcome=ExecutionOutcome.SUCCESS,
            reference=f"SIM-EMAIL-{secrets.token_hex(6)}",
            detail=f"Simulated win-back email sent to {recipient}.",
        )


class SimulatedTaskExecutor(ActionExecutor):
    """Stands in for creating a task in a real CRM/ticketing system.

    Used for the generic FOLLOWUP_TASK action type -- executing one of
    these is also how a non-customer, non-stock alert gets "acknowledged"
    in this prototype, since alerts themselves aren't persisted rows.
    """

    def execute(self, action: AgentAction, parameters: dict[str, Any]) -> ExecutionResult:
        task = parameters.get("task", "Follow up")
        return ExecutionResult(
            outcome=ExecutionOutcome.SUCCESS,
            reference=f"SIM-TASK-{secrets.token_hex(6)}",
            detail=f"Simulated task created and alert acknowledged: {task}",
        )


class SimulatedPurchaseOrderExecutor(ActionExecutor):
    """Stands in for submitting a purchase order to a real supplier/ERP API."""

    def execute(self, action: AgentAction, parameters: dict[str, Any]) -> ExecutionResult:
        quantity = parameters.get("restock_quantity", 0)
        product_name = parameters.get("product_name", "product")

        if not isinstance(quantity, int) or quantity <= 0:
            return ExecutionResult(
                outcome=ExecutionOutcome.FAILED,
                reference=f"SIM-PO-{secrets.token_hex(6)}",
                detail="",
                failure_reason=f"Restock quantity must be a positive whole number (got {quantity!r}).",
            )
        if quantity > MAX_SUPPLIER_QUANTITY:
            return ExecutionResult(
                outcome=ExecutionOutcome.FAILED,
                reference=f"SIM-PO-{secrets.token_hex(6)}",
                detail="",
                failure_reason=(
                    f"Supplier cannot fulfill orders over {MAX_SUPPLIER_QUANTITY} units in a single "
                    "purchase order (simulated). Approve a smaller quantity or split the order."
                ),
            )
        return ExecutionResult(
            outcome=ExecutionOutcome.SUCCESS,
            reference=f"SIM-PO-{secrets.token_hex(6)}",
            detail=f"Simulated purchase order created for {quantity} units of {product_name}.",
        )


EXECUTORS: dict[ActionType, ActionExecutor] = {
    ActionType.WIN_BACK_OFFER: SimulatedEmailExecutor(),
    ActionType.FOLLOWUP_TASK: SimulatedTaskExecutor(),
    ActionType.RESTOCK_REQUEST: SimulatedPurchaseOrderExecutor(),
}
