"""Tests for the pure message-building logic in anthropic_provider.py
(ai/llm/anthropic_provider.py::_to_anthropic_message) -- no network
call, no API key, just the ConversationTurn -> Anthropic wire-format
translation, including the image content block added for visual
product search.
"""

from __future__ import annotations

from omni_retail.ai.llm.anthropic_provider import _to_anthropic_message
from omni_retail.ai.llm.provider import ConversationTurn, ImageContent


def test_text_only_user_turn_is_a_plain_string_message():
    turn = ConversationTurn(role="user", text="Do you have headphones?")
    message = _to_anthropic_message(turn)
    assert message == {"role": "user", "content": "Do you have headphones?"}


def test_user_turn_with_image_produces_image_then_text_blocks():
    turn = ConversationTurn(
        role="user",
        text="Do you have something like this?",
        image=ImageContent(media_type="image/jpeg", data_base64="ZmFrZQ=="),
    )
    message = _to_anthropic_message(turn)

    assert message["role"] == "user"
    assert isinstance(message["content"], list)
    assert message["content"][0] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": "ZmFrZQ=="},
    }
    assert message["content"][1] == {"type": "text", "text": "Do you have something like this?"}


def test_user_turn_with_image_and_no_text_omits_the_text_block():
    turn = ConversationTurn(role="user", text="", image=ImageContent(media_type="image/png", data_base64="ZmFrZQ=="))
    message = _to_anthropic_message(turn)
    assert len(message["content"]) == 1
    assert message["content"][0]["type"] == "image"
