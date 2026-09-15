"""Gathers the evidence each intent needs, and nothing else.

Every function here is a thin read-only call into services/analytics.py
and/or automation/rules.py -- this file computes no business numbers
of its own. Each function's shape (session in, plain dict out) makes
it directly usable as an LLM function-calling "tool" in a later phase
without modification.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from omni_retail import services
from omni_retail.automation import config, rules
from omni_retail.automation.engine import run_all_rules


def gather_revenue_explanation(session: Session, today: Optional[date] = None) -> dict[str, Any]:
    today = today or date.today()
    start = today - timedelta(days=config.REVENUE_PERIOD_DAYS - 1)
    prev_start, prev_end = rules.prior_period(start, today)

    current_revenue = services.revenue(session, start, today)
    previous_revenue = services.revenue(session, prev_start, prev_end)
    pct_change = (current_revenue - previous_revenue) / previous_revenue * 100 if previous_revenue else None

    current_products = {p.product_id: p for p in services.top_products(session, start, today, limit=100)}
    previous_products = {p.product_id: p for p in services.top_products(session, prev_start, prev_end, limit=100)}
    movers = []
    for product_id in set(current_products) | set(previous_products):
        cur = current_products.get(product_id)
        prev = previous_products.get(product_id)
        cur_rev = cur.revenue if cur else 0.0
        prev_rev = prev.revenue if prev else 0.0
        movers.append(
            {
                "name": (cur or prev).name,
                "current_revenue": cur_rev,
                "previous_revenue": prev_rev,
                "delta": cur_rev - prev_rev,
            }
        )
    movers.sort(key=lambda m: m["delta"])
    biggest_decliners = [m for m in movers if m["delta"] < 0][:3]
    biggest_gainers = [m for m in movers if m["delta"] > 0][-3:][::-1]

    alerts = rules.detect_revenue_drop(session, today=today)

    return {
        "period_start": start,
        "period_end": today,
        "current_revenue": current_revenue,
        "previous_revenue": previous_revenue,
        "pct_change": round(pct_change, 1) if pct_change is not None else None,
        "biggest_decliners": biggest_decliners,
        "biggest_gainers": biggest_gainers,
        "alerts": alerts,
    }


def gather_product_performance(session: Session, today: Optional[date] = None) -> dict[str, Any]:
    today = today or date.today()
    start = today - timedelta(days=config.REVENUE_PERIOD_DAYS - 1)

    by_revenue = services.top_products(session, start, today, limit=1000, by="revenue")
    best_sellers = by_revenue[:5]
    worst_sellers = by_revenue[-5:][::-1] if len(by_revenue) > 5 else []

    low_stock_ids = {inv.product_id for inv in services.low_stock_products(session)}
    at_risk_bestsellers = [p for p in best_sellers if p.product_id in low_stock_ids]

    return {
        "period_start": start,
        "period_end": today,
        "best_sellers": best_sellers,
        "worst_sellers": worst_sellers,
        "products_with_sales": len(by_revenue),
        "at_risk_bestsellers": at_risk_bestsellers,
    }


def gather_restock_priority(session: Session, today: Optional[date] = None) -> dict[str, Any]:
    flagged = services.low_stock_products(session)
    out_of_stock_alerts = rules.detect_out_of_stock(session)
    low_stock_alerts = rules.detect_low_stock(session)
    return {
        "flagged_products": flagged,
        "out_of_stock_count": len(out_of_stock_alerts),
        "low_stock_count": len(low_stock_alerts),
        "alerts": out_of_stock_alerts + low_stock_alerts,
    }


def gather_top_customers(session: Session, today: Optional[date] = None) -> dict[str, Any]:
    customers = services.high_value_customers(session, limit=10)
    at_risk_ids = {a.supporting_data["customer_id"] for a in rules.detect_customer_win_back_opportunities(session, today=today)}
    at_risk_top_customers = [c for c in customers if c.customer_id in at_risk_ids]
    return {"customers": customers, "at_risk_top_customers": at_risk_top_customers}


def gather_churn_risk(session: Session, today: Optional[date] = None) -> dict[str, Any]:
    alerts = rules.detect_customer_win_back_opportunities(session, today=today)
    return {"alerts": alerts}


def gather_expense_anomalies(session: Session, today: Optional[date] = None) -> dict[str, Any]:
    today = today or date.today()
    start = today.replace(day=1)
    current_by_category = services.expenses_by_category(session, start, today)
    alerts = rules.detect_expense_spike(session, today=today)
    return {
        "period_start": start,
        "period_end": today,
        "current_by_category": current_by_category,
        "alerts": alerts,
    }


def gather_traffic_conversion(session: Session, today: Optional[date] = None) -> dict[str, Any]:
    today = today or date.today()
    start = today - timedelta(days=config.TRAFFIC_PERIOD_DAYS - 1)
    prev_start, prev_end = rules.prior_period(start, today)

    current = services.website_traffic_summary(session, start, today)
    previous = services.website_traffic_summary(session, prev_start, prev_end)
    alerts = rules.detect_traffic_conversion_gap(session, today=today)

    return {
        "period_start": start,
        "period_end": today,
        "current": current,
        "previous": previous,
        "alerts": alerts,
    }


def gather_business_issues_summary(session: Session, today: Optional[date] = None) -> dict[str, Any]:
    return {"alerts": run_all_rules(session, today=today)}
