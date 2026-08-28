"""Data shapes for completing a sale.

A Cart goes in, a SaleReceipt comes out -- or a specific TransactionError
is raised before any database write happens. This is the only write path
in the whole codebase; every other package (services, automation, ai) is
read-only. Both the POS API and a future customer storefront API should
build a Cart and call transactions.complete_sale() directly rather than
re-implementing any part of this.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from omni_retail.models import PaymentMethod, SalesChannel


class DiscountType(str, enum.Enum):
    PERCENT = "percent"
    AMOUNT = "amount"


@dataclass
class CartItem:
    product_id: int
    quantity: int


@dataclass
class Cart:
    items: list[CartItem]
    payment_method: PaymentMethod
    customer_id: Optional[int] = None
    channel: SalesChannel = SalesChannel.IN_STORE
    discount_type: Optional[DiscountType] = None
    discount_value: float = 0.0


@dataclass
class ReceiptLine:
    product_id: int
    product_name: str
    quantity: int
    unit_price: float
    line_total: float


@dataclass
class SaleReceipt:
    order_id: int
    order_datetime: datetime
    customer_id: Optional[int]
    customer_name: str
    channel: str
    lines: list[ReceiptLine] = field(default_factory=list)
    subtotal: float = 0.0
    discount_total: float = 0.0
    total: float = 0.0
    payment_method: str = ""
    payment_status: str = ""


class TransactionError(Exception):
    """Base class for every sale-validation failure.

    Every complete_sale() validation check runs before any write, so
    raising one of these always means nothing was committed.
    """


class EmptyCartError(TransactionError):
    pass


class InvalidQuantityError(TransactionError):
    pass


class ProductNotFoundError(TransactionError):
    pass


class InsufficientStockError(TransactionError):
    def __init__(self, product_name: str, requested: int, available: int):
        self.product_name = product_name
        self.requested = requested
        self.available = available
        super().__init__(f"Only {available} unit(s) of {product_name} available, {requested} requested.")


class InvalidDiscountError(TransactionError):
    pass


class CustomerNotFoundError(TransactionError):
    pass


class InvalidPaymentMethodError(TransactionError):
    pass


class InvalidChannelError(TransactionError):
    pass
