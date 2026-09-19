"""Optional LLM-driven agent mode: opt-in, provider-abstracted, with a
permanent deterministic fallback (see `ai/agent.py`).

`get_provider()` is the single assembly point: it reads config, and
returns `None` (never raises) whenever the feature isn't usable --
disabled, no API key, or the `anthropic` package missing -- so
"unconfigured" and "misconfigured" both degrade to the deterministic
Phase 4 pipeline instead of breaking the app.
"""

from __future__ import annotations

import logging

from omni_retail.ai.llm import config
from omni_retail.ai.llm.provider import (
    ConversationTurn,
    ImageContent,
    LLMProvider,
    LLMProviderError,
    LLMTurnResult,
    ProviderCallError,
    ProviderUnavailableError,
    ToolCall,
    ToolResultMessage,
)

logger = logging.getLogger(__name__)


def get_provider() -> LLMProvider | None:
    if not config.is_llm_enabled():
        return None

    api_key = config.anthropic_api_key()
    if not api_key:
        logger.warning("OMNI_LLM_ENABLED is set but ANTHROPIC_API_KEY is missing -- using the deterministic pipeline.")
        return None

    try:
        from omni_retail.ai.llm.anthropic_provider import AnthropicProvider
    except ImportError:
        logger.warning("OMNI_LLM_ENABLED is set but the 'anthropic' package is not installed -- using the deterministic pipeline.")
        return None

    try:
        return AnthropicProvider(
            api_key=api_key,
            model=config.model_id(),
            max_tokens=config.max_output_tokens(),
            timeout=config.timeout_seconds(),
        )
    except ProviderUnavailableError:
        logger.warning("Anthropic provider could not be constructed -- using the deterministic pipeline.", exc_info=True)
        return None


__all__ = [
    "ConversationTurn",
    "ImageContent",
    "LLMProvider",
    "LLMProviderError",
    "LLMTurnResult",
    "ProviderCallError",
    "ProviderUnavailableError",
    "ToolCall",
    "ToolResultMessage",
    "config",
    "get_provider",
]
