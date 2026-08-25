from datetime import date

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omni_retail.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    join_date: Mapped[date] = mapped_column(Date)

    orders: Mapped[list["Order"]] = relationship(back_populates="customer")

    def __repr__(self) -> str:
        return f"Customer(id={self.id!r}, name={self.name!r})"
