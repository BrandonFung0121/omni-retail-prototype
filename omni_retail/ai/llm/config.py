"""Environment-driven configuration for optional LLM-driven agent mode.

Follows the same `os.environ.get(...)` convention as
`api/dependencies.py`'s `OMNI_RETAIL_DB_PATH` rather than introducing a
settings framework. Every setting defaults to "off"/conservative, so an
unconfigured deployment behaves exactly like Phase 4 (deterministic
pipeline only, no outbound calls, no new dependency actually invoked).

`load_dotenv()` below reads a local `.env` file (see `.env.example`) into
`os.environ` if one exists -- it never overrides a variable the process
environment already set (e.g. a real deployment's own secret manager),
and does nothing at all if no `.env` is present. `.env` is gitignored;
only `.env.example`, with placeholder values, is committed.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

_TRUTHY = {"1", "true", "yes", "on"}


def is_llm_enabled() -> bool:
    """The one opt-in switch. Everything else in this package is inert
    unless this is set, regardless of whether an API key is present."""
    return os.environ.get("OMNI_LLM_ENABLED", "false").strip().lower() in _TRUTHY


def anthropic_api_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or None


def model_id() -> str:
    return os.environ.get("OMNI_LLM_MODEL", "claude-sonnet-5")


def max_output_tokens() -> int:
    return int(os.environ.get("OMNI_LLM_MAX_TOKENS", "1024"))


def timeout_seconds() -> float:
    return float(os.environ.get("OMNI_LLM_TIMEOUT_SECONDS", "20"))


def max_iterations() -> int:
    """Upper bound on LLM<->tool round trips for a single question."""
    return int(os.environ.get("OMNI_LLM_MAX_ITERATIONS", "4"))


def max_tool_calls() -> int:
    """Upper bound on total tool invocations for a single question,
    across all iterations -- a single model turn can request several
    tools at once, so this is tracked independently of max_iterations."""
    return int(os.environ.get("OMNI_LLM_MAX_TOOL_CALLS", "6"))
