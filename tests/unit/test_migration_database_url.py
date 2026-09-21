"""Tests for migration database URL normalization."""

from sqlalchemy import create_engine

from migrations.database_url import normalize_database_url


def test_implicit_postgresql_url_uses_psycopg_3() -> None:
    database_url = "postgresql://postgres:secret@127.0.0.1:5432/kanior?sslmode=require"

    normalized_url = normalize_database_url(database_url)

    assert normalized_url == (
        "postgresql+psycopg://postgres:secret@127.0.0.1:5432/kanior?sslmode=require"
    )
    engine = create_engine(normalized_url)
    try:
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()


def test_explicit_psycopg_url_is_unchanged() -> None:
    database_url = "postgresql+psycopg://kanior_migrator:secret@localhost:5432/kanior"

    assert normalize_database_url(database_url) == database_url


def test_non_postgresql_url_is_unchanged() -> None:
    database_url = "sqlite+pysqlite:///:memory:"

    assert normalize_database_url(database_url) == database_url
