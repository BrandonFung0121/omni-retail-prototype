from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from omni_retail import services
from omni_retail.api.dependencies import get_session
from omni_retail.api.schemas import AverageOrderValueResponse, OrderCountResponse

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("/count", response_model=OrderCountResponse)
def get_order_count(
    start: date | None = None, end: date | None = None, session: Session = Depends(get_session)
) -> OrderCountResponse:
    return OrderCountResponse(orders=services.order_count(session, start, end))


@router.get("/average-value", response_model=AverageOrderValueResponse)
def get_average_order_value(
    start: date | None = None, end: date | None = None, session: Session = Depends(get_session)
) -> AverageOrderValueResponse:
    return AverageOrderValueResponse(average_order_value=services.average_order_value(session, start, end))
