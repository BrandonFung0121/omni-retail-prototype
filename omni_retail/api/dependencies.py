import os
from collections.abc import Iterator

from sqlalchemy.orm import Session

from omni_retail.database import make_engine, make_session_factory

DB_PATH = os.environ.get("OMNI_RETAIL_DB_PATH", "omni_retail.db")

_engine = make_engine(DB_PATH)
_SessionLocal = make_session_factory(_engine)


def get_session() -> Iterator[Session]:
    with _SessionLocal() as session:
        yield session
