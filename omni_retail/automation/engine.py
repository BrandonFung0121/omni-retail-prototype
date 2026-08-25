"""Runs every detection rule and returns a combined, sorted alert list.

This is the one place that knows the full list of rules. A future
Phase 4 AI agent can either call `run_all_rules` for the same view the
dashboard gets, or import individual `rules.detect_*` functions to
investigate one condition at a time -- both are plain functions
returning `Alert` objects, nothing here is coupled to the API or UI.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from omni_retail.automation import rules
from omni_retail.automation.models import Alert

RULES = (
    rules.detect_out_of_stock,
    rules.detect_low_stock,
    rules.detect_revenue_drop,
    rules.detect_expense_spike,
    rules.detect_traffic_conversion_gap,
    rules.detect_order_failure_pattern,
    rules.detect_customer_win_back_opportunities,
)


def run_all_rules(session: Session, today: Optional[date] = None) -> list[Alert]:
    alerts: list[Alert] = []
    for rule in RULES:
        alerts.extend(rule(session, today=today))
    alerts.sort(key=lambda a: (-a.severity_rank, a.id))
    return alerts
