from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def make_engine(db_path: str = "omni_retail.db", echo: bool = False):
    if db_path == ":memory:":
        # A single shared connection is required so the in-memory database
        # survives across sessions and across the worker threads FastAPI's
        # TestClient dispatches sync endpoints to.
        return create_engine(
            "sqlite:///:memory:",
            echo=echo,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(f"sqlite:///{db_path}", echo=echo)


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine):
    from omni_retail import models  # noqa: F401  (register model metadata)

    Base.metadata.create_all(engine)
