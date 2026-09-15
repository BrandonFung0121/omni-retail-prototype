from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from omni_retail import services
from omni_retail.api.dependencies import get_session
from omni_retail.api.schemas import ProductCatalogEntryOut, ProductPerformanceOut

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("", response_model=list[ProductCatalogEntryOut])
def get_products(session: Session = Depends(get_session)) -> list[ProductCatalogEntryOut]:
    """Full catalog with live stock, for the POS product picker."""
    return services.list_products(session)


@router.get("/top", response_model=list[ProductPerformanceOut])
def get_top_products(
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(10, ge=1, le=100),
    by: Literal["revenue", "units"] = "revenue",
    session: Session = Depends(get_session),
) -> list[ProductPerformanceOut]:
    return services.top_products(session, start, end, limit=limit, by=by)
