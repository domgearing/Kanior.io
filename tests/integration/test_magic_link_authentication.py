from __future__ import annotations

import json
import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from api.config import Settings
from api.main import create_app
from domain.identity import normalize_email


def test_allowlisted_magic_link_login_replay_logout_and_disable(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    admin = create_engine(
        os.environ.get(
            "VERELO_TEST_ADMIN_DATABASE_URL",
            "postgresql+psycopg://verelo_admin:verelo_admin@127.0.0.1:5432/verelo",
        )
    )
    api = create_engine(Settings().database_url)
    tenant, workspace, user, identity = uuid4(), uuid4(), uuid4(), uuid4()
    email = "allowed.employee@example.invalid"
    origin = "http://127.0.0.1:5173"
    mailbox = tmp_path / "mailbox"
    monkeypatch.setenv("VERELO_PUBLIC_ORIGIN", origin)
    monkeypatch.setenv("VERELO_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("VERELO_DEVELOPMENT_MAILBOX_ROOT", str(mailbox))
    try:
        with admin.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO tenants (id,policy_config_ref,region)
                    VALUES (:id,'synthetic','local')"""
                ),
                {"id": tenant},
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
                    """INSERT INTO users (id,tenant_id,display_name,email)
                    VALUES (:id,:tenant,'Allowed Employee',:email)"""
                ),
                {"id": user, "tenant": tenant, "email": email},
            )
            connection.execute(
                text(
                    """INSERT INTO identity_accounts
                    (id,tenant_id,workspace_id,user_id,provider,subject,login_email_normalized)
                    VALUES (:id,:tenant,:workspace,:user,'magic_link',:subject,:email)"""
                ),
                {
                    "id": identity,
                    "tenant": tenant,
                    "workspace": workspace,
                    "user": user,
                    "subject": str(uuid4()),
                    "email": normalize_email(email),
                },
            )

        app = create_app(api)
        with TestClient(app) as client:
            assert client.get("/api/v1/auth/mode").json() == {"provider": "dev_password"}
            neutral = {
                "status": "accepted",
                "message": "If the account is eligible, a sign-in link will be sent.",
            }
            unknown = client.post(
                "/api/v1/auth/magic-link/request",
                headers={"Origin": origin},
                json={"email": "unknown@example.invalid"},
            )
            assert unknown.status_code == 202
            assert unknown.json() == neutral
            assert not (mailbox / "latest.json").exists()

            wrong_origin = client.post(
                "/api/v1/auth/magic-link/request",
                headers={"Origin": "https://attacker.invalid"},
                json={"email": email},
            )
            assert wrong_origin.status_code == 403

            password_request = client.post(
                "/api/v1/auth/dev-password/request",
                headers={"Origin": origin},
                json={"email": email.upper()},
            )
            assert password_request.status_code == 202
            assert password_request.json() == {
                "status": "accepted",
                "message": "If eligible, a one-time password is in the local mailbox.",
            }
            password_mail = json.loads((mailbox / "latest.json").read_text(encoding="utf-8"))
            assert password_mail["recipient"] == email
            assert "link" not in password_mail
            password = password_mail["password"]
            assert len(password) >= 32
            assert (
                client.post(
                    "/api/v1/auth/dev-password/request",
                    headers={"Origin": origin},
                    json={"email": "unknown@example.invalid"},
                ).status_code
                == 202
            )
            assert (
                json.loads((mailbox / "latest.json").read_text(encoding="utf-8")) == password_mail
            )
            assert (
                client.post(
                    "/api/v1/auth/dev-password/consume",
                    headers={"Origin": origin},
                    json={"email": "wrong@example.invalid", "password": password},
                ).status_code
                == 401
            )
            assert (
                client.post(
                    "/api/v1/auth/dev-password/consume",
                    headers={"Origin": origin},
                    json={"email": email, "password": "x" * 32},
                ).status_code
                == 401
            )
            assert (
                client.post(
                    "/api/v1/auth/dev-password/consume",
                    headers={"Origin": "https://attacker.invalid"},
                    json={"email": email, "password": password},
                ).status_code
                == 403
            )
            assert (
                client.post(
                    "/api/v1/auth/dev-password/consume",
                    headers={"Origin": origin},
                    json={"email": email, "password": password},
                ).status_code
                == 200
            )
            assert client.get("/api/v1/me").status_code == 200
            assert (
                client.post(
                    "/api/v1/auth/dev-password/consume",
                    headers={"Origin": origin},
                    json={"email": email, "password": password},
                ).status_code
                == 401
            )
            password_csrf = client.get("/api/v1/me").json()["csrf_token"]
            assert (
                client.post(
                    "/api/v1/auth/logout",
                    headers={"Origin": origin, "X-CSRF-Token": password_csrf},
                ).status_code
                == 200
            )

            accepted = client.post(
                "/api/v1/auth/magic-link/request",
                headers={"Origin": origin},
                json={"email": email.upper()},
            )
            assert accepted.status_code == 202
            assert accepted.json() == neutral
            link = json.loads((mailbox / "latest.json").read_text(encoding="utf-8"))["link"]
            token = link.split("#token=", 1)[1]

            consumed = client.post(
                "/api/v1/auth/magic-link/consume",
                headers={"Origin": origin},
                json={"token": token},
            )
            assert consumed.status_code == 200
            assert consumed.json() == {"status": "authenticated"}
            me = client.get("/api/v1/me")
            assert me.status_code == 200
            csrf = me.json()["csrf_token"]

            replay = client.post(
                "/api/v1/auth/magic-link/consume",
                headers={"Origin": origin},
                json={"token": token},
            )
            assert replay.status_code == 401

            signed_out = client.post(
                "/api/v1/auth/logout",
                headers={"Origin": origin, "X-CSRF-Token": csrf},
            )
            assert signed_out.status_code == 200
            assert client.get("/api/v1/me").status_code == 401

            client.post(
                "/api/v1/auth/magic-link/request",
                headers={"Origin": origin},
                json={"email": email},
            )
            second_link = json.loads((mailbox / "latest.json").read_text(encoding="utf-8"))["link"]
            second_token = second_link.split("#token=", 1)[1]
            assert (
                client.post(
                    "/api/v1/auth/magic-link/consume",
                    headers={"Origin": origin},
                    json={"token": second_token},
                ).status_code
                == 200
            )
            # Three requests above plus sign-ins and sign-outs must leave room
            # for two more challenges; only accepted requests use quota.
            for _ in range(2):
                assert (
                    client.post(
                        "/api/v1/auth/dev-password/request",
                        headers={"Origin": origin},
                        json={"email": email},
                    ).status_code
                    == 202
                )
                issued = json.loads((mailbox / "latest.json").read_text(encoding="utf-8"))
                assert issued["password"] != password
                password = issued["password"]
            for _ in range(2):
                assert (
                    client.post(
                        "/api/v1/auth/dev-password/request",
                        headers={"Origin": origin},
                        json={"email": email},
                    ).status_code
                    == 202
                )
                assert json.loads((mailbox / "latest.json").read_text(encoding="utf-8")) == issued
            with admin.begin() as connection:
                connection.execute(
                    text("UPDATE users SET enabled=false WHERE id=:id"), {"id": user}
                )
            assert client.get("/api/v1/me").status_code == 401
    finally:
        api.dispose()
        with admin.begin() as connection:
            connection.execute(
                text("DELETE FROM authentication_events WHERE user_id=:id"), {"id": user}
            )
            connection.execute(text("DELETE FROM sessions WHERE user_id=:id"), {"id": user})
            connection.execute(
                text("DELETE FROM magic_link_challenges WHERE user_id=:id"), {"id": user}
            )
            connection.execute(
                text("DELETE FROM identity_accounts WHERE user_id=:id"), {"id": user}
            )
            connection.execute(text("DELETE FROM users WHERE id=:id"), {"id": user})
            connection.execute(text("DELETE FROM workspaces WHERE id=:id"), {"id": workspace})
            connection.execute(text("DELETE FROM tenants WHERE id=:id"), {"id": tenant})
        admin.dispose()
