from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from omni_retail import services
from omni_retail.api.dependencies import get_session
from omni_retail.api.schemas import EstimatedProfitResponse

router = APIRouter(prefix="/api/profit", tags=["profit"])


@router.get("/estimated", response_model=EstimatedProfitResponse)
def get_estimated_profit(
    start: date | None = None, end: date | None = None, session: Session = Depends(get_session)
) -> EstimatedProfitResponse:
    return EstimatedProfitResponse(
        estimated_profit=services.estimated_profit(session, start, end),
        revenue=services.revenue(session, start, end),
        cost_of_goods_sold=services.cost_of_goods_sold(session, start, end),
        expenses=services.total_expenses(session, start, end),
    )
