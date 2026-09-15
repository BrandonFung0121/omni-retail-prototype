"""Entry point for the AI Business Analyst Agent.

Deterministic pipeline: classify -> retrieve -> synthesize. Each stage
is a plain function/class from this package, so any of the three can
be swapped independently.

An optional LLM-driven agent mode (`ai/llm/`) can additionally reason
over the same read-only tools and choose its own investigation path
instead of the fixed keyword classifier. It is strictly opt-in
(`OMNI_LLM_ENABLED`) and this module is the fallback boundary: if the
LLM path is disabled, unconfigured, or fails in an expected way
(provider unavailable, a call to it failing, or the bounded tool-call
loop running out its budget), `answer_question()` falls straight back
to the deterministic pipeline below -- the same pipeline this module
has always run, unchanged. A genuine programming bug (anywhere in the
LLM path or the deterministic one) is deliberately NOT caught here and
propagates, rather than silently presenting as a normal fallback.

This module never writes to the database or calls an external service
on its own -- the LLM path's only write-shaped capability
(`propose_action`) only ever creates a PROPOSED AgentAction row for
human review (see `actions/service.py::create_manual_proposal`).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from omni_retail.ai.intents import Intent, classify_intent
from omni_retail.ai.llm import config as llm_config
from omni_retail.ai.llm import get_provider
from omni_retail.ai.llm.orchestrator import OrchestrationLimitExceeded, answer_with_llm
from omni_retail.ai.llm.provider import LLMProviderError
from omni_retail.ai.models import AgentResponse
from omni_retail.ai.retrieval import RETRIEVERS
from omni_retail.ai.synthesis import get_synthesizer

logger = logging.getLogger(__name__)

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

    if llm_config.is_llm_enabled():
        provider = get_provider()
        if provider is not None:
            try:
                return answer_with_llm(provider, session, question, today)
            except (LLMProviderError, OrchestrationLimitExceeded) as exc:
                logger.warning(
                    "LLM agent path unavailable for question %r (%s: %s); falling back to the deterministic pipeline.",
                    question,
                    type(exc).__name__,
                    exc,
                )

    return _answer_deterministic(session, question, today)


def _answer_deterministic(session: Session, question: str, today: Optional[date] = None) -> AgentResponse:
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
        evidence = RETRIEVERS[intent](session, today)
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
