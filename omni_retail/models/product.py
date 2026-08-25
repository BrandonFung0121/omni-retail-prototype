from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omni_retail.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100))
    selling_price: Mapped[float] = mapped_column(Numeric(10, 2))
    cost: Mapped[float] = mapped_column(Numeric(10, 2))

    order_items: Mapped[list["OrderItem"]] = relationship(back_populates="product")
    inventory: Mapped["Inventory"] = relationship(
        back_populates="product", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"Product(id={self.id!r}, name={self.name!r})"
