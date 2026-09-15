"""Entry point for the AI Business Analyst Agent.

Pipeline: classify -> retrieve -> synthesize. Each stage is a plain
function/class from this package, so any of the three can be swapped
independently (e.g. an LLM-driven intent classifier, or a real LLM
synthesizer) without touching this orchestration.

This phase is read-only end to end: retrieval.py only calls read
functions, and nothing here writes to the database or calls an
external service. Answering a question can never change business
data.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from omni_retail.ai import retrieval
from omni_retail.ai.intents import Intent, classify_intent
from omni_retail.ai.models import AgentResponse
from omni_retail.ai.synthesis import get_synthesizer

logger = logging.getLogger(__name__)

_RETRIEVERS = {
    Intent.REVENUE_EXPLANATION: retrieval.gather_revenue_explanation,
    Intent.PRODUCT_PERFORMANCE: retrieval.gather_product_performance,
    Intent.RESTOCK_PRIORITY: retrieval.gather_restock_priority,
    Intent.TOP_CUSTOMERS: retrieval.gather_top_customers,
    Intent.CHURN_RISK: retrieval.gather_churn_risk,
    Intent.EXPENSE_ANOMALIES: retrieval.gather_expense_anomalies,
    Intent.TRAFFIC_CONVERSION: retrieval.gather_traffic_conversion,
    Intent.BUSINESS_ISSUES_SUMMARY: retrieval.gather_business_issues_summary,
}

EXAMPLE_QUESTIONS = [
    "Why did revenue change this month?",
    "Which products are performing best or worst?",
    "Which products should be restocked first?",
    "Which customers are most valuable?",
    "Which high-value customers are at risk of becoming inactive?",
    "Are there any unusual expense patterns?",
    "Is website traffic converting effectively?",
    "What are the most important business issues right now?",
]


def answer_question(session: Session, question: str, today: Optional[date] = None) -> AgentResponse:
    question = (question or "").strip()
    if not question:
        return AgentResponse(
            question=question,
            intent=Intent.UNKNOWN.value,
            answer="Ask me something about revenue, products, inventory, customers, expenses, or website traffic.",
            confidence="low",
        )

    intent = classify_intent(question)

    if intent == Intent.UNKNOWN:
        result = get_synthesizer().synthesize(question, intent, {})
        return AgentResponse(
            question=question,
            intent=intent.value,
            answer=result.answer,
            confidence="low",
        )

    try:
        evidence = _RETRIEVERS[intent](session, today)
        result = get_synthesizer().synthesize(question, intent, evidence)
    except Exception:
        logger.exception("Agent failed to answer question: %r (intent=%s)", question, intent.value)
        return AgentResponse(
            question=question,
            intent=intent.value,
            answer=(
                "I ran into a problem pulling the data for that question. "
                "Try rephrasing it, or ask about revenue, products, inventory, customers, expenses, or traffic."
            ),
            confidence="low",
        )

    return AgentResponse(
        question=question,
        intent=intent.value,
        answer=result.answer,
        confidence="high",
        supporting_metrics=result.supporting_metrics,
        recommended_actions=result.recommended_actions,
        related_alert_ids=result.related_alert_ids,
    )
