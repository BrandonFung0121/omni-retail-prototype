"""The one place in this codebase that writes an Order/OrderItem/Payment/
Inventory change.

complete_sale() is a pure function: session + Cart in, SaleReceipt out.
It knows nothing about HTTP, POS UI, or storefronts, so any front end
can reuse it unchanged.

Every validation check (empty cart, bad quantity, unknown product,
insufficient stock, bad discount, unknown customer, bad payment method)
runs before the first `session.add()`, so a rejected sale is guaranteed
to leave the database untouched -- no partial commits, no rollback
choreography needed for the validation path.

Once validation passes, the cart is charged via a PaymentProcessor
(defaulting to the simulated one -- see payments/processor.py). A
successful charge writes the sale exactly as Phase 5 did: Order
COMPLETED, inventory decremented, Payment SUCCESS. A declined charge
still writes an audit record -- Order CANCELLED with its line items,
Payment FAILED -- but never touches inventory. Either way the write
section is wrapped defensively in case of an unexpected DB-level
failure.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from omni_retail.models import (
    Customer,
    Inventory,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Product,
    SalesChannel,
)
from omni_retail.payments import PaymentProcessor, PaymentRequest, default_processor
from omni_retail.transactions.models import (
    Cart,
    CustomerNotFoundError,
    DiscountType,
    EmptyCartError,
    InsufficientStockError,
    InvalidChannelError,
    InvalidDiscountError,
    InvalidPaymentMethodError,
    InvalidQuantityError,
    ProductNotFoundError,
    ReceiptLine,
    SaleReceipt,
)

ResolvedLine = tuple[Product, Inventory, int]


def complete_sale(session: Session, cart: Cart, processor: PaymentProcessor = default_processor) -> SaleReceipt:
    if not cart.items:
        raise EmptyCartError("Cart is empty -- add at least one item before checking out.")

    try:
        payment_method = PaymentMethod(cart.payment_method)
    except ValueError:
        raise InvalidPaymentMethodError(f"Unknown payment method: {cart.payment_method!r}") from None

    try:
        channel = SalesChannel(cart.channel)
    except ValueError:
        raise InvalidChannelError(f"Unknown sales channel: {cart.channel!r}") from None

    quantity_by_product: dict[int, int] = {}
    for item in cart.items:
        if not isinstance(item.quantity, int) or item.quantity <= 0:
            raise InvalidQuantityError(f"Quantity must be a positive whole number (got {item.quantity!r}).")
        quantity_by_product[item.product_id] = quantity_by_product.get(item.product_id, 0) + item.quantity

    resolved_lines: list[ResolvedLine] = []
    for product_id, quantity in quantity_by_product.items():
        product = session.get(Product, product_id)
        if product is None:
            raise ProductNotFoundError(f"No product with id {product_id}.")
        inventory = product.inventory
        available = inventory.current_stock if inventory else 0
        if inventory is None or available < quantity:
            raise InsufficientStockError(product.name, quantity, available)
        resolved_lines.append((product, inventory, quantity))

    customer = None
    if cart.customer_id is not None:
        customer = session.get(Customer, cart.customer_id)
        if customer is None:
            raise CustomerNotFoundError(f"No customer with id {cart.customer_id}.")

    subtotal = sum(float(product.selling_price) * quantity for product, _inv, quantity in resolved_lines)
    discount_total = _resolve_discount(cart, subtotal)
    # Priced (and summed) before charging, not derived as subtotal - discount
    # -- per-line rounding means those can differ from the sum of lines by a
    # cent, and the amount charged must exactly match what the order records.
    receipt_lines = _price_lines(resolved_lines, subtotal, discount_total)
    total = round(sum(line.line_total for line in receipt_lines), 2)

    payment_result = processor.charge(
        PaymentRequest(amount=total, method=payment_method, card_number=cart.card_number)
    )
    succeeded = payment_result.status == PaymentStatus.SUCCESS

    try:
        now = datetime.now()
        order = Order(
            customer_id=customer.id if customer else None,
            order_datetime=now,
            status=OrderStatus.COMPLETED if succeeded else OrderStatus.CANCELLED,
            channel=channel,
            discount_total=round(discount_total, 2),
        )
        session.add(order)
        session.flush()

        for (product, inventory, quantity), line in zip(resolved_lines, receipt_lines):
            session.add(
                OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=quantity,
                    unit_price=line.unit_price,
                )
            )
            if succeeded:
                inventory.current_stock -= quantity
                inventory.last_updated = now

        payment = Payment(
            order_id=order.id,
            method=payment_method,
            amount=total,
            status=payment_result.status,
            payment_date=payment_result.processed_at,
            reference=payment_result.reference,
        )
        session.add(payment)
        session.commit()
    except Exception:
        session.rollback()
        raise

    return SaleReceipt(
        order_id=order.id,
        order_datetime=now,
        customer_id=customer.id if customer else None,
        customer_name=customer.name if customer else "Guest",
        channel=channel.value,
        status=order.status.value,
        lines=receipt_lines,
        subtotal=round(subtotal, 2),
        discount_total=round(discount_total, 2),
        total=total,
        payment_method=payment_method.value,
        payment_status=payment_result.status.value,
        payment_reference=payment_result.reference,
        failure_reason=payment_result.failure_reason,
    )


def _price_lines(resolved_lines: list[ResolvedLine], subtotal: float, discount_total: float) -> list[ReceiptLine]:
    """Pro-rates the cart discount across line items and returns the
    priced lines -- pure, no DB writes, shared by both the success and
    decline paths so a declined order's audit record shows the same
    prices a completed one would have."""
    lines: list[ReceiptLine] = []
    remaining_discount = round(discount_total, 2)
    for index, (product, _inventory, quantity) in enumerate(resolved_lines):
        line_subtotal = float(product.selling_price) * quantity
        is_last_line = index == len(resolved_lines) - 1
        if discount_total <= 0 or subtotal <= 0:
            line_discount = 0.0
        elif is_last_line:
            line_discount = remaining_discount
        else:
            line_discount = round(discount_total * (line_subtotal / subtotal), 2)
            remaining_discount = round(remaining_discount - line_discount, 2)

        charged_unit_price = round((line_subtotal - line_discount) / quantity, 2)
        lines.append(
            ReceiptLine(
                product_id=product.id,
                product_name=product.name,
                quantity=quantity,
                unit_price=charged_unit_price,
                line_total=round(charged_unit_price * quantity, 2),
            )
        )
    return lines


def _resolve_discount(cart: Cart, subtotal: float) -> float:
    if cart.discount_type is None:
        return 0.0

    try:
        discount_type = DiscountType(cart.discount_type)
    except ValueError:
        raise InvalidDiscountError(f"Unknown discount type: {cart.discount_type!r}") from None

    if discount_type == DiscountType.PERCENT:
        if cart.discount_value < 0 or cart.discount_value > 100:
            raise InvalidDiscountError(f"Percent discount must be between 0 and 100 (got {cart.discount_value}).")
        return round(subtotal * cart.discount_value / 100, 2)

    if cart.discount_value < 0:
        raise InvalidDiscountError(f"Discount amount cannot be negative (got {cart.discount_value}).")
    if cart.discount_value > subtotal:
        raise InvalidDiscountError(f"Discount amount ({cart.discount_value:.2f}) cannot exceed the subtotal ({subtotal:.2f}).")
    return round(cart.discount_value, 2)
