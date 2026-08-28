from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from omni_retail.api.dependencies import get_session
from omni_retail.api.schemas import CheckoutRequest, SaleReceiptOut
from omni_retail.transactions import Cart, CartItem, TransactionError, complete_sale

router = APIRouter(prefix="/api/pos", tags=["pos"])


@router.post("/checkout", response_model=SaleReceiptOut)
def checkout(request: CheckoutRequest, session: Session = Depends(get_session)) -> SaleReceiptOut:
    """Complete a sale: creates the order/order items/payment, decrements
    inventory, and makes the transaction immediately visible to the
    dashboard, analytics, alerts, and AI assistant on their next read.

    Every validation failure maps to 422 with a message identifying
    exactly what was wrong -- the cart is guaranteed untouched in the
    database when this happens.
    """
    cart = Cart(
        items=[CartItem(product_id=i.product_id, quantity=i.quantity) for i in request.items],
        payment_method=request.payment_method,
        customer_id=request.customer_id,
        channel=request.channel,
        discount_type=request.discount_type,
        discount_value=request.discount_value,
    )
    try:
        return complete_sale(session, cart)
    except TransactionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
