"""Small shared helpers."""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive-UTC now — the storage convention for all DateTime columns.

    Replaces the deprecated datetime.utcnow() (removed in Python 3.13+).
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
