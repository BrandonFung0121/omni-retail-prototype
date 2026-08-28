from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
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


@router.get("/{product_id}", response_model=ProductCatalogEntryOut)
def get_product(product_id: int, session: Session = Depends(get_session)) -> ProductCatalogEntryOut:
    """Single product with live stock, for the storefront Product Details page."""
    product = services.get_product(session, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"No product with id {product_id}.")
    return product
