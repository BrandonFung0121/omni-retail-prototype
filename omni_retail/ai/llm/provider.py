"""Provider-agnostic contract between the orchestrator and a concrete
LLM backend.

`orchestrator.py` only ever imports names from this module -- never a
vendor SDK directly. A concrete provider (e.g. `anthropic_provider.py`)
translates `ConversationTurn`/`ToolCall`/`ToolResultMessage` to and from
its own wire format internally. Adding a second provider later (OpenAI,
a local model, ...) means writing one class here and registering it in
`ai/llm/__init__.py::get_provider()` -- nothing about tool dispatch,
the bounded loop, or `agent.py`'s fallback wiring changes.

The two exception types below are deliberately narrow and are the only
ones `agent.py` catches by name to trigger the deterministic fallback.
A real bug elsewhere (in a tool handler, in the orchestrator itself)
must not subclass either of these, so it propagates instead of being
silently mistaken for "the LLM was unavailable."
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResultMessage:
    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class ConversationTurn:
    """One entry in the provider-agnostic transcript the orchestrator
    maintains. `role="user"` carries the original question (`text`),
    `role="assistant"` carries the model's prior reply (`text` and/or
    `tool_calls`), and `role="tool_results"` carries the outcomes of
    the tool calls the orchestrator just ran (`tool_results`)."""

    role: Literal["user", "assistant", "tool_results"]
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResultMessage] = field(default_factory=list)


@dataclass
class LLMTurnResult:
    """What a provider hands back for one turn: either a final answer
    (`stop_reason="end_turn"`) or a request to run tools
    (`stop_reason="tool_use"`, `tool_calls` non-empty)."""

    stop_reason: Literal["tool_use", "end_turn"]
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProviderError(Exception):
    """Base class for expected, recoverable provider failures."""


class ProviderUnavailableError(LLMProviderError):
    """The provider isn't usable at all -- no API key, SDK not
    installed, etc. Raised at construction time, before any network
    call is attempted."""


class ProviderCallError(LLMProviderError):
    """The provider was reachable/configured but a specific call
    failed (timeout, network error, non-2xx API response, malformed
    response). Vendor-specific exceptions must be caught and re-raised
    as this type inside the concrete provider -- callers of this
    module never need to know which SDK is underneath."""


class LLMProvider(ABC):
    @abstractmethod
    def run_turn(
        self,
        system: str,
        transcript: list[ConversationTurn],
        tools: list[dict[str, Any]],
    ) -> LLMTurnResult:
        """Send the conversation so far plus the available tool
        schemas, and return the model's next turn.

        `tools` is a list of `{"name", "description", "input_schema"}`
        dicts (JSON Schema for each tool's arguments) as produced by
        `ai/llm/tools.py::get_tool_schemas()`.

        Must raise `ProviderCallError` (not a vendor-specific
        exception) if the call fails."""
