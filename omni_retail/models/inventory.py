import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omni_retail.database import Base


class InventoryStatus(str, enum.Enum):
    HEALTHY = "healthy"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"


class Inventory(Base):
    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), unique=True)
    current_stock: Mapped[int]
    reorder_threshold: Mapped[int]
    last_updated: Mapped[datetime] = mapped_column(DateTime)

    product: Mapped["Product"] = relationship(back_populates="inventory")

    @property
    def status(self) -> InventoryStatus:
        if self.current_stock <= 0:
            return InventoryStatus.OUT_OF_STOCK
        if self.current_stock <= self.reorder_threshold:
            return InventoryStatus.LOW_STOCK
        return InventoryStatus.HEALTHY
