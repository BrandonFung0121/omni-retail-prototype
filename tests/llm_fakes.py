"""Scripted `LLMProvider` test doubles.

No network call, no `anthropic` package, no API key -- these implement
the exact same `LLMProvider` interface `anthropic_provider.py` does, so
`orchestrator.py` and `ai/agent.py` are tested against the real
contract without ever touching a paid API. Not a test_*.py module on
purpose, so pytest doesn't try to collect it as a test file.
"""

from __future__ import annotations

from typing import Any

from omni_retail.ai.llm.provider import ConversationTurn, LLMProvider, LLMTurnResult, ToolCall


class FakeLLMProvider(LLMProvider):
    """Returns a fixed sequence of `LLMTurnResult`s (or raises a
    pre-supplied exception) on successive `run_turn()` calls."""

    def __init__(self, turns: list[LLMTurnResult | Exception]):
        self._turns = list(turns)
        self.calls: list[tuple[str, list[ConversationTurn], list[dict[str, Any]]]] = []

    def run_turn(self, system: str, transcript: list[ConversationTurn], tools: list[dict[str, Any]]) -> LLMTurnResult:
        self.calls.append((system, list(transcript), tools))
        if not self._turns:
            raise AssertionError("FakeLLMProvider ran out of scripted turns")
        item = self._turns.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class RepeatingToolCallProvider(LLMProvider):
    """Always asks for the same tool call and never produces a final
    answer -- for exercising the orchestrator's iteration/tool-call
    budget."""

    def __init__(self, tool_name: str, arguments: dict[str, Any] | None = None):
        self._tool_name = tool_name
        self._arguments = arguments or {}
        self._counter = 0

    def run_turn(self, system: str, transcript: list[ConversationTurn], tools: list[dict[str, Any]]) -> LLMTurnResult:
        self._counter += 1
        call = ToolCall(id=f"call-{self._counter}", name=self._tool_name, arguments=dict(self._arguments))
        return LLMTurnResult(stop_reason="tool_use", tool_calls=[call])
