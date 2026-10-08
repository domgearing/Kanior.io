"""Provision only disposable PR-gate roles before applying migrations."""

from __future__ import annotations

import os

import psycopg
from sqlalchemy.engine import make_url


def main() -> None:
    raw_url = os.environ.get("PR_GATE_DATABASE_URL", "")
    if not raw_url:
        raise RuntimeError("PR_GATE_DATABASE_URL is required")
    url = make_url(raw_url)
    if url.database != "verelo_pr_gate" or url.host not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("PR-gate role provisioning requires a local verelo_pr_gate database")

    with psycopg.connect(raw_url.replace("postgresql+psycopg://", "postgresql://")) as connection:
        for role in ("verelo_api", "verelo_worker"):
            exists = connection.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)", (role,)
            ).fetchone()
            if exists is None or not exists[0]:
                # These fixed credentials are for the disposable synthetic PR gate only.
                connection.execute(
                    f"CREATE ROLE {role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
                    f"PASSWORD '{role}'"
                )
            connection.execute(f"GRANT CONNECT ON DATABASE verelo_pr_gate TO {role}")
            connection.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
    print("Disposable PR-gate API and worker roles are ready")


if __name__ == "__main__":
    main()
