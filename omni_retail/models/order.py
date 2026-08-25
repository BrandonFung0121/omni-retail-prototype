import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omni_retail.database import Base


class OrderStatus(str, enum.Enum):
    COMPLETED = "completed"
    PENDING = "pending"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class SalesChannel(str, enum.Enum):
    IN_STORE = "in_store"
    ONLINE = "online"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    order_datetime: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus))
    channel: Mapped[SalesChannel] = mapped_column(Enum(SalesChannel))

    customer: Mapped["Customer"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    payment: Mapped["Payment"] = relationship(
        back_populates="order", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def order_value(self) -> float:
        return sum(item.line_total for item in self.items)

    def __repr__(self) -> str:
        return f"Order(id={self.id!r}, status={self.status!r})"


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int]
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2))

    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship(back_populates="order_items")

    @property
    def line_total(self) -> float:
        return float(self.quantity) * float(self.unit_price)
