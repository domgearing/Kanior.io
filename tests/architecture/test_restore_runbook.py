from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_restore_runbook_covers_architecture_reopening_controls() -> None:
    runbook = (ROOT / "runbooks/database-object-restore.md").read_text(encoding="utf-8")
    for requirement in (
        "isolated recovery",
        "deletion ledger",
        "SHA-256",
        "Rebuild derived",
        "provider reconciliation",
        "RLS/cross-tenant",
        "explicitly authorizes reopening",
    ):
        assert requirement in runbook


def test_restore_smoke_backs_up_and_verifies_database_and_objects() -> None:
    script = (ROOT / "scripts/backup-restore-smoke.sh").read_text(encoding="utf-8")
    for command in ("pg_dump", "pg_restore", "objects.tar.gz", "sha256sum --check"):
        assert command in script
    assert "synthetic original audio" in script
