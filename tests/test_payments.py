from omni_retail.models import PaymentMethod, PaymentStatus
from omni_retail.payments import PaymentRequest, SimulatedPaymentProcessor


def test_digital_wallet_always_succeeds():
    processor = SimulatedPaymentProcessor()
    result = processor.charge(PaymentRequest(amount=50.0, method=PaymentMethod.DIGITAL_WALLET))
    assert result.status == PaymentStatus.SUCCESS
    assert result.reference.startswith("SIM-")
    assert result.failure_reason is None


def test_card_with_no_number_succeeds():
    """POS checkout never supplies a card number -- must keep working
    exactly as it did before payment simulation existed."""
    processor = SimulatedPaymentProcessor()
    result = processor.charge(PaymentRequest(amount=50.0, method=PaymentMethod.CREDIT_CARD, card_number=None))
    assert result.status == PaymentStatus.SUCCESS


def test_known_success_test_card_succeeds():
    processor = SimulatedPaymentProcessor()
    result = processor.charge(
        PaymentRequest(amount=50.0, method=PaymentMethod.CREDIT_CARD, card_number="4242 4242 4242 4242")
    )
    assert result.status == PaymentStatus.SUCCESS


def test_known_decline_test_card_fails():
    processor = SimulatedPaymentProcessor()
    result = processor.charge(
        PaymentRequest(amount=50.0, method=PaymentMethod.CREDIT_CARD, card_number="4000 0000 0000 0002")
    )
    assert result.status == PaymentStatus.FAILED
    assert result.failure_reason


def test_decline_only_applies_to_card_methods():
    """The decline-suffix convention is a card-number thing; it should
    never affect wallet/cash even if a caller passed the same digits
    in some other field."""
    processor = SimulatedPaymentProcessor()
    result = processor.charge(
        PaymentRequest(amount=50.0, method=PaymentMethod.DIGITAL_WALLET, card_number="4000000000000002")
    )
    assert result.status == PaymentStatus.SUCCESS


def test_each_charge_gets_a_unique_reference():
    processor = SimulatedPaymentProcessor()
    r1 = processor.charge(PaymentRequest(amount=10.0, method=PaymentMethod.CASH))
    r2 = processor.charge(PaymentRequest(amount=10.0, method=PaymentMethod.CASH))
    assert r1.reference != r2.reference
