from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(db_path: str = "omni_retail.db", echo: bool = False):
    return create_engine(f"sqlite:///{db_path}", echo=echo)


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine):
    from omni_retail import models  # noqa: F401  (register model metadata)

    Base.metadata.create_all(engine)
