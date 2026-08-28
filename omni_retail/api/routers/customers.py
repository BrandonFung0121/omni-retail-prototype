from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from omni_retail import services
from omni_retail.api.dependencies import get_session
from omni_retail.api.schemas import CustomerSummaryOut, CustomerValueOut

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("/search", response_model=list[CustomerSummaryOut])
def search_customers(
    q: str = "",
    limit: int = Query(10, ge=1, le=50),
    session: Session = Depends(get_session),
) -> list[CustomerSummaryOut]:
    """Name/email typeahead, for the POS customer-selection step."""
    return services.search_customers(session, q, limit=limit)


@router.get("/high-value", response_model=list[CustomerValueOut])
def get_high_value_customers(
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(10, ge=1, le=100),
    session: Session = Depends(get_session),
) -> list[CustomerValueOut]:
    return services.high_value_customers(session, start, end, limit=limit)
