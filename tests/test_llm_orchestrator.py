"""Tests for the bounded LLM orchestration loop (ai/llm/orchestrator.py)
and its wiring into ai/agent.py's deterministic fallback.

Every test uses a scripted `FakeLLMProvider`/`RepeatingToolCallProvider`
from tests/llm_fakes.py -- no network call, no API key, no `anthropic`
package touched.
"""

from __future__ import annotations

import pytest

from omni_retail.ai import agent
from omni_retail.ai.llm.orchestrator import OrchestrationLimitExceeded, answer_with_llm
from omni_retail.ai.llm.provider import LLMTurnResult, ProviderCallError, ToolCall
from tests.llm_fakes import FakeLLMProvider, RepeatingToolCallProvider


def test_multi_step_tool_orchestration_produces_grounded_answer(session):
    provider = FakeLLMProvider(
        [
            LLMTurnResult(
                stop_reason="tool_use",
                tool_calls=[ToolCall(id="1", name="get_restock_priority", arguments={})],
            ),
            LLMTurnResult(
                stop_reason="tool_use",
                tool_calls=[ToolCall(id="2", name="get_business_issues_summary", arguments={})],
            ),
            LLMTurnResult(stop_reason="end_turn", text="Here's what's going on, grounded in the data above."),
        ]
    )

    response = answer_with_llm(provider, session, "What should I focus on today?")

    assert response.generated_by == "llm"
    assert response.answer == "Here's what's going on, grounded in the data above."
    assert response.confidence == "high"
    assert [entry["tool"] for entry in response.tool_trace] == ["get_restock_priority", "get_business_issues_summary"]
    assert all(entry["ok"] for entry in response.tool_trace)


def test_unknown_tool_call_is_recovered_not_fatal(session):
    provider = FakeLLMProvider(
        [
            LLMTurnResult(stop_reason="tool_use", tool_calls=[ToolCall(id="1", name="delete_everything", arguments={})]),
            LLMTurnResult(stop_reason="end_turn", text="I couldn't use that tool, but here's what I do know."),
        ]
    )

    response = answer_with_llm(provider, session, "do something weird")

    assert response.generated_by == "llm"
    assert response.tool_trace[0]["tool"] == "delete_everything"
    assert response.tool_trace[0]["ok"] is False


def test_malformed_tool_call_is_recovered_not_fatal(session):
    provider = FakeLLMProvider(
        [
            LLMTurnResult(stop_reason="tool_use", tool_calls=[ToolCall(id="1", name="get_order", arguments={})]),
            LLMTurnResult(stop_reason="end_turn", text="I need an order id to look that up."),
        ]
    )

    response = answer_with_llm(provider, session, "look up my order")

    assert response.generated_by == "llm"
    assert response.tool_trace[0]["ok"] is False


def test_loop_and_tool_call_limits_raise_orchestration_limit_exceeded(session, monkeypatch):
    monkeypatch.setenv("OMNI_LLM_MAX_ITERATIONS", "2")
    monkeypatch.setenv("OMNI_LLM_MAX_TOOL_CALLS", "3")
    provider = RepeatingToolCallProvider("get_business_issues_summary")

    with pytest.raises(OrchestrationLimitExceeded):
        answer_with_llm(provider, session, "keep going forever")


def test_provider_call_error_propagates_out_of_orchestrator(session):
    provider = FakeLLMProvider([ProviderCallError("simulated timeout")])

    with pytest.raises(ProviderCallError):
        answer_with_llm(provider, session, "anything")


def test_a_real_bug_in_a_tool_handler_is_not_swallowed(session, monkeypatch):
    """Distinguishes 'the model asked for something invalid' (recoverable,
    fed back into the loop) from 'our own code is broken' (must stay
    visible). A genuine exception from a tool handler is neither
    UnknownToolError nor ToolArgumentError, so it must propagate all the
    way out, not be reinterpreted as a provider failure."""
    from omni_retail.ai.llm import tools as tools_module

    def broken_handler(session, arguments, *, question, today):
        raise RuntimeError("a real programming bug, not a bad tool call")

    monkeypatch.setattr(tools_module.TOOL_REGISTRY["get_restock_priority"], "handler", broken_handler)

    provider = FakeLLMProvider(
        [LLMTurnResult(stop_reason="tool_use", tool_calls=[ToolCall(id="1", name="get_restock_priority", arguments={})])]
    )

    with pytest.raises(RuntimeError, match="a real programming bug"):
        answer_with_llm(provider, session, "trigger the bug")


# --- agent.answer_question() dispatch/fallback wiring ---------------------


def test_agent_dispatches_to_llm_when_enabled_and_provider_available(session, monkeypatch):
    provider = FakeLLMProvider([LLMTurnResult(stop_reason="end_turn", text="Grounded LLM answer.")])
    monkeypatch.setattr(agent.llm_config, "is_llm_enabled", lambda: True)
    monkeypatch.setattr(agent, "get_provider", lambda: provider)

    response = agent.answer_question(session, "Why did revenue change?")

    assert response.generated_by == "llm"
    assert response.answer == "Grounded LLM answer."


def test_agent_falls_back_to_deterministic_when_llm_disabled(session, monkeypatch):
    monkeypatch.setattr(agent.llm_config, "is_llm_enabled", lambda: False)

    response = agent.answer_question(session, "Why did revenue change?")

    assert response.generated_by == "template"


def test_agent_falls_back_to_deterministic_when_provider_unavailable(session, monkeypatch):
    monkeypatch.setattr(agent.llm_config, "is_llm_enabled", lambda: True)
    monkeypatch.setattr(agent, "get_provider", lambda: None)

    response = agent.answer_question(session, "Why did revenue change?")

    assert response.generated_by == "template"
    assert response.answer


def test_agent_falls_back_to_deterministic_on_provider_call_error(session, monkeypatch):
    provider = FakeLLMProvider([ProviderCallError("simulated network failure")])
    monkeypatch.setattr(agent.llm_config, "is_llm_enabled", lambda: True)
    monkeypatch.setattr(agent, "get_provider", lambda: provider)

    response = agent.answer_question(session, "Why did revenue change?")

    assert response.generated_by == "template"
    assert response.answer


def test_agent_falls_back_to_deterministic_on_orchestration_limit_exceeded(session, monkeypatch):
    monkeypatch.setenv("OMNI_LLM_MAX_ITERATIONS", "1")
    monkeypatch.setenv("OMNI_LLM_MAX_TOOL_CALLS", "1")
    monkeypatch.setattr(agent.llm_config, "is_llm_enabled", lambda: True)
    monkeypatch.setattr(agent, "get_provider", lambda: RepeatingToolCallProvider("get_business_issues_summary"))

    response = agent.answer_question(session, "keep asking forever")

    assert response.generated_by == "template"
    assert response.answer


def test_agent_does_not_swallow_an_unexpected_bug_in_the_llm_path(session, monkeypatch):
    """Mirrors test_a_real_bug_in_a_tool_handler_is_not_swallowed but
    through the public agent.answer_question() entry point: a genuine
    bug must surface as a real exception, not a silent deterministic
    fallback that looks like normal behavior."""

    class ExplodingProvider:
        def run_turn(self, system, transcript, tools):
            raise KeyError("not a recognized LLMProviderError subclass")

    monkeypatch.setattr(agent.llm_config, "is_llm_enabled", lambda: True)
    monkeypatch.setattr(agent, "get_provider", lambda: ExplodingProvider())

    with pytest.raises(KeyError):
        agent.answer_question(session, "Why did revenue change?")
