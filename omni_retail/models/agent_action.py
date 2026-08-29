import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omni_retail.database import Base


class ActionType(str, enum.Enum):
    WIN_BACK_OFFER = "win_back_offer"
    RESTOCK_REQUEST = "restock_request"
    FOLLOWUP_TASK = "followup_task"


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActionStatus(str, enum.Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"


class AgentAction(Base):
    """A structured business action the AI proposed, and the full record of
    what happened to it afterward.

    Rows are written only by omni_retail/actions/service.py -- the same
    "single write path" convention as transactions/service.py -- so the
    lifecycle (proposed -> approved/rejected -> executed/failed) can never
    be skipped or reordered from elsewhere. `source_alert_id` stores the
    alert's own deterministic string id (e.g. "low_stock:7") rather than a
    foreign key, since alerts are computed on demand and never persisted.
    """

    __tablename__ = "agent_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    action_type: Mapped[ActionType] = mapped_column(Enum(ActionType))
    source_alert_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"), nullable=True)
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id"), nullable=True)

    business_reason: Mapped[str] = mapped_column(Text)
    supporting_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    proposed_parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Human edits to the proposed parameters, applied at approval time.
    # None until an admin actually edits something.
    edited_parameters: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    expected_outcome: Mapped[str] = mapped_column(Text)
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel))

    status: Mapped[ActionStatus] = mapped_column(Enum(ActionStatus), default=ActionStatus.PROPOSED)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Free-text name/email of whoever approved or rejected -- there is no
    # admin-user table in this prototype to hang a real foreign key off of.
    decided_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    execution_result: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    customer: Mapped[Optional["Customer"]] = relationship()
    product: Mapped[Optional["Product"]] = relationship()

    def __repr__(self) -> str:
        return f"AgentAction(id={self.id!r}, action_type={self.action_type!r}, status={self.status!r})"
