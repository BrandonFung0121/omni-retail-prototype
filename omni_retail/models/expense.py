import enum
from datetime import date

from sqlalchemy import Date, Enum, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from omni_retail.database import Base


class ExpenseCategory(str, enum.Enum):
    RENT = "rent"
    MARKETING = "marketing"
    PAYROLL = "payroll"
    LOGISTICS = "logistics"
    SOFTWARE = "software"
    UTILITIES = "utilities"
    OTHER = "other"


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[ExpenseCategory] = mapped_column(Enum(ExpenseCategory))
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    expense_date: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(300))
