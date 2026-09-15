from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from omni_retail import services
from omni_retail.api.dependencies import get_session
from omni_retail.api.schemas import AverageOrderValueResponse, OrderCountResponse, OrderDetailOut, OrderSummaryOut
from omni_retail.models import OrderStatus

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("", response_model=list[OrderSummaryOut])
def get_orders(
    start: date | None = None,
    end: date | None = None,
    status: OrderStatus | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> list[OrderSummaryOut]:
    """Recent transactions, newest first, for the Transactions view."""
    return services.list_orders(session, start, end, status=status, limit=limit, offset=offset)


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


@router.get("/{order_id}", response_model=OrderDetailOut)
def get_order(order_id: int, session: Session = Depends(get_session)) -> OrderDetailOut:
    """Full line-item detail for one order, for a receipt view."""
    order = services.get_order(session, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"No order with id {order_id}.")
    return order
