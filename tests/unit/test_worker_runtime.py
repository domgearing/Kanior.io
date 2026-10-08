from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from contracts.models import AuthContext
from domain.jobs import LeasedJob
from domain.observability import InMemorySignalSink
from domain.outbox import DispatchResult
from workers.runtime import DurableWorker, WorkerScope


class FakeOutbox:
    def dispatch(self, *_args: Any, **_kwargs: Any) -> DispatchResult:
        return DispatchResult(2, 1)


class EmptyOutbox:
    def dispatch(self, *_args: Any, **_kwargs: Any) -> DispatchResult:
        return DispatchResult(0, 0)


class FakeJobs:
    def __init__(self, jobs: list[LeasedJob]) -> None:
        self.jobs = jobs
        self.completed: list[UUID] = []
        self.failed: list[tuple[UUID, str, int]] = []
        self.heartbeats: list[UUID] = []

    def claim(self, *_args: Any, **_kwargs: Any) -> LeasedJob | None:
        return self.jobs.pop(0) if self.jobs else None

    def heartbeat(self, *_args: Any, **kwargs: Any) -> datetime:
        self.heartbeats.append(kwargs.get("job_id", _args[2]))
        return datetime.now(UTC) + timedelta(seconds=60)

    def complete(self, *_args: Any, **kwargs: Any) -> None:
        self.completed.append(kwargs.get("job_id", _args[2]))

    def fail(self, *_args: Any, **kwargs: Any) -> None:
        job_id = kwargs.get("job_id", _args[2])
        self.failed.append((job_id, kwargs["safe_error_code"], kwargs["retry_after_seconds"]))


def _scope() -> WorkerScope:
    return WorkerScope(
        AuthContext(
            principal_kind="service",
            principal_id=uuid4(),
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            authorization_epoch=0,
            capabilities=[],
            request_id=str(uuid4()),
        ),
        uuid4(),
    )


def _job(job_type: str, attempt: int = 1) -> LeasedJob:
    return LeasedJob(
        uuid4(),
        job_type,
        {"trace_id": str(uuid4())},
        attempt,
        datetime.now(UTC) + timedelta(seconds=60),
    )


def test_worker_completes_known_work_and_reports_content_free_signal() -> None:
    job = _job("known")
    jobs = FakeJobs([job])
    signals = InMemorySignalSink()
    worker = DurableWorker(
        jobs, FakeOutbox(), {"known": lambda _job: "synthetic-ref"}, signals, worker_id="w1"
    )

    result = worker.run_once(_scope())

    assert (
        result.events_dispatched,
        result.unsupported_events,
        result.jobs_succeeded,
        result.jobs_retried,
    ) == (2, 1, 1, 0)
    assert jobs.heartbeats == [job.job_id]
    assert jobs.completed == [job.job_id]
    assert signals.signals[0].outcome == "succeeded"
    assert set(signals.signals[0].__dict__) == {
        "name",
        "trace_id",
        "outcome",
        "duration_ms",
        "count",
        "safe_code",
    }


def test_worker_retries_failure_and_unknown_type_without_leaking_exception() -> None:
    failed, unknown = _job("known", 3), _job("unknown")
    jobs = FakeJobs([failed, unknown])
    signals = InMemorySignalSink()

    def broken(_job: LeasedJob) -> None:
        raise RuntimeError("confidential sentinel must not enter the signal")

    worker = DurableWorker(jobs, FakeOutbox(), {"known": broken}, signals, worker_id="w1")
    result = worker.run_once(_scope())

    assert result.jobs_retried == 2
    assert jobs.failed == [
        (failed.job_id, "handler_failed", 8),
        (unknown.job_id, "unsupported_job_type", 0),
    ]
    assert "confidential sentinel" not in repr(signals.signals)


def test_worker_loop_uses_only_supplied_scopes_and_waits_when_idle() -> None:
    jobs = FakeJobs([])
    worker = DurableWorker(
        jobs, EmptyOutbox(), {}, InMemorySignalSink(), worker_id="synthetic-loop"
    )
    scope = _scope()
    calls = 0
    waits: list[float] = []

    def should_stop() -> bool:
        return calls >= 2

    def scopes() -> list[WorkerScope]:
        nonlocal calls
        calls += 1
        return [scope]

    worker.run_until_stopped(scopes, should_stop=should_stop, wait=waits.append)

    assert calls == 2
    assert waits == [1.0]
