"""Customer-facing storefront endpoints.

Checkout below is a thin wrapper around transactions.complete_sale()
-- exactly like omni_retail/api/routers/pos.py's checkout. It's the
same write path, same validation, same Payment/Inventory/Order model;
only the default channel (online vs. in_store) and the optional
card-number/idempotency-key inputs differ.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from omni_retail import services
from omni_retail.api.dependencies import get_current_customer, get_current_customer_optional, get_session
from omni_retail.api.schemas import (
    AuthResponse,
    CustomerMeOut,
    LoginRequest,
    OrderDetailOut,
    OrderSummaryOut,
    RegisterRequest,
    SaleReceiptOut,
    StorefrontCheckoutRequest,
)
from omni_retail.auth import create_session, hash_password, verify_password
from omni_retail.models import Customer
from omni_retail.transactions import Cart, CartItem, TransactionError, complete_sale

router = APIRouter(prefix="/api/storefront", tags=["storefront"])

# Idempotency: the storefront generates one key per checkout attempt and
# resends it on retry, so a double-click/double-submit replays the first
# result instead of charging twice. In-memory and unbounded is fine for a
# single-process prototype; a real deployment would use a TTL cache or a
# DB-backed table.
_IDEMPOTENCY_CACHE: dict[str, SaleReceiptOut] = {}


def _to_me(customer: Customer) -> CustomerMeOut:
    return CustomerMeOut(customer_id=customer.id, name=customer.name, email=customer.email)


@router.post("/auth/register", response_model=AuthResponse)
def register(request: RegisterRequest, session: Session = Depends(get_session)) -> AuthResponse:
    existing = session.execute(select(Customer).where(Customer.email == request.email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with that email already exists.")
    if not request.name.strip():
        raise HTTPException(status_code=422, detail="Name is required.")
    if len(request.password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters.")

    salt, password_hash = hash_password(request.password)
    customer = Customer(
        name=request.name.strip(),
        email=request.email.strip().lower(),
        join_date=date.today(),
        password_hash=password_hash,
        password_salt=salt,
    )
    session.add(customer)
    session.commit()

    token = create_session(customer.id)
    return AuthResponse(token=token, customer=_to_me(customer))


@router.post("/auth/login", response_model=AuthResponse)
def login(request: LoginRequest, session: Session = Depends(get_session)) -> AuthResponse:
    customer = session.execute(select(Customer).where(Customer.email == request.email.strip().lower())).scalar_one_or_none()
    if (
        customer is None
        or not customer.password_hash
        or not customer.password_salt
        or not verify_password(request.password, customer.password_salt, customer.password_hash)
    ):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    token = create_session(customer.id)
    return AuthResponse(token=token, customer=_to_me(customer))


@router.get("/me", response_model=CustomerMeOut)
def me(customer: Customer = Depends(get_current_customer)) -> CustomerMeOut:
    return _to_me(customer)


@router.post("/checkout", response_model=SaleReceiptOut)
def checkout(
    request: StorefrontCheckoutRequest,
    customer: Customer | None = Depends(get_current_customer_optional),
    session: Session = Depends(get_session),
) -> SaleReceiptOut:
    """Complete an online purchase -- guest or logged-in. Uses the exact
    same complete_sale() as the POS checkout; only defaults differ."""
    if request.idempotency_key and request.idempotency_key in _IDEMPOTENCY_CACHE:
        return _IDEMPOTENCY_CACHE[request.idempotency_key]

    cart = Cart(
        items=[CartItem(product_id=i.product_id, quantity=i.quantity) for i in request.items],
        payment_method=request.payment_method,
        customer_id=customer.id if customer else None,
        channel=request.channel,
        discount_type=request.discount_type,
        discount_value=request.discount_value,
        card_number=request.card_number,
    )
    try:
        receipt = complete_sale(session, cart)
    except TransactionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = SaleReceiptOut.model_validate(receipt)
    if request.idempotency_key:
        _IDEMPOTENCY_CACHE[request.idempotency_key] = result
    return result


@router.get("/orders", response_model=list[OrderSummaryOut])
def my_orders(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    customer: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
) -> list[OrderSummaryOut]:
    """The logged-in customer's own order history -- reuses the exact
    same list_orders() the admin Transactions view uses, scoped by
    customer_id."""
    return services.list_orders(session, customer_id=customer.id, limit=limit, offset=offset)


@router.get("/orders/{order_id}", response_model=OrderDetailOut)
def my_order_detail(
    order_id: int,
    customer: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
) -> OrderDetailOut:
    """A single past order's full receipt -- scoped to the logged-in
    customer. Deliberately separate from the admin's unauthenticated
    GET /api/orders/{id}: that endpoint is fine for an internal staff
    tool, but a customer-facing one must not let any visitor enumerate
    other customers' order details by guessing IDs."""
    order = services.get_order(session, order_id)
    if order is None or order.customer_id != customer.id:
        raise HTTPException(status_code=404, detail=f"No order with id {order_id}.")
    return order
