"""Concrete `LLMProvider` backed by the official `anthropic` Python SDK.

This is the only file in the codebase that imports `anthropic` or knows
about its message/content-block shapes -- `orchestrator.py` and
`agent.py` only ever see the generic types from `provider.py`. Adding a
second provider (a different vendor, a local model) means writing
another class like this one and wiring it into
`ai/llm/__init__.py::get_provider()`; nothing else changes.
"""

from __future__ import annotations

from typing import Any

from omni_retail.ai.llm.provider import (
    ConversationTurn,
    LLMProvider,
    LLMTurnResult,
    ProviderCallError,
    ProviderUnavailableError,
    ToolCall,
)

try:
    import anthropic
except ImportError:  # pragma: no cover - exercised via get_provider()'s own fallback
    anthropic = None


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str, max_tokens: int = 1024, timeout: float = 20.0):
        if anthropic is None:
            raise ProviderUnavailableError(
                "The 'anthropic' package is not installed. Add it to requirements.txt and reinstall."
            )
        if not api_key:
            raise ProviderUnavailableError("No Anthropic API key was provided.")

        self._model = model
        self._max_tokens = max_tokens
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout)

    def run_turn(
        self,
        system: str,
        transcript: list[ConversationTurn],
        tools: list[dict[str, Any]],
    ) -> LLMTurnResult:
        messages = [_to_anthropic_message(turn) for turn in transcript]
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=messages,
                tools=tools,
            )
        except anthropic.AnthropicError as exc:
            raise ProviderCallError(f"Anthropic API call failed: {exc}") from exc

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=dict(block.input or {})))

        stop_reason = "tool_use" if tool_calls else "end_turn"
        return LLMTurnResult(stop_reason=stop_reason, text="\n".join(text_parts), tool_calls=tool_calls)


def _to_anthropic_message(turn: ConversationTurn) -> dict[str, Any]:
    if turn.role == "user":
        if turn.image is None:
            return {"role": "user", "content": turn.text}
        # Image first, then text -- Anthropic's own recommendation for
        # single-image-plus-question messages, so the model "sees" the
        # photo before it reads what's being asked about it.
        content: list[dict[str, Any]] = [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": turn.image.media_type, "data": turn.image.data_base64},
            }
        ]
        if turn.text:
            content.append({"type": "text", "text": turn.text})
        return {"role": "user", "content": content}

    if turn.role == "assistant":
        content: list[dict[str, Any]] = []
        if turn.text:
            content.append({"type": "text", "text": turn.text})
        for call in turn.tool_calls:
            content.append({"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments})
        return {"role": "assistant", "content": content}

    # role == "tool_results"
    content = [
        {"type": "tool_result", "tool_use_id": result.tool_call_id, "content": result.content, "is_error": result.is_error}
        for result in turn.tool_results
    ]
    return {"role": "user", "content": content}
