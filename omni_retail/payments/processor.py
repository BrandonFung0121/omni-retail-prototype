"""The payment abstraction.

transactions/service.py depends only on the PaymentProcessor interface,
never on SimulatedPaymentProcessor directly (it takes a `processor`
argument that defaults to the module-level singleton below). Swapping
in a real provider later means writing a StripePaymentProcessor that
implements `charge()` and passing an instance of it in -- no change to
checkout, the transaction layer, or any caller.
"""

from __future__ import annotations

import secrets
from abc import ABC, abstractmethod
from datetime import datetime

from omni_retail.models import PaymentMethod, PaymentStatus
from omni_retail.payments.models import PaymentRequest, PaymentResult

# Stripe's own well-known test-card convention, reused here for realism:
# https://stripe.com/docs/testing -- 4242...4242 succeeds, 4000...0002 is
# a generic decline. Makes "a real Stripe processor could drop in later"
# a credible claim rather than a throwaway comment.
_DECLINE_CARD_SUFFIXES = ("0002",)


class PaymentProcessor(ABC):
    @abstractmethod
    def charge(self, request: PaymentRequest) -> PaymentResult: ...


class SimulatedPaymentProcessor(PaymentProcessor):
    """No real payment provider is contacted; no real card data is
    collected, transmitted, or stored anywhere -- only the method,
    amount, a generated reference, and the outcome are ever recorded
    (on the Payment model, via transactions/service.py).

    Card-present methods (credit/debit) decline when the supplied
    number ends in a known Stripe test-decline suffix; anything else,
    including no card number at all, succeeds. Digital wallet and cash
    always succeed -- there's no "number" to simulate a decline against.
    """

    def charge(self, request: PaymentRequest) -> PaymentResult:
        now = datetime.now()
        reference = f"SIM-{secrets.token_hex(8)}"

        if request.method in (PaymentMethod.CREDIT_CARD, PaymentMethod.DEBIT_CARD) and request.card_number:
            digits = "".join(ch for ch in request.card_number if ch.isdigit())
            if digits.endswith(_DECLINE_CARD_SUFFIXES):
                return PaymentResult(
                    status=PaymentStatus.FAILED,
                    reference=reference,
                    processed_at=now,
                    failure_reason="Card declined by issuer (simulated).",
                )

        return PaymentResult(status=PaymentStatus.SUCCESS, reference=reference, processed_at=now)


default_processor = SimulatedPaymentProcessor()
