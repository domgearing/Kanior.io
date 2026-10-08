"""Database engine and transaction-local trusted context helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import Connection, Engine, create_engine, text

from api.config import Settings, get_settings
from contracts.models import AuthContext


def create_database_engine(settings: Settings | None = None) -> Engine:
    value = settings or get_settings()
    return create_engine(value.database_url, pool_pre_ping=True, future=True)


def bind_context(
    connection: Connection,
    context: AuthContext,
    project_id: UUID | None = None,
    action: str = "",
) -> None:
    values = {
        "app.principal_kind": context.principal_kind,
        "app.principal_id": str(context.principal_id),
        "app.tenant_id": str(context.tenant_id),
        "app.workspace_id": str(context.workspace_id),
        "app.project_id": "" if project_id is None else str(project_id),
        "app.action": action,
    }
    for name, value in values.items():
        connection.execute(
            text("SELECT set_config(:name, :value, true)"), {"name": name, "value": value}
        )


@contextmanager
def scoped_transaction(
    engine: Engine,
    context: AuthContext,
    project_id: UUID | None = None,
    action: str = "",
) -> Iterator[Connection]:
    with engine.begin() as connection:
        bind_context(connection, context, project_id, action)
        yield connection
