from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from omni_retail import services
from omni_retail.api.dependencies import get_session
from omni_retail.api.schemas import ExpensesResponse

router = APIRouter(prefix="/api/expenses", tags=["expenses"])


@router.get("", response_model=ExpensesResponse)
def get_expenses(
    start: date | None = None, end: date | None = None, session: Session = Depends(get_session)
) -> ExpensesResponse:
    by_category = services.expenses_by_category(session, start, end)
    return ExpensesResponse(
        total=services.total_expenses(session, start, end),
        by_category={category.value: amount for category, amount in by_category.items()},
    )
