"""Data shapes for the payment abstraction.

A PaymentRequest goes in, a PaymentResult comes out. Nothing here
knows about Orders, carts, or checkout -- transactions/service.py is
the only caller, and it treats any PaymentProcessor identically
regardless of implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from omni_retail.models import PaymentMethod, PaymentStatus


@dataclass
class PaymentRequest:
    amount: float
    method: PaymentMethod
    card_number: Optional[str] = None


@dataclass
class PaymentResult:
    status: PaymentStatus
    reference: str
    processed_at: datetime
    failure_reason: Optional[str] = None
