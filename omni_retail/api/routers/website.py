from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from omni_retail import services
from omni_retail.api.dependencies import get_session
from omni_retail.api.schemas import ConversionRateResponse, DailyTrafficPointOut, TrafficResponse

router = APIRouter(prefix="/api/website", tags=["website"])


@router.get("/traffic", response_model=TrafficResponse)
def get_traffic(
    start: date | None = None, end: date | None = None, session: Session = Depends(get_session)
) -> TrafficResponse:
    summary = services.website_traffic_summary(session, start, end)
    return TrafficResponse(**summary.__dict__)


@router.get("/traffic/trend", response_model=list[DailyTrafficPointOut])
def get_traffic_trend(
    start: date | None = None, end: date | None = None, session: Session = Depends(get_session)
) -> list[DailyTrafficPointOut]:
    return services.website_traffic_trend(session, start, end)


@router.get("/conversion-rate", response_model=ConversionRateResponse)
def get_conversion_rate(
    start: date | None = None, end: date | None = None, session: Session = Depends(get_session)
) -> ConversionRateResponse:
    summary = services.website_traffic_summary(session, start, end)
    return ConversionRateResponse(
        conversion_rate=summary.conversion_rate, visitors=summary.visitors, conversions=summary.conversions
    )
