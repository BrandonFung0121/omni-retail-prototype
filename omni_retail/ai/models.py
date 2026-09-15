"""Response shape for the AI Business Analyst Agent.

Mirrors the automation layer's Alert dataclass on purpose (plain,
JSON-friendly, computed fresh per request, no persistence) so the two
features feel like one system rather than two bolted-together ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentResponse:
    question: str
    intent: str
    answer: str
    confidence: str  # "high" | "low"
    supporting_metrics: dict[str, Any] = field(default_factory=dict)
    recommended_actions: list[str] = field(default_factory=list)
    related_alert_ids: list[str] = field(default_factory=list)
    generated_by: str = "template"  # "template" | "llm" (see ai/llm/orchestrator.py)
    # One entry per tool call the LLM made while answering (empty for the
    # deterministic "template" path) -- populated by ai/llm/orchestrator.py,
    # never by the deterministic pipeline.
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
