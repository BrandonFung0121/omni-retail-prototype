"""Storefront login sessions.

An in-memory token->customer_id map, intentionally simple: no JWT
library, no persistent session store. Fine for a single-process
prototype demo; a real deployment would swap this for signed tokens
or a proper session store without touching any caller of this module.
"""

from __future__ import annotations

import secrets

_SESSIONS: dict[str, int] = {}


def create_session(customer_id: int) -> str:
    token = secrets.token_hex(24)
    _SESSIONS[token] = customer_id
    return token


def get_customer_id(token: str) -> int | None:
    return _SESSIONS.get(token)


def invalidate_session(token: str) -> None:
    _SESSIONS.pop(token, None)
