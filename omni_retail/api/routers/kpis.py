from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from omni_retail import services
from omni_retail.api.dependencies import get_session
from omni_retail.api.schemas import KPISummaryResponse

router = APIRouter(prefix="/api/kpis", tags=["kpis"])


@router.get("/summary", response_model=KPISummaryResponse)
def get_kpi_summary(
    start: date | None = None, end: date | None = None, session: Session = Depends(get_session)
) -> KPISummaryResponse:
    """Bundles the headline KPI-card numbers into one call for the dashboard."""
    traffic = services.website_traffic_summary(session, start, end)
    return KPISummaryResponse(
        revenue=services.revenue(session, start, end),
        orders=services.order_count(session, start, end),
        average_order_value=services.average_order_value(session, start, end),
        estimated_profit=services.estimated_profit(session, start, end),
        website_visitors=traffic.visitors,
        conversion_rate=traffic.conversion_rate,
    )
