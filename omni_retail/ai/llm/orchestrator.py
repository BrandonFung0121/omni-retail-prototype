"""Bounded LLM tool-calling loop for the AI Business Analyst.

User question -> LLM reasoning -> tool selection -> tool execution
(real OMNI data, or a PROPOSED-only action) -> tool result -> LLM
reasoning/synthesis -> grounded answer. Every tool call is traced; the
loop can never run unbounded (`OrchestrationLimitExceeded`); and the
two failure modes that must never break the app -- the provider being
unavailable or a call to it failing -- surface as the typed exceptions
from `provider.py` that `ai/agent.py` catches explicitly to fall back
to the deterministic Phase 4 pipeline.

Unknown or malformed tool calls from the model are recoverable *within*
the loop (fed back as a tool error result, per Anthropic's tool-use
convention) -- they don't trigger the outer fallback, since that would
hide a model asking for the wrong thing behind "the LLM is down."
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from sqlalchemy.orm import Session

from omni_retail.ai.llm import config as llm_config
from omni_retail.ai.llm.provider import ConversationTurn, LLMProvider, ToolResultMessage
from omni_retail.ai.llm.tools import ToolArgumentError, UnknownToolError, dispatch_tool, get_tool_schemas
from omni_retail.ai.models import AgentResponse

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are the OMNI Retail AI Business Analyst. Answer the merchant's question "
    "using ONLY the provided tools -- every tool reads real, current business data. "
    "Call at least one tool before answering, unless the question has nothing to do "
    "with the business. Never state a number or fact that didn't come from a tool "
    "result. If your answer implies an action that would change business state "
    "(sending an offer, reordering stock, creating a follow-up task), call "
    "propose_action -- you cannot approve or execute anything yourself; a human "
    "always reviews and approves it first. Once you have enough evidence, give a "
    "concise, grounded answer and stop calling tools."
)

_TRACE_SUMMARY_CHARS = 200


class OrchestrationLimitExceeded(Exception):
    """The bounded loop reached its iteration or tool-call budget
    without the model producing a final answer. Caught by ai/agent.py
    to trigger the deterministic fallback."""


@dataclass
class ToolTraceEntry:
    tool: str
    arguments: dict[str, Any]
    ok: bool
    summary: str


def _trace_dict(entry: ToolTraceEntry) -> dict[str, Any]:
    return {"tool": entry.tool, "arguments": entry.arguments, "ok": entry.ok, "summary": entry.summary}


def answer_with_llm(
    provider: LLMProvider,
    session: Session,
    question: str,
    today: Optional[date] = None,
) -> AgentResponse:
    max_iterations = llm_config.max_iterations()
    max_tool_calls = llm_config.max_tool_calls()

    transcript: list[ConversationTurn] = [ConversationTurn(role="user", text=question)]
    tool_schemas = get_tool_schemas()
    trace: list[dict[str, Any]] = []
    tool_calls_used = 0

    for _iteration in range(max_iterations):
        turn = provider.run_turn(SYSTEM_PROMPT, transcript, tool_schemas)

        if turn.stop_reason == "end_turn" or not turn.tool_calls:
            return AgentResponse(
                question=question,
                intent="llm_orchestrated",
                answer=turn.text or "I wasn't able to find a grounded answer to that.",
                confidence="high" if trace else "low",
                generated_by="llm",
                tool_trace=trace,
            )

        transcript.append(ConversationTurn(role="assistant", text=turn.text, tool_calls=turn.tool_calls))

        results: list[ToolResultMessage] = []
        for call in turn.tool_calls:
            if tool_calls_used >= max_tool_calls:
                message = "Tool call budget exhausted for this request. Answer now using only the evidence already gathered."
                results.append(ToolResultMessage(tool_call_id=call.id, content=message, is_error=True))
                logger.info("LLM tool call skipped (budget exhausted): %s(%r)", call.name, call.arguments)
                continue

            tool_calls_used += 1
            try:
                payload = dispatch_tool(session, call.name, call.arguments, question=question, today=today)
            except (UnknownToolError, ToolArgumentError) as exc:
                results.append(ToolResultMessage(tool_call_id=call.id, content=str(exc), is_error=True))
                trace.append(_trace_dict(ToolTraceEntry(call.name, call.arguments, False, str(exc))))
                logger.info("LLM tool call rejected: %s(%r): %s", call.name, call.arguments, exc)
                continue

            results.append(ToolResultMessage(tool_call_id=call.id, content=payload))
            trace.append(_trace_dict(ToolTraceEntry(call.name, call.arguments, True, payload[:_TRACE_SUMMARY_CHARS])))
            logger.info("LLM tool call: %s(%r) -> %d bytes", call.name, call.arguments, len(payload))

        transcript.append(ConversationTurn(role="tool_results", tool_results=results))

    raise OrchestrationLimitExceeded(
        f"No final answer after {max_iterations} iteration(s) / {tool_calls_used} tool call(s) for question: {question!r}"
    )
