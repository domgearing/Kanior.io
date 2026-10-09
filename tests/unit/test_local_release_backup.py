import base64
import json
from types import SimpleNamespace

import pytest

from api.config import Environment, IntegrationsMode
from scripts import local_release_backup as backup


def _ref(bucket: str, key: str, version: str) -> str:
    raw = json.dumps([bucket, key, version]).encode()
    return "b2v1:" + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def test_decode_ref_rejects_wrong_bucket_and_prefix() -> None:
    ref = _ref("runtime", "verelo/objects/ab/file", "version-1")
    assert backup.decode_ref(ref, "runtime", "verelo/") == (
        "verelo/objects/ab/file",
        "version-1",
    )
    with pytest.raises(backup.BackupFailure, match="object_ref_outside_source_scope"):
        backup.decode_ref(ref, "other", "verelo/")
    with pytest.raises(backup.BackupFailure, match="object_ref_outside_source_scope"):
        backup.decode_ref(ref, "runtime", "other/")
    with pytest.raises(backup.BackupFailure, match="invalid_object_ref"):
        backup.decode_ref("b2v1:not-base64", "runtime", "verelo/")


def test_object_rows_deduplicates_and_checks_integrity() -> None:
    digest = "a" * 64
    assert backup.object_rows([("ref", digest, None), ("ref", digest, 4)]) == [
        {"ref": "ref", "sha256": digest, "size": 4}
    ]
    with pytest.raises(backup.BackupFailure, match="inconsistent_object_reference"):
        backup.object_rows([("ref", digest, 4), ("ref", "b" * 64, 4)])
    with pytest.raises(backup.BackupFailure, match="invalid_object_hash"):
        backup.object_rows([("ref", "invalid", 4)])


def test_backup_requires_independent_bucket() -> None:
    settings = SimpleNamespace(
        environment=Environment.LOCAL,
        integrations_mode=IntegrationsMode.LIVE,
        b2_bucket_name="same",
        b2_backup_bucket_name="same",
    )
    with pytest.raises(backup.BackupFailure, match="backup_bucket_must_be_separate"):
        backup.validate_settings(settings)  # type: ignore[arg-type]


def test_backup_status_never_contains_content(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(backup, "STATUS", tmp_path / "backup-status.json")
    backup._write_status(success=True, code="verified", snapshot="snapshot-1", count=2)
    backup._write_status(success=False, code="provider_error")
    value = json.loads(backup.STATUS.read_text(encoding="utf-8"))
    assert value["state"] == "failed"
    assert value["code"] == "provider_error"
    assert value["snapshot"] == "snapshot-1"
    assert value["object_count"] == 2
    assert "last_success_at" in value
