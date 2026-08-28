import pytest
from fastapi.testclient import TestClient

from omni_retail.api.app import create_app
from omni_retail.api.dependencies import get_session
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


@pytest.fixture()
def client(seeded_session_factory):
    app = create_app()

    def _get_test_session():
        with seeded_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _get_test_session
    with TestClient(app) as test_client:
        yield test_client


def _fresh_seeded_session_factory():
    """A brand-new, independently seeded in-memory DB.

    `seeded_session_factory` above is session-scoped and shared by every
    read-only test, which is fine as long as nothing writes to it. Tests
    that call complete_sale() (or anything else that mutates data) must
    use this instead, so a decremented stock count or a new order in one
    test can never leak into another test's assertions.
    """
    engine = make_engine(":memory:")
    init_db(engine)
    SessionLocal = make_session_factory(engine)
    with SessionLocal() as session:
        seed_database(session)
    return SessionLocal


@pytest.fixture()
def fresh_session():
    SessionLocal = _fresh_seeded_session_factory()
    with SessionLocal() as session:
        yield session


@pytest.fixture()
def fresh_client():
    app = create_app()
    SessionLocal = _fresh_seeded_session_factory()

    def _get_test_session():
        with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = _get_test_session
    with TestClient(app) as test_client:
        yield test_client
