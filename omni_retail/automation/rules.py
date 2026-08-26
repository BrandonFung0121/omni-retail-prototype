"""Business-condition detectors.

Each `detect_*` function takes a DB session and returns a list of
Alert objects. Every rule is read-only and stateless: it calls into
`services/analytics.py` for numbers (never recomputes them) and turns
the result into a structured Alert if a threshold is crossed. Rules
know nothing about each other, the API, or the dashboard -- they can
be called individually (e.g. by a future AI agent that only cares
about inventory) or all together via `engine.run_all_rules`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from omni_retail import services
from omni_retail.automation import config
from omni_retail.automation.models import Alert, AlertType, Severity
from omni_retail.models import InventoryStatus, OrderStatus


def prior_period(start: date, end: date) -> tuple[date, date]:
    span = (end - start).days + 1
    prior_end = start - timedelta(days=1)
    prior_start = prior_end - timedelta(days=span - 1)
    return prior_start, prior_end


def _calendar_month_bounds(anchor: date, months_back: int = 0) -> tuple[date, date]:
    year, month = anchor.year, anchor.month
    for _ in range(months_back):
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    start = date(year, month, 1)
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, next_month - timedelta(days=1)


def detect_low_stock(session: Session, **_kwargs) -> list[Alert]:
    alerts = []
    for inv in services.low_stock_products(session):
        if inv.status != InventoryStatus.LOW_STOCK:
            continue
        alerts.append(
            Alert(
                id=f"low_stock:{inv.product_id}",
                type=AlertType.LOW_STOCK,
                severity=Severity.WARNING,
                title=f"{inv.product.name} is running low on stock",
                description=(
                    f"{inv.current_stock} units remain, at or below the reorder "
                    f"threshold of {inv.reorder_threshold}."
                ),
                recommended_action="Place a reorder soon to avoid a stockout.",
                supporting_data={
                    "product_id": inv.product_id,
                    "product_name": inv.product.name,
                    "category": inv.product.category,
                    "current_stock": inv.current_stock,
                    "reorder_threshold": inv.reorder_threshold,
                },
            )
        )
    return alerts


def detect_out_of_stock(session: Session, **_kwargs) -> list[Alert]:
    alerts = []
    for inv in services.low_stock_products(session):
        if inv.status != InventoryStatus.OUT_OF_STOCK:
            continue
        alerts.append(
            Alert(
                id=f"out_of_stock:{inv.product_id}",
                type=AlertType.OUT_OF_STOCK,
                severity=Severity.CRITICAL,
                title=f"{inv.product.name} is out of stock",
                description=f"{inv.product.name} has 0 units in stock and cannot be sold.",
                recommended_action="Reorder immediately and consider hiding the product from sale until restocked.",
                supporting_data={
                    "product_id": inv.product_id,
                    "product_name": inv.product.name,
                    "category": inv.product.category,
                    "current_stock": inv.current_stock,
                    "reorder_threshold": inv.reorder_threshold,
                },
            )
        )
    return alerts


def detect_revenue_drop(session: Session, today: Optional[date] = None, **_kwargs) -> list[Alert]:
    today = today or date.today()
    start = today - timedelta(days=config.REVENUE_PERIOD_DAYS - 1)
    prev_start, prev_end = prior_period(start, today)

    current = services.revenue(session, start, today)
    previous = services.revenue(session, prev_start, prev_end)
    if previous <= 0:
        return []

    pct_change = (current - previous) / previous * 100
    if pct_change > -config.REVENUE_DROP_WARNING_PCT:
        return []

    severity = Severity.CRITICAL if pct_change <= -config.REVENUE_DROP_CRITICAL_PCT else Severity.WARNING
    return [
        Alert(
            id=f"revenue_drop:{start.isoformat()}:{today.isoformat()}",
            type=AlertType.REVENUE_DROP,
            severity=severity,
            title=f"Revenue is down {abs(pct_change):.1f}% vs. the prior period",
            description=(
                f"Revenue for {start.isoformat()} to {today.isoformat()} was ${current:,.2f}, "
                f"down from ${previous:,.2f} in the {config.REVENUE_PERIOD_DAYS} days before that."
            ),
            recommended_action=(
                "Review which products or channels declined most and consider a promotion "
                "or outreach campaign to recover volume."
            ),
            supporting_data={
                "period_start": start.isoformat(),
                "period_end": today.isoformat(),
                "current_revenue": current,
                "previous_revenue": previous,
                "pct_change": round(pct_change, 1),
            },
        )
    ]


def detect_expense_spike(session: Session, today: Optional[date] = None, **_kwargs) -> list[Alert]:
    today = today or date.today()
    cur_start, cur_end = _calendar_month_bounds(today, months_back=0)
    prev_start, prev_end = _calendar_month_bounds(today, months_back=1)

    current = services.expenses_by_category(session, cur_start, today)
    previous = services.expenses_by_category(session, prev_start, prev_end)

    alerts = []
    for category, current_amount in current.items():
        previous_amount = previous.get(category, 0.0)
        if previous_amount <= 0:
            continue
        pct_change = (current_amount - previous_amount) / previous_amount * 100
        if pct_change < config.EXPENSE_SPIKE_WARNING_PCT:
            continue

        severity = Severity.CRITICAL if pct_change >= config.EXPENSE_SPIKE_CRITICAL_PCT else Severity.WARNING
        alerts.append(
            Alert(
                id=f"expense_spike:{category.value}:{cur_start.isoformat()}",
                type=AlertType.EXPENSE_SPIKE,
                severity=severity,
                title=f"{category.value.title()} spend is up {pct_change:.0f}% this month",
                description=(
                    f"{category.value.title()} spend so far this month is ${current_amount:,.2f}, "
                    f"vs ${previous_amount:,.2f} for all of last month."
                ),
                recommended_action=f"Review recent {category.value} expenses for one-off or unnecessary charges.",
                supporting_data={
                    "category": category.value,
                    "current_month_start": cur_start.isoformat(),
                    "current_amount": current_amount,
                    "previous_month_start": prev_start.isoformat(),
                    "previous_amount": previous_amount,
                    "pct_change": round(pct_change, 1),
                },
            )
        )
    return alerts


def detect_traffic_conversion_gap(session: Session, today: Optional[date] = None, **_kwargs) -> list[Alert]:
    today = today or date.today()
    start = today - timedelta(days=config.TRAFFIC_PERIOD_DAYS - 1)
    prev_start, prev_end = prior_period(start, today)

    current = services.website_traffic_summary(session, start, today)
    previous = services.website_traffic_summary(session, prev_start, prev_end)
    if previous.visitors <= 0:
        return []

    visitor_growth_pct = (current.visitors - previous.visitors) / previous.visitors * 100
    if visitor_growth_pct < config.TRAFFIC_SPIKE_VISITOR_GROWTH_WARNING_PCT:
        return []

    conversion_kept_pace = current.conversion_rate >= previous.conversion_rate * config.TRAFFIC_CONVERSION_KEEP_PACE_TOLERANCE
    if conversion_kept_pace:
        return []

    severity = (
        Severity.CRITICAL if visitor_growth_pct >= config.TRAFFIC_SPIKE_VISITOR_GROWTH_CRITICAL_PCT else Severity.WARNING
    )
    return [
        Alert(
            id=f"traffic_conversion_gap:{start.isoformat()}:{today.isoformat()}",
            type=AlertType.TRAFFIC_CONVERSION_GAP,
            severity=severity,
            title=f"Traffic is up {visitor_growth_pct:.0f}% but conversion rate hasn't followed",
            description=(
                f"Visitors grew from {previous.visitors:,} to {current.visitors:,} "
                f"({visitor_growth_pct:.1f}%), while conversion rate moved from "
                f"{previous.conversion_rate}% to {current.conversion_rate}%."
            ),
            recommended_action=(
                "Check which traffic source is driving the increase and whether landing "
                "pages/offers match that traffic's intent."
            ),
            supporting_data={
                "period_start": start.isoformat(),
                "period_end": today.isoformat(),
                "current_visitors": current.visitors,
                "previous_visitors": previous.visitors,
                "visitor_growth_pct": round(visitor_growth_pct, 1),
                "current_conversion_rate": current.conversion_rate,
                "previous_conversion_rate": previous.conversion_rate,
            },
        )
    ]


def detect_order_failure_pattern(session: Session, today: Optional[date] = None, **_kwargs) -> list[Alert]:
    today = today or date.today()
    start = today - timedelta(days=config.ORDER_PERIOD_DAYS - 1)

    counts = services.order_status_counts(session, start, today)
    total = sum(counts.values())
    if total == 0:
        return []

    problem_count = counts[OrderStatus.CANCELLED] + counts[OrderStatus.REFUNDED]
    rate_pct = problem_count / total * 100
    if rate_pct < config.ORDER_FAILURE_RATE_WARNING_PCT:
        return []

    severity = Severity.CRITICAL if rate_pct >= config.ORDER_FAILURE_RATE_CRITICAL_PCT else Severity.WARNING
    return [
        Alert(
            id=f"order_failure_pattern:{start.isoformat()}:{today.isoformat()}",
            type=AlertType.ORDER_FAILURE_PATTERN,
            severity=severity,
            title=f"{rate_pct:.1f}% of orders were cancelled or refunded this period",
            description=(
                f"Of {total} orders placed between {start.isoformat()} and {today.isoformat()}, "
                f"{counts[OrderStatus.CANCELLED]} were cancelled and {counts[OrderStatus.REFUNDED]} were refunded."
            ),
            recommended_action=(
                "Look for a common cause (payment method, product, or channel) across the "
                "cancelled/refunded orders before it affects more customers."
            ),
            supporting_data={
                "period_start": start.isoformat(),
                "period_end": today.isoformat(),
                "total_orders": total,
                "cancelled": counts[OrderStatus.CANCELLED],
                "refunded": counts[OrderStatus.REFUNDED],
                "completed": counts[OrderStatus.COMPLETED],
                "pending": counts[OrderStatus.PENDING],
                "failure_rate_pct": round(rate_pct, 1),
            },
        )
    ]


def detect_customer_win_back_opportunities(session: Session, today: Optional[date] = None, **_kwargs) -> list[Alert]:
    today = today or date.today()
    alerts = []
    for customer in services.high_value_customers(session, limit=config.CUSTOMER_POOL_SIZE):
        last_order = services.last_order_date(session, customer.customer_id)
        if last_order is None:
            continue
        days_since = (today - last_order).days
        if days_since < config.CHURN_RISK_DAYS_WARNING:
            continue

        severity = Severity.CRITICAL if days_since >= config.CHURN_RISK_DAYS_CRITICAL else Severity.WARNING
        alerts.append(
            Alert(
                id=f"customer_win_back:{customer.customer_id}",
                type=AlertType.CUSTOMER_WIN_BACK_OPPORTUNITY,
                severity=severity,
                title=f"{customer.name} hasn't ordered in {days_since} days",
                description=(
                    f"{customer.name} has spent ${customer.total_spent:,.2f} across "
                    f"{customer.order_count} orders (avg ${customer.average_order_value:,.2f}), "
                    f"but last ordered on {last_order.isoformat()}."
                ),
                recommended_action="Reach out with a personalized win-back offer before this relationship goes cold.",
                supporting_data={
                    "customer_id": customer.customer_id,
                    "customer_name": customer.name,
                    "customer_email": customer.email,
                    "total_spent": customer.total_spent,
                    "order_count": customer.order_count,
                    "average_order_value": customer.average_order_value,
                    "last_order_date": last_order.isoformat(),
                    "days_since_last_order": days_since,
                },
            )
        )
    return alerts
