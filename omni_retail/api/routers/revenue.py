from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from omni_retail import services
from omni_retail.api.dependencies import get_session
from omni_retail.api.schemas import DailyRevenuePointOut, RevenueResponse

router = APIRouter(prefix="/api/revenue", tags=["revenue"])


@router.get("", response_model=RevenueResponse)
def get_revenue(
    start: date | None = None, end: date | None = None, session: Session = Depends(get_session)
) -> RevenueResponse:
    return RevenueResponse(revenue=services.revenue(session, start, end))


@router.get("/trend", response_model=list[DailyRevenuePointOut])
def get_revenue_trend(
    start: date | None = None, end: date | None = None, session: Session = Depends(get_session)
) -> list[DailyRevenuePointOut]:
    return services.revenue_trend(session, start, end)
