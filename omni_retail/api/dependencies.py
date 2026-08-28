import os
from collections.abc import Iterator
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from omni_retail.auth import get_customer_id
from omni_retail.database import make_engine, make_session_factory
from omni_retail.models import Customer

DB_PATH = os.environ.get("OMNI_RETAIL_DB_PATH", "omni_retail.db")

_engine = make_engine(DB_PATH)
_SessionLocal = make_session_factory(_engine)


def get_session() -> Iterator[Session]:
    with _SessionLocal() as session:
        yield session


def _resolve_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization.removeprefix("Bearer ").strip()


def get_current_customer(
    authorization: Optional[str] = Header(default=None), session: Session = Depends(get_session)
) -> Customer:
    """Required auth -- for My Orders and anything storefront-account-only."""
    token = _resolve_token(authorization)
    customer_id = get_customer_id(token) if token else None
    if customer_id is None:
        raise HTTPException(status_code=401, detail="Not logged in.")
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=401, detail="Account no longer exists.")
    return customer


def get_current_customer_optional(
    authorization: Optional[str] = Header(default=None), session: Session = Depends(get_session)
) -> Optional[Customer]:
    """Optional auth -- for checkout, where guest checkout is also valid."""
    token = _resolve_token(authorization)
    customer_id = get_customer_id(token) if token else None
    return session.get(Customer, customer_id) if customer_id is not None else None
