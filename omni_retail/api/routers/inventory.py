from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from omni_retail import services
from omni_retail.api.dependencies import get_session
from omni_retail.api.schemas import InventoryItemOut, InventoryStatusResponse
from omni_retail.models import InventoryStatus

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


@router.get("/status", response_model=InventoryStatusResponse)
def get_inventory_status(session: Session = Depends(get_session)) -> InventoryStatusResponse:
    counts = services.inventory_status_counts(session)
    low_stock_items = [
        InventoryItemOut(
            product_id=inv.product_id,
            product_name=inv.product.name,
            category=inv.product.category,
            current_stock=inv.current_stock,
            reorder_threshold=inv.reorder_threshold,
            status=inv.status.value,
        )
        for inv in services.low_stock_products(session)
    ]
    return InventoryStatusResponse(
        healthy=counts[InventoryStatus.HEALTHY],
        low_stock=counts[InventoryStatus.LOW_STOCK],
        out_of_stock=counts[InventoryStatus.OUT_OF_STOCK],
        low_stock_items=low_stock_items,
    )
