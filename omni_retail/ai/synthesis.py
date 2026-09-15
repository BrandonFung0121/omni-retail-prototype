"""Turns retrieved evidence into an answer a business owner can read.

`TemplateAnswerSynthesizer` is deterministic and has no external
dependency -- every sentence is built directly from the numbers
`retrieval.py` fetched, so nothing in the answer can be un-grounded.

This is deliberately swappable: a future `LLMAnswerSynthesizer` would
implement the same `synthesize(question, intent, evidence)` contract,
using the identical evidence dict as its prompt context (with
instructions to answer only from that data), and `agent.py` would
pick whichever synthesizer `get_synthesizer()` returns. No caller
needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from omni_retail.ai.intents import Intent
from omni_retail.automation.models import Alert


@dataclass
class SynthesisResult:
    answer: str
    recommended_actions: list[str] = field(default_factory=list)
    supporting_metrics: dict[str, Any] = field(default_factory=dict)
    related_alert_ids: list[str] = field(default_factory=list)


class AnswerSynthesizer(ABC):
    @abstractmethod
    def synthesize(self, question: str, intent: Intent, evidence: dict[str, Any]) -> SynthesisResult: ...


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _alert_ids(alerts: list[Alert]) -> list[str]:
    return [a.id for a in alerts]


def _alert_summaries(alerts: list[Alert]) -> list[dict[str, Any]]:
    return [{"id": a.id, "severity": a.severity.value, "title": a.title} for a in alerts]


def _dedup(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


class TemplateAnswerSynthesizer(AnswerSynthesizer):
    def synthesize(self, question: str, intent: Intent, evidence: dict[str, Any]) -> SynthesisResult:
        handler = getattr(self, f"_synthesize_{intent.value}", None)
        if handler is None:
            return self._synthesize_unknown(question)
        return handler(evidence)

    def _synthesize_revenue_explanation(self, evidence: dict[str, Any]) -> SynthesisResult:
        current = evidence["current_revenue"]
        previous = evidence["previous_revenue"]
        pct = evidence["pct_change"]
        decliners = evidence["biggest_decliners"]
        gainers = evidence["biggest_gainers"]
        alerts: list[Alert] = evidence["alerts"]
        n_days = (evidence["period_end"] - evidence["period_start"]).days + 1

        if pct is None:
            answer = (
                f"Revenue for the last {n_days} days was {_money(current)}, but there's no revenue in the "
                "prior period to compare against, so I can't say whether that's up or down."
            )
            return SynthesisResult(answer=answer, supporting_metrics={"current_revenue": current})

        direction = "up" if pct > 0 else "down" if pct < 0 else "flat vs."
        answer = (
            f"Revenue over the last {n_days} days was {_money(current)}, "
            f"{direction} {abs(pct):.1f}% from {_money(previous)} in the {n_days} days before that."
        )

        if pct < 0 and decliners:
            names = ", ".join(f"{m['name']} ({_money(m['delta'])})" for m in decliners)
            answer += f" The biggest declines came from: {names}."
        elif pct > 0 and gainers:
            names = ", ".join(f"{m['name']} (+{_money(m['delta'])})" for m in gainers)
            answer += f" The biggest gains came from: {names}."

        if alerts:
            answer += f" This has already been flagged as a {alerts[0].severity.value} alert in the Action Center."

        actions = [a.recommended_action for a in alerts]
        if not actions and pct < 0:
            actions = ["Review the declining products above and check whether it's a demand, pricing, or stock issue."]

        return SynthesisResult(
            answer=answer,
            recommended_actions=_dedup(actions),
            supporting_metrics={
                "current_revenue": current,
                "previous_revenue": previous,
                "pct_change": pct,
                "biggest_decliners": decliners,
                "biggest_gainers": gainers,
            },
            related_alert_ids=_alert_ids(alerts),
        )

    def _synthesize_product_performance(self, evidence: dict[str, Any]) -> SynthesisResult:
        best = evidence["best_sellers"]
        worst = evidence["worst_sellers"]
        at_risk = evidence["at_risk_bestsellers"]
        n_days = (evidence["period_end"] - evidence["period_start"]).days + 1

        if not best:
            return SynthesisResult(answer=f"No products sold in the last {n_days} days.")

        best_text = ", ".join(f"{p.name} ({_money(p.revenue)}, {p.units_sold} units)" for p in best[:3])
        answer = f"Over the last {n_days} days, the top performers were: {best_text}."

        if worst:
            worst_text = ", ".join(f"{p.name} ({_money(p.revenue)})" for p in worst[:3])
            answer += f" The weakest sellers (among products that sold at all) were: {worst_text}."

        actions = []
        if at_risk:
            risk_names = ", ".join(p.name for p in at_risk)
            answer += f" Worth flagging: {risk_names} {'is' if len(at_risk) == 1 else 'are'} a top seller but also low/out of stock."
            actions.append(f"Reorder {risk_names} before the sales momentum is lost to a stockout.")
        if worst:
            actions.append("Consider a promotion, bundle, or markdown for the weakest sellers, or review whether they should stay in the catalog.")

        return SynthesisResult(
            answer=answer,
            recommended_actions=actions,
            supporting_metrics={
                "best_sellers": [{"name": p.name, "revenue": p.revenue, "units_sold": p.units_sold} for p in best],
                "worst_sellers": [{"name": p.name, "revenue": p.revenue, "units_sold": p.units_sold} for p in worst],
            },
        )

    def _synthesize_restock_priority(self, evidence: dict[str, Any]) -> SynthesisResult:
        flagged = evidence["flagged_products"]
        alerts: list[Alert] = evidence["alerts"]

        if not flagged:
            return SynthesisResult(answer="Nothing needs restocking right now — every product is above its reorder threshold.")

        top = flagged[:5]
        listing = "; ".join(f"{inv.product.name} ({inv.current_stock} left, threshold {inv.reorder_threshold})" for inv in top)
        answer = (
            f"{evidence['out_of_stock_count']} product(s) are completely out of stock and "
            f"{evidence['low_stock_count']} are running low. In priority order (most urgent first): {listing}."
        )

        actions = _dedup([a.recommended_action for a in alerts])
        return SynthesisResult(
            answer=answer,
            recommended_actions=actions,
            supporting_metrics={
                "out_of_stock_count": evidence["out_of_stock_count"],
                "low_stock_count": evidence["low_stock_count"],
                "priority_list": [
                    {"name": inv.product.name, "current_stock": inv.current_stock, "reorder_threshold": inv.reorder_threshold}
                    for inv in top
                ],
            },
            related_alert_ids=_alert_ids(alerts),
        )

    def _synthesize_top_customers(self, evidence: dict[str, Any]) -> SynthesisResult:
        customers = evidence["customers"]
        at_risk = evidence["at_risk_top_customers"]

        if not customers:
            return SynthesisResult(answer="No completed orders yet, so there are no customers to rank.")

        listing = "; ".join(f"{c.name} ({_money(c.total_spent)} across {c.order_count} orders)" for c in customers[:5])
        answer = f"Your most valuable customers by total spend are: {listing}."

        actions = ["Consider a loyalty perk or early access offer to protect this revenue base."]
        if at_risk:
            names = ", ".join(c.name for c in at_risk)
            answer += f" Note: {names} {'is' if len(at_risk) == 1 else 'are'} among your top spenders but also haven't ordered recently."
            actions.insert(0, f"Prioritize a win-back outreach to {names} before they churn - they're high-value.")

        return SynthesisResult(
            answer=answer,
            recommended_actions=actions,
            supporting_metrics={
                "top_customers": [
                    {"name": c.name, "total_spent": c.total_spent, "order_count": c.order_count} for c in customers
                ]
            },
        )

    def _synthesize_churn_risk(self, evidence: dict[str, Any]) -> SynthesisResult:
        alerts: list[Alert] = evidence["alerts"]
        if not alerts:
            return SynthesisResult(answer="No high-value customers currently look at risk of churning — everyone in your top spenders has ordered recently.")

        listing = "; ".join(
            f"{a.supporting_data['customer_name']} ({a.supporting_data['days_since_last_order']} days, "
            f"{_money(a.supporting_data['total_spent'])} lifetime)"
            for a in alerts
        )
        answer = f"{len(alerts)} high-value customer(s) look at risk: {listing}."

        return SynthesisResult(
            answer=answer,
            recommended_actions=_dedup([a.recommended_action for a in alerts]),
            supporting_metrics={"at_risk_customers": [a.supporting_data for a in alerts]},
            related_alert_ids=_alert_ids(alerts),
        )

    def _synthesize_expense_anomalies(self, evidence: dict[str, Any]) -> SynthesisResult:
        by_category = evidence["current_by_category"]
        alerts: list[Alert] = evidence["alerts"]
        total = sum(by_category.values())

        if not alerts:
            answer = (
                f"No expense category has spiked unusually this month. Total spend so far is {_money(total)} "
                f"across {len(by_category)} categories."
            )
            return SynthesisResult(answer=answer, supporting_metrics={"total_this_month": total})

        listing = "; ".join(
            f"{a.supporting_data['category']} up {a.supporting_data['pct_change']:.0f}% "
            f"({_money(a.supporting_data['current_amount'])} vs {_money(a.supporting_data['previous_amount'])} last month)"
            for a in alerts
        )
        answer = f"{len(alerts)} expense categor{'y looks' if len(alerts) == 1 else 'ies look'} unusual this month: {listing}."

        return SynthesisResult(
            answer=answer,
            recommended_actions=_dedup([a.recommended_action for a in alerts]),
            supporting_metrics={"total_this_month": total, "flagged_categories": [a.supporting_data for a in alerts]},
            related_alert_ids=_alert_ids(alerts),
        )

    def _synthesize_traffic_conversion(self, evidence: dict[str, Any]) -> SynthesisResult:
        current = evidence["current"]
        previous = evidence["previous"]
        alerts: list[Alert] = evidence["alerts"]
        n_days = (evidence["period_end"] - evidence["period_start"]).days + 1

        visitor_change = (
            (current.visitors - previous.visitors) / previous.visitors * 100 if previous.visitors else None
        )
        answer = (
            f"Over the last {n_days} days: {current.visitors:,} visitors "
            f"({f'{visitor_change:+.1f}%' if visitor_change is not None else 'n/a'} vs. the prior period), "
            f"converting at {current.conversion_rate}% (was {previous.conversion_rate}%)."
        )

        if alerts:
            answer += " Traffic grew without a matching lift in conversions — flagged in the Action Center."
        elif visitor_change is not None and visitor_change > 0 and current.conversion_rate >= previous.conversion_rate:
            answer += " Conversion is keeping pace with the traffic growth, which is healthy."

        actions = _dedup([a.recommended_action for a in alerts])
        return SynthesisResult(
            answer=answer,
            recommended_actions=actions,
            supporting_metrics={
                "current_visitors": current.visitors,
                "previous_visitors": previous.visitors,
                "current_conversion_rate": current.conversion_rate,
                "previous_conversion_rate": previous.conversion_rate,
            },
            related_alert_ids=_alert_ids(alerts),
        )

    def _synthesize_business_issues_summary(self, evidence: dict[str, Any]) -> SynthesisResult:
        alerts: list[Alert] = evidence["alerts"]
        if not alerts:
            return SynthesisResult(answer="No business conditions are currently flagged — everything looks healthy.")

        critical = [a for a in alerts if a.severity.value == "critical"]
        warning = [a for a in alerts if a.severity.value == "warning"]
        top = alerts[:5]
        listing = "; ".join(f"[{a.severity.value}] {a.title}" for a in top)
        answer = (
            f"There are {len(alerts)} open issue(s): {len(critical)} critical, {len(warning)} warning. "
            f"Top priorities: {listing}."
        )

        return SynthesisResult(
            answer=answer,
            recommended_actions=_dedup([a.recommended_action for a in top]),
            supporting_metrics={"total_alerts": len(alerts), "critical": len(critical), "warning": len(warning), "top_alerts": _alert_summaries(top)},
            related_alert_ids=_alert_ids(alerts),
        )

    def _synthesize_unknown(self, question: str) -> SynthesisResult:
        answer = (
            "I'm not sure how to answer that yet. I can currently help with: why revenue changed, which "
            "products are performing best/worst, what to restock first, who your most valuable customers "
            "are, which high-value customers are at risk of churning, unusual expense patterns, whether "
            "website traffic is converting, and a summary of the most important issues right now."
        )
        return SynthesisResult(answer=answer)


def get_synthesizer() -> AnswerSynthesizer:
    return TemplateAnswerSynthesizer()
