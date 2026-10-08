"""Bounded durable-worker execution for credential-free and live adapters."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from contracts.models import AuthContext
from domain.jobs import LeasedJob
from domain.observability import OperationalSignal, SignalSink
from domain.outbox import DispatchResult

JobHandler = Callable[[LeasedJob], str | None]
ScopeProvider = Callable[[], Iterable["WorkerScope"]]


class JobStore(Protocol):
    def claim(self, *args: Any, **kwargs: Any) -> LeasedJob | None: ...
    def heartbeat(self, *args: Any, **kwargs: Any) -> object: ...
    def complete(self, *args: Any, **kwargs: Any) -> None: ...
    def fail(self, *args: Any, **kwargs: Any) -> None: ...


class EventDispatcher(Protocol):
    def dispatch(self, *args: Any, **kwargs: Any) -> DispatchResult: ...


@dataclass(frozen=True)
class WorkerScope:
    context: AuthContext
    project_id: UUID
    dispatch_action: str = "outbox.dispatch"
    execute_action: str = "jobs.execute"


@dataclass(frozen=True)
class WorkerCycle:
    events_dispatched: int
    unsupported_events: int
    jobs_succeeded: int
    jobs_retried: int


class DurableWorker:
    def __init__(
        self,
        jobs: JobStore,
        outbox: EventDispatcher,
        handlers: Mapping[str, JobHandler],
        signals: SignalSink,
        *,
        worker_id: str,
    ) -> None:
        if not worker_id or len(worker_id) > 200:
            raise ValueError("invalid worker id")
        self._jobs = jobs
        self._outbox = outbox
        self._handlers = handlers
        self._signals = signals
        self._worker_id = worker_id

    def run_once(self, scope: WorkerScope, *, max_jobs: int = 25) -> WorkerCycle:
        if max_jobs < 1 or max_jobs > 100:
            raise ValueError("invalid job limit")
        dispatched = self._outbox.dispatch(
            scope.context, scope.project_id, action=scope.dispatch_action, limit=max_jobs
        )
        succeeded = retried = 0
        for _ in range(max_jobs):
            job = self._jobs.claim(
                scope.context,
                scope.project_id,
                worker_id=self._worker_id,
                action=scope.execute_action,
            )
            if job is None:
                break
            handler = self._handlers.get(job.job_type)
            if handler is None:
                self._jobs.fail(
                    scope.context,
                    scope.project_id,
                    job.job_id,
                    worker_id=self._worker_id,
                    action=scope.execute_action,
                    safe_error_code="unsupported_job_type",
                    retry_after_seconds=0,
                )
                retried += 1
                self._emit(job, "retry", "unsupported_job_type")
                continue
            try:
                # Heartbeat revalidates the current service grant immediately before the effect.
                self._jobs.heartbeat(
                    scope.context,
                    scope.project_id,
                    job.job_id,
                    worker_id=self._worker_id,
                    action=scope.execute_action,
                )
                provider_ref = handler(job)
                self._jobs.complete(
                    scope.context,
                    scope.project_id,
                    job.job_id,
                    worker_id=self._worker_id,
                    action=scope.execute_action,
                    provider_ref=provider_ref,
                )
                succeeded += 1
                self._emit(job, "succeeded")
            except Exception:
                self._jobs.fail(
                    scope.context,
                    scope.project_id,
                    job.job_id,
                    worker_id=self._worker_id,
                    action=scope.execute_action,
                    safe_error_code="handler_failed",
                    retry_after_seconds=min(300, 2 ** min(job.attempt, 8)),
                )
                retried += 1
                self._emit(job, "retry", "handler_failed")
        return WorkerCycle(dispatched.dispatched, dispatched.unsupported, succeeded, retried)

    def _emit(self, job: LeasedJob, outcome: str, safe_code: str | None = None) -> None:
        trace = job.payload.get("trace_id")
        self._signals.emit(
            OperationalSignal(
                name="job.execution",
                trace_id=trace if isinstance(trace, str) else str(job.job_id),
                outcome=outcome,
                count=1,
                safe_code=safe_code,
            )
        )

    def run_until_stopped(
        self,
        scopes: ScopeProvider,
        *,
        should_stop: Callable[[], bool],
        wait: Callable[[float], None],
        idle_seconds: float = 1.0,
        max_jobs_per_scope: int = 25,
    ) -> None:
        """Run authorized scopes continuously with injected shutdown and wait controls.

        Scope discovery stays outside the worker so the loop cannot invent project
        authority. Production and synthetic hosts must supply already provisioned
        service scopes; each database operation still revalidates its service grant.
        """

        if idle_seconds < 0:
            raise ValueError("invalid idle interval")
        while not should_stop():
            work = 0
            for scope in scopes():
                if should_stop():
                    break
                cycle = self.run_once(scope, max_jobs=max_jobs_per_scope)
                work += cycle.events_dispatched + cycle.jobs_succeeded + cycle.jobs_retried
            if work == 0 and not should_stop():
                wait(idle_seconds)
