"""Maps a free-text question to one of the business questions the
agent knows how to investigate.

This is a keyword classifier, not an LLM call -- intentionally. The
system (not a language model) decides which data gets pulled, so the
agent can never "investigate" the wrong thing or skip investigation
entirely. A future phase could replace this with LLM-driven tool
selection; retrieval.py's functions are already shaped like tools
(one function per data need), so that swap wouldn't touch this file's
callers.
"""

from __future__ import annotations

import enum


class Intent(str, enum.Enum):
    REVENUE_EXPLANATION = "revenue_explanation"
    PRODUCT_PERFORMANCE = "product_performance"
    RESTOCK_PRIORITY = "restock_priority"
    TOP_CUSTOMERS = "top_customers"
    CHURN_RISK = "churn_risk"
    EXPENSE_ANOMALIES = "expense_anomalies"
    TRAFFIC_CONVERSION = "traffic_conversion"
    BUSINESS_ISSUES_SUMMARY = "business_issues_summary"
    UNKNOWN = "unknown"


# Checked in order -- more specific phrasing first, so e.g. a question
# about "at-risk high-value customers" matches CHURN_RISK rather than
# the more generic TOP_CUSTOMERS.
_KEYWORD_RULES: list[tuple[Intent, tuple[str, ...]]] = [
    (
        Intent.BUSINESS_ISSUES_SUMMARY,
        (
            "most important", "biggest issue", "top priorit", "what's wrong",
            "what should i focus", "needs attention", "right now", "action center",
            "business issues", "overall health", "how is the business",
        ),
    ),
    (
        Intent.RESTOCK_PRIORITY,
        (
            "restock", "re-order", "reorder", "out of stock", "low stock",
            "stock level", "running low", "inventory",
        ),
    ),
    (
        Intent.CHURN_RISK,
        (
            "at risk", "churn", "win back", "win-back", "winback", "inactive",
            "stopped buying", "stopped ordering", "haven't ordered", "havent ordered",
            "going cold", "lapsed",
        ),
    ),
    (
        Intent.TOP_CUSTOMERS,
        (
            "valuable customer", "best customer", "top customer", "high-value customer",
            "high value customer", "biggest spender", "who spends", "loyal customer",
        ),
    ),
    (
        Intent.EXPENSE_ANOMALIES,
        (
            "expense", "spending pattern", "cost increase", "unusual spend",
            "spending unusual", "operating cost", "overspend",
        ),
    ),
    (
        Intent.TRAFFIC_CONVERSION,
        (
            "traffic", "conversion", "visitor", "website performance", "converting",
        ),
    ),
    (
        Intent.REVENUE_EXPLANATION,
        (
            "why did revenue", "why is revenue", "revenue increase", "revenue decrease",
            "revenue drop", "revenue change", "revenue up", "revenue down",
            "sales increase", "sales decrease", "sales drop", "why did sales",
        ),
    ),
    (
        Intent.PRODUCT_PERFORMANCE,
        (
            "best selling", "best-selling", "worst product", "top product",
            "which product", "product performance", "underperform", "top seller",
            "best product",
        ),
    ),
]

# Looser, single-word fallback -- tried only if nothing above matched.
_FALLBACK_RULES: list[tuple[Intent, tuple[str, ...]]] = [
    (Intent.RESTOCK_PRIORITY, ("stock", "inventory")),
    (Intent.CHURN_RISK, ("risk",)),
    (Intent.TOP_CUSTOMERS, ("customer",)),
    (Intent.EXPENSE_ANOMALIES, ("expense", "cost")),
    (Intent.TRAFFIC_CONVERSION, ("traffic", "website")),
    (Intent.REVENUE_EXPLANATION, ("revenue", "sales")),
    (Intent.PRODUCT_PERFORMANCE, ("product",)),
]


def classify_intent(question: str) -> Intent:
    text = question.lower()

    for intent, keywords in _KEYWORD_RULES:
        if any(kw in text for kw in keywords):
            return intent

    for intent, keywords in _FALLBACK_RULES:
        if any(kw in text for kw in keywords):
            return intent

    return Intent.UNKNOWN
