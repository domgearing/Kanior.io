"""Database URL compatibility helpers for Alembic."""

from __future__ import annotations


def normalize_database_url(database_url: str) -> str:
    """Select the installed psycopg 3 driver for an implicit PostgreSQL URL."""
    implicit_driver_prefix = "postgresql://"
    if database_url.startswith(implicit_driver_prefix):
        return f"postgresql+psycopg://{database_url.removeprefix(implicit_driver_prefix)}"
    return database_url
