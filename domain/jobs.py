"""Durable, project-scoped job leasing and completion primitives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Engine, text

from api.database import scoped_transaction
from contracts.models import AuthContext
from domain.errors import CONFLICT


@dataclass(frozen=True)
class LeasedJob:
    job_id: UUID
    job_type: str
    payload: dict[str, Any]
    attempt: int
    lease_until: datetime


@dataclass(frozen=True)
class QueueHealth:
    pending_count: int
    retry_count: int
    leased_count: int
    expired_lease_count: int
    dead_letter_count: int
    oldest_ready_age_seconds: float | None


class DurableJobStore:
    """Lease jobs under an explicit service action; never bypasses project RLS."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def claim(
        self,
        context: AuthContext,
        project_id: UUID,
        *,
        worker_id: str,
        action: str,
        lease_seconds: int = 60,
    ) -> LeasedJob | None:
        if (
            context.principal_kind != "service"
            or not worker_id
            or len(worker_id) > 200
            or lease_seconds < 1
        ):
            raise CONFLICT
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=lease_seconds)
        with scoped_transaction(self._engine, context, project_id, action) as connection:
            row = (
                connection.execute(
                    text(
                        """WITH candidate AS (
                          SELECT id FROM jobs
                          WHERE (status IN ('pending','retry') AND next_attempt_at<=:now)
                             OR (status='leased' AND lease_until<=:now)
                          ORDER BY next_attempt_at,created_at,id
                          FOR UPDATE SKIP LOCKED LIMIT 1
                        )
                        UPDATE jobs j SET status='leased',attempt=j.attempt+1,
                          lease_owner=:owner,lease_until=:lease_until,updated_at=:now
                        FROM candidate WHERE j.id=candidate.id
                        RETURNING j.id,j.job_type,j.payload,j.attempt,j.lease_until"""
                    ),
                    {"now": now, "owner": worker_id, "lease_until": lease_until},
                )
                .mappings()
                .one_or_none()
            )
        return (
            None
            if row is None
            else LeasedJob(
                row["id"], row["job_type"], dict(row["payload"]), row["attempt"], row["lease_until"]
            )
        )

    def heartbeat(
        self,
        context: AuthContext,
        project_id: UUID,
        job_id: UUID,
        *,
        worker_id: str,
        action: str,
        lease_seconds: int = 60,
    ) -> datetime:
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=lease_seconds)
        with scoped_transaction(self._engine, context, project_id, action) as connection:
            updated = connection.execute(
                text(
                    """UPDATE jobs SET lease_until=:until,updated_at=:now
                    WHERE id=:id AND status='leased' AND lease_owner=:owner
                      AND lease_until>:now RETURNING lease_until"""
                ),
                {"until": lease_until, "now": now, "id": job_id, "owner": worker_id},
            ).scalar_one_or_none()
        if updated is None:
            raise CONFLICT
        return cast(datetime, updated)

    def complete(
        self,
        context: AuthContext,
        project_id: UUID,
        job_id: UUID,
        *,
        worker_id: str,
        action: str,
        provider_ref: str | None = None,
    ) -> None:
        self._finish(context, project_id, job_id, worker_id, action, True, provider_ref, None)

    def fail(
        self,
        context: AuthContext,
        project_id: UUID,
        job_id: UUID,
        *,
        worker_id: str,
        action: str,
        safe_error_code: str,
        retry_after_seconds: int,
    ) -> None:
        if not safe_error_code or len(safe_error_code) > 100 or retry_after_seconds < 0:
            raise CONFLICT
        self._finish(
            context,
            project_id,
            job_id,
            worker_id,
            action,
            False,
            None,
            (safe_error_code, retry_after_seconds),
        )

    def _finish(
        self,
        context: AuthContext,
        project_id: UUID,
        job_id: UUID,
        worker_id: str,
        action: str,
        succeeded: bool,
        provider_ref: str | None,
        failure: tuple[str, int] | None,
    ) -> None:
        now = datetime.now(UTC)
        with scoped_transaction(self._engine, context, project_id, action) as connection:
            if succeeded:
                statement = """UPDATE jobs SET status='succeeded',provider_ref=:provider,
                    lease_owner=NULL,lease_until=NULL,updated_at=:now
                    WHERE id=:id AND status='leased' AND lease_owner=:owner
                    RETURNING id"""
                values = {"provider": provider_ref, "now": now, "id": job_id, "owner": worker_id}
            else:
                assert failure is not None
                code, delay = failure
                statement = """UPDATE jobs SET
                    status=CASE WHEN attempt>=max_attempts THEN 'dead_letter' ELSE 'retry' END,
                    safe_error_code=:code,next_attempt_at=:retry_at,
                    lease_owner=NULL,lease_until=NULL,updated_at=:now
                    WHERE id=:id AND status='leased' AND lease_owner=:owner
                    RETURNING id"""
                values = {
                    "code": code,
                    "retry_at": now + timedelta(seconds=max(0, delay)),
                    "now": now,
                    "id": job_id,
                    "owner": worker_id,
                }
            updated = connection.execute(text(statement), values).scalar_one_or_none()
        if updated is None:
            raise CONFLICT

    def health(self, context: AuthContext, project_id: UUID, *, action: str) -> QueueHealth:
        """Return content-free queue signals for one authorized project scope."""

        now = datetime.now(UTC)
        with scoped_transaction(self._engine, context, project_id, action) as connection:
            row = (
                connection.execute(
                    text(
                        """SELECT
                          count(*) FILTER (WHERE status='pending') AS pending_count,
                          count(*) FILTER (WHERE status='retry') AS retry_count,
                          count(*) FILTER (WHERE status='leased') AS leased_count,
                          count(*) FILTER (WHERE status='leased' AND lease_until<=:now)
                            AS expired_lease_count,
                          count(*) FILTER (WHERE status='dead_letter') AS dead_letter_count,
                          EXTRACT(EPOCH FROM (:now - min(next_attempt_at))) FILTER (
                            WHERE status IN ('pending','retry') AND next_attempt_at<=:now
                          ) AS oldest_ready_age_seconds
                        FROM jobs"""
                    ),
                    {"now": now},
                )
                .mappings()
                .one()
            )
        age = row["oldest_ready_age_seconds"]
        return QueueHealth(
            pending_count=row["pending_count"],
            retry_count=row["retry_count"],
            leased_count=row["leased_count"],
            expired_lease_count=row["expired_lease_count"],
            dead_letter_count=row["dead_letter_count"],
            oldest_ready_age_seconds=None if age is None else max(0.0, float(age)),
        )
