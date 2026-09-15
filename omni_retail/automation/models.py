"""Alert data shape for the automation/alerting layer.

An Alert is a plain, JSON-friendly record produced by a rule in
rules.py. Alerts are computed on demand from current data (there is
no alerts table) -- the same way the dashboard's KPIs are computed on
demand -- so "status" is always "open" for now. A future phase that
lets an AI agent investigate/resolve alerts would add persistence at
that point; nothing here needs to change to support that, since
callers only ever see a plain list of Alert objects.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class Severity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# Higher number = shown first.
_SEVERITY_RANK = {Severity.CRITICAL: 2, Severity.WARNING: 1, Severity.INFO: 0}


class AlertType(str, enum.Enum):
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"
    REVENUE_DROP = "revenue_drop"
    EXPENSE_SPIKE = "expense_spike"
    TRAFFIC_CONVERSION_GAP = "traffic_conversion_gap"
    ORDER_FAILURE_PATTERN = "order_failure_pattern"
    CUSTOMER_WIN_BACK_OPPORTUNITY = "customer_win_back_opportunity"


@dataclass
class Alert:
    id: str
    type: AlertType
    severity: Severity
    title: str
    description: str
    recommended_action: str
    supporting_data: dict[str, Any] = field(default_factory=dict)
    detected_at: datetime = field(default_factory=datetime.utcnow)
    status: str = "open"

    @property
    def severity_rank(self) -> int:
        return _SEVERITY_RANK[self.severity]
