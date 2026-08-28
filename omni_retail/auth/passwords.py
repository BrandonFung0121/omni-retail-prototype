"""Password hashing for storefront customer accounts.

Deliberately dependency-free (stdlib PBKDF2-HMAC-SHA256) rather than
bcrypt/argon2 -- appropriate for a prototype demonstrating the login
flow, not a claim of production-grade security hardening. Passwords
are never logged or stored in plaintext.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ITERATIONS = 200_000


def hash_password(password: str) -> tuple[str, str]:
    """Returns (salt_hex, hash_hex)."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS)
    return salt, digest.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), _ITERATIONS)
    return hmac.compare_digest(digest.hex(), hash_hex)
