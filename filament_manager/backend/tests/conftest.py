"""
Shared pytest fixtures for the filament-manager backend test suite.

A minimal FastAPI app is assembled from the real routers but uses an
in-memory SQLite database (fresh for every test function) instead of the
production /data/filament.db.  The full application lifespan (scheduler,
migrations, seed data) is intentionally skipped so tests are isolated.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.routers import spools, prints, printers, dashboard, app_settings, data_transfer


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def engine():
    """Fresh in-memory SQLite engine with all tables created."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture(scope="function")
def session(engine):
    """SQLAlchemy session bound to the test engine."""
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    sess = Session()
    yield sess
    sess.close()


# ---------------------------------------------------------------------------
# HTTP test client
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def client(session):
    """
    TestClient wired to all routers with get_db overridden to use the
    per-test in-memory session.
    """
    def override_get_db():
        try:
            yield session
        finally:
            pass

    test_app = FastAPI()
    test_app.include_router(spools.router)
    test_app.include_router(prints.router)
    test_app.include_router(printers.router)
    test_app.include_router(dashboard.router)
    test_app.include_router(app_settings.router)
    test_app.include_router(data_transfer.router)
    test_app.dependency_overrides[get_db] = override_get_db

    with TestClient(test_app) as c:
        yield c


# ---------------------------------------------------------------------------
# Reusable data helpers
# ---------------------------------------------------------------------------

SPOOL_DEFAULTS = dict(
    brand="Bambu Lab",
    material="PLA",
    color_name="Red",
    color_hex="#FF0000",
    initial_weight_g=1000.0,
    current_weight_g=1000.0,
)


def make_spool_payload(**overrides) -> dict:
    data = dict(SPOOL_DEFAULTS)
    data.update(overrides)
    return data


def make_print_payload(started_at="2024-01-01T10:00:00", usages=None, **overrides) -> dict:
    data = dict(
        name="Test Print",
        started_at=started_at,
        success=True,
        usages=usages or [],
    )
    data.update(overrides)
    return data
