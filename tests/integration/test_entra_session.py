from __future__ import annotations

import os
from uuid import uuid4

from sqlalchemy import create_engine, text

from api.config import Settings


def test_entra_session_requires_preprovisioned_enabled_identity_and_one_time_flow() -> None:
    admin = create_engine(
        os.environ.get(
            "VERELO_TEST_ADMIN_DATABASE_URL",
            "postgresql+psycopg://verelo_admin:verelo_admin@127.0.0.1:5432/verelo",
        )
    )
    api = create_engine(Settings().database_url)
    tenant, workspace, user, oid, identity = (uuid4() for _ in range(5))
    flow_state, browser = uuid4().hex, uuid4().hex
    session_id, token, csrf = uuid4(), uuid4().hex, uuid4().hex
    try:
        with admin.begin() as connection:
            connection.execute(
                text("""INSERT INTO tenants(id,entra_tenant_id,policy_config_ref,region)
                VALUES (:id,:entra,'synthetic','local')"""),
                {"id": tenant, "entra": tenant},
            )
            connection.execute(
                text("""INSERT INTO workspaces(id,tenant_id,name,is_default)
                VALUES (:id,:tenant,'Entra Test',true)"""),
                {"id": workspace, "tenant": tenant},
            )
            connection.execute(
                text("""INSERT INTO users(id,tenant_id,entra_object_id,display_name,email)
                VALUES (:id,:tenant,:oid,'Entra Test','entra-test@example.invalid')"""),
                {"id": user, "tenant": tenant, "oid": oid},
            )
            connection.execute(
                text("""INSERT INTO identity_accounts
                (id,tenant_id,workspace_id,user_id,provider,subject)
                VALUES (:id,:tenant,:workspace,:user,'entra',:subject)"""),
                {
                    "id": identity,
                    "tenant": tenant,
                    "workspace": workspace,
                    "user": user,
                    "subject": str(oid),
                },
            )
        with api.begin() as connection:
            connection.execute(
                text("SELECT verelo_begin_entra_flow(:state,:browser,CAST(:flow AS jsonb))"),
                {"state": flow_state, "browser": browser, "flow": '{"state":"test"}'},
            )
            assert (
                connection.execute(
                    text("SELECT verelo_take_entra_flow(:state,:browser)"),
                    {"state": flow_state, "browser": "wrong"},
                ).scalar_one()
                is None
            )
            assert connection.execute(
                text("SELECT verelo_take_entra_flow(:state,:browser)"),
                {"state": flow_state, "browser": browser},
            ).scalar_one() == {"state": "test"}
            assert (
                connection.execute(
                    text("SELECT verelo_take_entra_flow(:state,:browser)"),
                    {"state": flow_state, "browser": browser},
                ).scalar_one()
                is None
            )
            assert not connection.execute(
                text("""SELECT verelo_create_entra_session(
                :tenant,:oid,:session,:token,:csrf,:csrf_hash)"""),
                {
                    "tenant": uuid4(),
                    "oid": oid,
                    "session": uuid4(),
                    "token": uuid4().hex,
                    "csrf": csrf,
                    "csrf_hash": csrf,
                },
            ).scalar_one()
            assert not connection.execute(
                text("""SELECT verelo_create_entra_session(
                :tenant,:oid,:session,:token,:csrf,:csrf_hash)"""),
                {
                    "tenant": tenant,
                    "oid": uuid4(),
                    "session": uuid4(),
                    "token": uuid4().hex,
                    "csrf": csrf,
                    "csrf_hash": csrf,
                },
            ).scalar_one()
            assert connection.execute(
                text("""SELECT verelo_create_entra_session(
                :tenant,:oid,:session,:token,:csrf,:csrf_hash)"""),
                {
                    "tenant": tenant,
                    "oid": oid,
                    "session": session_id,
                    "token": token,
                    "csrf": csrf,
                    "csrf_hash": csrf,
                },
            ).scalar_one()
            assert (
                connection.execute(
                    text("SELECT user_id FROM verelo_resolve_session(:token)"),
                    {"token": token},
                ).scalar_one()
                == user
            )
        with admin.begin() as connection:
            connection.execute(text("UPDATE users SET enabled=false WHERE id=:id"), {"id": user})
        with api.begin() as connection:
            assert (
                connection.execute(
                    text("SELECT user_id FROM verelo_resolve_session(:token)"),
                    {"token": token},
                ).scalar_one_or_none()
                is None
            )
    finally:
        with admin.begin() as connection:
            connection.execute(text("DELETE FROM sessions WHERE user_id=:id"), {"id": user})
            connection.execute(
                text("DELETE FROM identity_accounts WHERE user_id=:id"), {"id": user}
            )
            connection.execute(text("DELETE FROM users WHERE id=:id"), {"id": user})
            connection.execute(text("DELETE FROM workspaces WHERE id=:id"), {"id": workspace})
            connection.execute(text("DELETE FROM tenants WHERE id=:id"), {"id": tenant})
            connection.execute(
                text("DELETE FROM entra_auth_flows WHERE state_sha256=:state"),
                {"state": flow_state},
            )
        api.dispose()
        admin.dispose()
