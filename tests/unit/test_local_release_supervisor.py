import json

from scripts import local_release_supervisor as supervisor


def test_alert_requires_persistent_failure_and_deduplicates() -> None:
    first = {"worker_process"}
    samples, alerted, notify = supervisor.alert_transition(set(), first, 0, set())
    assert (samples, alerted, notify) == (1, set(), False)
    samples, alerted, notify = supervisor.alert_transition(first, first, samples, alerted)
    assert (samples, alerted, notify) == (2, first, True)
    samples, alerted, notify = supervisor.alert_transition(first, first, samples, alerted)
    assert (samples, alerted, notify) == (3, first, False)
    assert supervisor.alert_transition(first, set(), samples, alerted) == (0, set(), False)


def test_diagnostic_events_contain_only_safe_metadata(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "events.jsonl"
    monkeypatch.setattr(supervisor, "EVENTS", path)
    supervisor.write_event("health", "backup", "down")
    record = json.loads(path.read_text(encoding="utf-8"))
    assert set(record) == {"at", "kind", "component", "code"}
    assert record["component"] == "backup"
