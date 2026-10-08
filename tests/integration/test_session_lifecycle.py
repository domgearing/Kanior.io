from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from api.config import Settings
from api.main import create_app


def test_session_lifecycle_csrf_origin_renewal_and_revocation(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    admin = create_engine(
        os.environ.get(
            "VERELO_TEST_ADMIN_DATABASE_URL",
            "postgresql+psycopg://verelo_admin:verelo_admin@127.0.0.1:5432/verelo",
        )
    )
    api = create_engine(Settings().database_url)
    tenant, workspace, user, session = uuid4(), uuid4(), uuid4(), uuid4()
    token = "fictional-session-token-000000000000"
    csrf = "fictional-csrf-token-000000000000000"
    now = datetime.now(UTC)
    monkeypatch.setenv("VERELO_PUBLIC_ORIGIN", "http://127.0.0.1:5173")
    try:
        with admin.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO tenants (id,entra_tenant_id,policy_config_ref,region)
                    VALUES (:id,:entra,'synthetic','local')"""
                ),
                {"id": tenant, "entra": uuid4()},
            )
            connection.execute(
                text(
                    """INSERT INTO workspaces (id,tenant_id,name,is_default)
                    VALUES (:id,:tenant,'Synthetic',true)"""
                ),
                {"id": workspace, "tenant": tenant},
            )
            connection.execute(
                text(
                    """INSERT INTO users
                    (id,tenant_id,entra_object_id,display_name,email)
                    VALUES (:id,:tenant,:entra,'Session User','session.invalid')"""
                ),
                {"id": user, "tenant": tenant, "entra": uuid4()},
            )
            connection.execute(
                text("""INSERT INTO sessions
                    (id,tenant_id,workspace_id,user_id,token_sha256,csrf_token,csrf_sha256,
                     last_seen_at,idle_expires_at,absolute_expires_at)
                    VALUES
                    (:id,:tenant,:workspace,:user,:token,:csrf,:csrf_hash,:seen,:idle,:absolute)"""),
                {
                    "id": session,
                    "tenant": tenant,
                    "workspace": workspace,
                    "user": user,
                    "token": sha256(token.encode()).hexdigest(),
                    "csrf": csrf,
                    "csrf_hash": sha256(csrf.encode()).hexdigest(),
                    "seen": now - timedelta(minutes=10),
                    "idle": now + timedelta(minutes=5),
                    "absolute": now + timedelta(hours=2),
                },
            )
        app = create_app(api)
        auth = {"Cookie": f"verelo_session={token}"}
        with TestClient(app) as client:
            assert client.get("/api/v1/me").status_code == 401
            assert client.get("/api/v1/me", headers=auth).status_code == 200
            assert (
                client.post("/api/v1/projects", headers=auth, json={"name": "Denied"}).status_code
                == 403
            )
            wrong_origin = client.post(
                "/api/v1/projects",
                headers={
                    **auth,
                    "X-CSRF-Token": csrf,
                    "Origin": "https://attacker.invalid",
                },
                json={"name": "Denied"},
            )
            assert wrong_origin.status_code == 403
        with admin.begin() as connection:
            renewed = connection.execute(
                text("SELECT last_seen_at,idle_expires_at FROM sessions WHERE id=:id"),
                {"id": session},
            ).one()
            assert renewed.last_seen_at > now - timedelta(minutes=1)
            assert renewed.idle_expires_at > now + timedelta(minutes=20)
            connection.execute(
                text("UPDATE sessions SET revoked_at=now() WHERE id=:id"), {"id": session}
            )
        with TestClient(app) as client:
            assert client.get("/api/v1/me", headers=auth).status_code == 401
        with admin.begin() as connection:
            connection.execute(
                text(
                    """UPDATE sessions SET revoked_at=NULL,
                    idle_expires_at=now()-interval '1 second' WHERE id=:id"""
                ),
                {"id": session},
            )
        with TestClient(app) as client:
            assert client.get("/api/v1/me", headers=auth).status_code == 401
        with admin.begin() as connection:
            connection.execute(
                text("""UPDATE sessions SET idle_expires_at=now()-interval '2 seconds',
                    absolute_expires_at=now()-interval '1 second' WHERE id=:id"""),
                {"id": session},
            )
        with TestClient(app) as client:
            assert client.get("/api/v1/me", headers=auth).status_code == 401
        with admin.begin() as connection:
            connection.execute(
                text("""UPDATE sessions SET idle_expires_at=now()+interval '30 minutes',
                    absolute_expires_at=now()+interval '2 hours' WHERE id=:id"""),
                {"id": session},
            )
            connection.execute(text("UPDATE users SET enabled=false WHERE id=:id"), {"id": user})
        with TestClient(app) as client:
            assert client.get("/api/v1/me", headers=auth).status_code == 401
    finally:
        api.dispose()
        with admin.begin() as connection:
            connection.execute(text("DELETE FROM sessions WHERE id=:id"), {"id": session})
            connection.execute(text("DELETE FROM users WHERE id=:id"), {"id": user})
            connection.execute(text("DELETE FROM workspaces WHERE id=:id"), {"id": workspace})
            connection.execute(text("DELETE FROM tenants WHERE id=:id"), {"id": tenant})
        admin.dispose()


def test_transaction_local_rls_context_clears_after_rollback() -> None:
    api = create_engine(Settings().database_url, pool_size=1, max_overflow=0)
    tenant, workspace, principal = uuid4(), uuid4(), uuid4()
    try:
        try:
            with api.begin() as connection:
                connection.execute(
                    text("SELECT set_config('app.tenant_id',:value,true)"), {"value": str(tenant)}
                )
                connection.execute(
                    text("SELECT set_config('app.workspace_id',:value,true)"),
                    {"value": str(workspace)},
                )
                connection.execute(
                    text("SELECT set_config('app.principal_id',:value,true)"),
                    {"value": str(principal)},
                )
                connection.execute(text("SELECT set_config('app.principal_kind','employee',true)"))
                raise RuntimeError("force rollback")
        except RuntimeError:
            pass
        with api.begin() as connection:
            assert (
                connection.execute(
                    text("SELECT current_setting('app.tenant_id',true)")
                ).scalar_one()
                == ""
            )
            assert connection.execute(text("SELECT count(*) FROM projects")).scalar_one() == 0
    finally:
        api.dispose()
