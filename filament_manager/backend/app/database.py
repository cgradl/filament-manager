import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATA_DIR = os.environ.get("DATA_DIR", "/data")
DATABASE_URL = f"sqlite:///{DATA_DIR}/filament.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _connection_record):
    """Per-connection SQLite settings.

    - foreign_keys: SQLite ignores ON DELETE CASCADE / SET NULL unless enabled;
      without it, deleting a spool leaves orphaned spool_audit rows.
    - WAL + busy_timeout: multiple writers exist (route handlers in the thread
      pool, MQTT-driven print monitor tasks, background cloud-sync tasks,
      ha_publisher) — WAL allows concurrent reads during writes and the busy
      timeout retries instead of failing with 'database is locked'.
    """
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
