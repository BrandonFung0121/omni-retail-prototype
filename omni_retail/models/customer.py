from datetime import date
from typing import Optional

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omni_retail.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    join_date: Mapped[date] = mapped_column(Date)
    # Storefront login. Nullable: most seeded customers are admin-side-only
    # and never registered on the storefront. Prototype-grade auth --
    # stdlib PBKDF2, not a claim of production security hardening.
    password_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    password_salt: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    orders: Mapped[list["Order"]] = relationship(back_populates="customer")

    def __repr__(self) -> str:
        return f"Customer(id={self.id!r}, name={self.name!r})"
