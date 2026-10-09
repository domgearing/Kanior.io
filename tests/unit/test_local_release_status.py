import json
from datetime import UTC, datetime, timedelta

from scripts import local_release_status


def test_process_status_requires_fresh_heartbeat(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    status = tmp_path / "status.json"
    monkeypatch.setattr(local_release_status, "STATUS", status)
    assert local_release_status.process_status() == {"api": False, "worker": False}

    status.write_text(
        json.dumps(
            {
                "checked_at": datetime.now(UTC).isoformat(),
                "components": {"api": {"running": True}, "worker": {"running": False}},
            }
        ),
        encoding="utf-8",
    )
    assert local_release_status.process_status() == {"api": True, "worker": False}

    status.write_text(
        json.dumps(
            {
                "checked_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                "components": {"api": {"running": True}, "worker": {"running": True}},
            }
        ),
        encoding="utf-8",
    )
    assert local_release_status.process_status() == {"api": False, "worker": False}


def test_backup_status_requires_recent_verified_success(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    status = tmp_path / "backup-status.json"
    monkeypatch.setattr(local_release_status, "BACKUP_STATUS", status)
    assert local_release_status.backup_status() == (False, "backup_not_verified")
    status.write_text(
        json.dumps(
            {
                "last_success_at": datetime.now(UTC).isoformat(),
                "state": "ok",
                "code": "verified",
            }
        ),
        encoding="utf-8",
    )
    assert local_release_status.backup_status() == (True, "verified")
    status.write_text(
        json.dumps(
            {
                "last_success_at": datetime.now(UTC).isoformat(),
                "state": "failed",
                "code": "database_command_failed",
            }
        ),
        encoding="utf-8",
    )
    assert local_release_status.backup_status() == (False, "database_command_failed")
    status.write_text(
        json.dumps(
            {
                "last_success_at": (datetime.now(UTC) - timedelta(days=3)).isoformat(),
                "state": "ok",
                "code": "verified",
            }
        ),
        encoding="utf-8",
    )
    assert local_release_status.backup_status() == (False, "backup_stale")
