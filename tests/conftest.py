import pytest

from omni_retail.data.seed import seed_database
from omni_retail.database import init_db, make_engine, make_session_factory


@pytest.fixture(scope="session")
def seeded_session_factory():
    engine = make_engine(":memory:")
    init_db(engine)
    SessionLocal = make_session_factory(engine)
    with SessionLocal() as session:
        seed_database(session)
    return SessionLocal


@pytest.fixture()
def session(seeded_session_factory):
    with seeded_session_factory() as session:
        yield session
