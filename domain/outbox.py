"""Restricted, project-scoped transactional outbox dispatch."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from api.database import scoped_transaction
from contracts.models import AuthContext


@dataclass(frozen=True)
class DispatchResult:
    dispatched: int
    unsupported: int


class OutboxDispatcher:
    """Atomically hand known events to durable jobs without global queue access."""

    _JOB_TYPES = {
        "access.changed": "reconcile_access",
        "transcript.published": "observe_transcript_publication",
        # Kept while the local Phase 2 publisher migrates to the canonical event name.
        "TranscriptPublished": "observe_transcript_publication",
    }

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def dispatch(
        self,
        context: AuthContext,
        project_id: UUID,
        *,
        action: str = "outbox.dispatch",
        limit: int = 50,
    ) -> DispatchResult:
        if context.principal_kind != "service" or limit < 1 or limit > 100:
            raise ValueError("invalid dispatch context")
        dispatched = unsupported = 0
        now = datetime.now(UTC)
        with scoped_transaction(self._engine, context, project_id, action) as connection:
            rows = connection.execute(
                text(
                    """SELECT id,tenant_id,workspace_id,project_id,document_id,aggregate_id,
                              event_type,schema_version,payload,created_at
                       FROM outbox_events
                       WHERE dispatched_at IS NULL
                       ORDER BY created_at,id
                       FOR UPDATE SKIP LOCKED LIMIT :limit"""
                ),
                {"limit": limit},
            ).mappings()
            for row in rows:
                job_type = self._JOB_TYPES.get(row["event_type"])
                if job_type is None or row["schema_version"] != 1:
                    unsupported += 1
                    continue
                payload = self._safe_payload(row)
                serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
                connection.execute(
                    text(
                        """INSERT INTO jobs
                        (id,tenant_id,workspace_id,project_id,document_id,job_type,operation_key,
                         payload_hash,payload,trace_id)
                        VALUES (:id,:tenant,:workspace,:project,:document,:job_type,:operation,
                          :payload_hash,CAST(:payload AS jsonb),:trace)
                        ON CONFLICT (tenant_id,workspace_id,project_id,operation_key) DO NOTHING"""
                    ),
                    {
                        "id": uuid4(),
                        "tenant": row["tenant_id"],
                        "workspace": row["workspace_id"],
                        "project": row["project_id"],
                        "document": row["document_id"],
                        "job_type": job_type,
                        "operation": f"outbox:{row['id']}:{job_type}",
                        "payload_hash": sha256(serialized.encode()).hexdigest(),
                        "payload": serialized,
                        "trace": payload["trace_id"],
                    },
                )
                connection.execute(
                    text("UPDATE outbox_events SET dispatched_at=:now WHERE id=:id"),
                    {"now": now, "id": row["id"]},
                )
                dispatched += 1
        return DispatchResult(dispatched, unsupported)

    @staticmethod
    def _safe_payload(row: Any) -> dict[str, Any]:
        raw = dict(row["payload"])
        trace_id = raw.get("trace_id")
        if not isinstance(trace_id, str) or not trace_id or len(trace_id) > 128:
            trace_id = f"outbox-{row['id']}"
        # Only identifiers and event metadata cross the queue boundary.
        return {
            "event_id": str(row["id"]),
            "event_type": row["event_type"],
            "schema_version": row["schema_version"],
            "aggregate_id": str(row["aggregate_id"]),
            "document_id": None if row["document_id"] is None else str(row["document_id"]),
            "trace_id": trace_id,
        }
