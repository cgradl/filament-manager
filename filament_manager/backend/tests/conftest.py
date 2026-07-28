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
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
import app.models  # noqa: F401 — registers all ORM models with Base before create_all
from app.routers import spools, prints, printers, dashboard, app_settings, data_transfer, bambu_cloud, filament_sync


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def engine():
    """Fresh in-memory SQLite engine with all tables created.

    foreign_keys=ON matches the production engine (see app.database) so tests
    exercise the same ON DELETE CASCADE / SET NULL behavior.
    """
    from sqlalchemy import event

    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

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
    test_app.include_router(bambu_cloud.router)
    test_app.include_router(filament_sync.router)
    test_app.dependency_overrides[get_db] = override_get_db

    with TestClient(test_app) as c:
        yield c


# ---------------------------------------------------------------------------
# Reusable data helpers
# ---------------------------------------------------------------------------

from sqlalchemy.orm import sessionmaker as _sessionmaker  # noqa: E402


@pytest.fixture(scope="function")
def session_factory(engine):
    """
    Callable session factory backed by the per-test in-memory engine.

    Used to patch `print_monitor.SessionLocal` in background-task tests so
    every `SessionLocal()` call inside the function under test returns a fresh
    session that shares the same in-memory SQLite database as the test's
    `session` fixture (StaticPool ensures one connection for all sessions).
    """
    return _sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
