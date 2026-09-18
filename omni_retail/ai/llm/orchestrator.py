"""Bounded LLM tool-calling loop, shared by every agent in this
codebase (currently: the admin AI Business Analyst below, and the
storefront shopping assistant in `ai/storefront_agent.py`).

User question -> LLM reasoning -> tool selection -> tool execution
(real OMNI data, or a PROPOSED-only action) -> tool result -> LLM
reasoning/synthesis -> grounded answer. Every tool call is traced; the
loop can never run unbounded (`OrchestrationLimitExceeded`); and the
two failure modes that must never break the app -- the provider being
unavailable or a call to it failing -- surface as the typed exceptions
from `provider.py` that each agent's entry point catches explicitly to
fall back to its own non-LLM behavior.

Unknown or malformed tool calls from the model are recoverable *within*
the loop (fed back as a tool error result, per Anthropic's tool-use
convention) -- they don't trigger the outer fallback, since that would
hide a model asking for the wrong thing behind "the LLM is down."

`run_tool_loop()` below is registry-agnostic on purpose: it takes a
system prompt, a tool schema list, and a `dispatch` callable, and knows
nothing about which registry they came from. This is what lets the
storefront agent reuse the exact same bounded-loop mechanics against
its own, separately-scoped tool registry without importing anything
from the admin `ai/llm/tools.py` module -- there is no code path by
which a storefront request can reach an admin tool.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from omni_retail.ai.llm import config as llm_config
from omni_retail.ai.llm.provider import ConversationTurn, LLMProvider, ToolResultMessage
from omni_retail.ai.llm.tool_kit import ToolArgumentError, UnknownToolError
from omni_retail.ai.llm.tools import dispatch_tool, get_tool_schemas
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
    without the model producing a final answer. Caught by each agent's
    entry point to trigger its own fallback."""


@dataclass
class ToolCallRecord:
    """One tool call the loop made, with its full (untruncated)
    result/error string -- callers that need structured data out of a
    specific tool (e.g. the storefront agent reading an `add_to_cart`
    result) parse `result` themselves; callers that only want a
    display trace (e.g. the admin agent) truncate it on their own
    terms."""

    tool: str
    arguments: dict[str, Any]
    ok: bool
    result: str


@dataclass
class ToolLoopResult:
    text: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)


def _trace_dict(entry: ToolCallRecord) -> dict[str, Any]:
    summary = entry.result[:_TRACE_SUMMARY_CHARS] if entry.ok else entry.result
    return {"tool": entry.tool, "arguments": entry.arguments, "ok": entry.ok, "summary": summary}


def run_tool_loop(
    provider: LLMProvider,
    transcript: list[ConversationTurn],
    *,
    system_prompt: str,
    tool_schemas: list[dict[str, Any]],
    dispatch: Callable[[str, dict[str, Any]], str],
    max_iterations: int,
    max_tool_calls: int,
    budget_exhausted_message: str = "Tool call budget exhausted for this request. Answer now using only the evidence already gathered.",
) -> ToolLoopResult:
    """The registry-agnostic bounded loop. `dispatch(name, arguments)`
    must raise `UnknownToolError`/`ToolArgumentError` for a bad request
    from the model (recovered within the loop) and let anything else
    propagate (a real bug must never look like "the model asked for
    something invalid"). Raises `OrchestrationLimitExceeded` if the
    model never produces a final answer within budget."""
    trace: list[ToolCallRecord] = []
    tool_calls_used = 0

    for _iteration in range(max_iterations):
        turn = provider.run_turn(system_prompt, transcript, tool_schemas)

        if turn.stop_reason == "end_turn" or not turn.tool_calls:
            return ToolLoopResult(text=turn.text, tool_calls=trace)

        transcript.append(ConversationTurn(role="assistant", text=turn.text, tool_calls=turn.tool_calls))

        results: list[ToolResultMessage] = []
        for call in turn.tool_calls:
            if tool_calls_used >= max_tool_calls:
                results.append(ToolResultMessage(tool_call_id=call.id, content=budget_exhausted_message, is_error=True))
                logger.info("LLM tool call skipped (budget exhausted): %s(%r)", call.name, call.arguments)
                continue

            tool_calls_used += 1
            try:
                payload = dispatch(call.name, call.arguments)
            except (UnknownToolError, ToolArgumentError) as exc:
                results.append(ToolResultMessage(tool_call_id=call.id, content=str(exc), is_error=True))
                trace.append(ToolCallRecord(call.name, call.arguments, False, str(exc)))
                logger.info("LLM tool call rejected: %s(%r): %s", call.name, call.arguments, exc)
                continue

            results.append(ToolResultMessage(tool_call_id=call.id, content=payload))
            trace.append(ToolCallRecord(call.name, call.arguments, True, payload))
            logger.info("LLM tool call: %s(%r) -> %d bytes", call.name, call.arguments, len(payload))

        transcript.append(ConversationTurn(role="tool_results", tool_results=results))

    raise OrchestrationLimitExceeded(
        f"No final answer after {max_iterations} iteration(s) / {tool_calls_used} tool call(s)."
    )


def answer_with_llm(
    provider: LLMProvider,
    session: Session,
    question: str,
    today: Optional[date] = None,
) -> AgentResponse:
    transcript: list[ConversationTurn] = [ConversationTurn(role="user", text=question)]

    result = run_tool_loop(
        provider,
        transcript,
        system_prompt=SYSTEM_PROMPT,
        tool_schemas=get_tool_schemas(),
        dispatch=lambda name, arguments: dispatch_tool(session, name, arguments, question=question, today=today),
        max_iterations=llm_config.max_iterations(),
        max_tool_calls=llm_config.max_tool_calls(),
    )
    trace = [_trace_dict(entry) for entry in result.tool_calls]

    return AgentResponse(
        question=question,
        intent="llm_orchestrated",
        answer=result.text or "I wasn't able to find a grounded answer to that.",
        confidence="high" if trace else "low",
        generated_by="llm",
        tool_trace=trace,
    )
