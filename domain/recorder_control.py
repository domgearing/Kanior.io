"""Same-employee, short-lived command handoff to an authenticated desktop recorder."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, RowMapping, text

from api.database import scoped_transaction
from contracts.models import (
    AuthContext,
    RecorderCommand,
    RecorderCommandCreate,
    RecorderCommandPoll,
    RecorderCommandResult,
    RecorderDevice,
    RecorderDevicePage,
    RecorderHeartbeat,
)
from domain.errors import CONFLICT, FORBIDDEN, NOT_FOUND, DomainError

_ONLINE_SECONDS = 15


class RecorderControlService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @staticmethod
    def _employee(context: AuthContext) -> None:
        if context.principal_kind != "employee":
            raise FORBIDDEN

    @staticmethod
    def _token_digest(token: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", token):
            raise NOT_FOUND
        return sha256(token.encode()).hexdigest()

    @staticmethod
    def _device(value: RowMapping) -> RecorderDevice:
        return RecorderDevice(
            device_id=value["id"],
            online=value["last_seen_at"] >= datetime.now(UTC) - timedelta(seconds=_ONLINE_SECONDS),
            state=value["state"],
            document_id=value["document_id"],
            capture_session_id=value["capture_session_id"],
        )

    @staticmethod
    def _command(value: RowMapping) -> RecorderCommand:
        return RecorderCommand(
            command_id=value["id"],
            device_id=value["device_id"],
            action=value["action"],
            document_id=value["document_id"],
            status=value["status"],
            safe_error_code=value["safe_error_code"],
        )

    @staticmethod
    def _expire(connection: Connection, device_id: UUID) -> None:
        connection.execute(
            text("""UPDATE recorder_commands SET status='expired',
              safe_error_code='recorder_unavailable',updated_at=now()
              WHERE device_id=:device AND status IN ('pending','running')
                AND expires_at<=now()"""),
            {"device": device_id},
        )

    @staticmethod
    def _authorized_document(
        connection: Connection, context: AuthContext, document_id: UUID
    ) -> UUID:
        row = (
            connection.execute(
                text("""SELECT d.project_id,p.state AS project_state,d.state AS document_state,
                    m.role FROM documents d JOIN projects p ON p.id=d.project_id
                    LEFT JOIN project_memberships m ON m.project_id=d.project_id
                      AND m.user_id=:actor AND m.enabled
                    WHERE d.id=:document AND d.tenant_id=:tenant
                      AND d.workspace_id=:workspace"""),
                {
                    "document": document_id,
                    "actor": context.principal_id,
                    "tenant": context.tenant_id,
                    "workspace": context.workspace_id,
                },
            )
            .mappings()
            .one_or_none()
        )
        if (
            row is None
            or row["role"] is None
            or row["project_state"] != "active"
            or row["document_state"] != "created"
        ):
            raise NOT_FOUND
        if row["role"] not in {"contributor", "project_owner"}:
            raise FORBIDDEN
        return row["project_id"]  # type: ignore[no-any-return]

    @staticmethod
    def _audit(
        connection: Connection,
        context: AuthContext,
        action: str,
        project_id: UUID | None = None,
        document_id: UUID | None = None,
    ) -> None:
        connection.execute(
            text("""INSERT INTO audit_events
              (id,tenant_id,workspace_id,project_id,document_id,actor_kind,actor_id,
               action,outcome,request_id,authorization_epoch,occurred_at)
              VALUES (:id,:tenant,:workspace,:project,:document,'employee',:actor,
                :action,'allowed',:request,:epoch,now())"""),
            {
                "id": uuid4(),
                "tenant": context.tenant_id,
                "workspace": context.workspace_id,
                "project": project_id,
                "document": document_id,
                "actor": context.principal_id,
                "action": action,
                "request": context.request_id,
                "epoch": context.authorization_epoch,
            },
        )

    def heartbeat(
        self,
        context: AuthContext,
        device_id: UUID,
        report: RecorderHeartbeat,
        token: str,
    ) -> RecorderDevice:
        self._employee(context)
        if report.state == "idle" and (report.document_id or report.capture_session_id):
            raise CONFLICT
        with scoped_transaction(self._engine, context) as connection:
            row = (
                connection.execute(
                    text("""INSERT INTO recorder_devices
                  (id,tenant_id,workspace_id,user_id,token_sha256,state,document_id,capture_session_id)
                  VALUES (:id,:tenant,:workspace,:actor,:digest,:state,:document,:capture)
                  ON CONFLICT (id) DO UPDATE SET state=EXCLUDED.state,
                    document_id=EXCLUDED.document_id,
                    capture_session_id=EXCLUDED.capture_session_id,last_seen_at=now()
                  WHERE recorder_devices.tenant_id=EXCLUDED.tenant_id
                    AND recorder_devices.workspace_id=EXCLUDED.workspace_id
                    AND recorder_devices.user_id=EXCLUDED.user_id
                    AND recorder_devices.token_sha256=EXCLUDED.token_sha256
                  RETURNING *"""),
                    {
                        "id": device_id,
                        "tenant": context.tenant_id,
                        "workspace": context.workspace_id,
                        "actor": context.principal_id,
                        "digest": self._token_digest(token),
                        "state": report.state,
                        "document": report.document_id,
                        "capture": report.capture_session_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise NOT_FOUND
            return self._device(row)

    def list_devices(self, context: AuthContext) -> RecorderDevicePage:
        self._employee(context)
        with scoped_transaction(self._engine, context) as connection:
            rows = (
                connection.execute(
                    text("""SELECT * FROM recorder_devices WHERE user_id=:actor
                  ORDER BY last_seen_at DESC,id LIMIT 20"""),
                    {"actor": context.principal_id},
                )
                .mappings()
                .all()
            )
            return RecorderDevicePage(items=[self._device(row) for row in rows])

    def submit(
        self, context: AuthContext, device_id: UUID, request: RecorderCommandCreate
    ) -> RecorderCommand:
        self._employee(context)
        if (request.action == "start") != (request.document_id is not None):
            raise CONFLICT
        with scoped_transaction(self._engine, context) as connection:
            device = (
                connection.execute(
                    text(
                        "SELECT * FROM recorder_devices WHERE id=:id AND user_id=:actor FOR UPDATE"
                    ),
                    {"id": device_id, "actor": context.principal_id},
                )
                .mappings()
                .one_or_none()
            )
            if device is None:
                raise NOT_FOUND
            project_id = None
            if request.action == "start":
                assert request.document_id is not None
                project_id = self._authorized_document(connection, context, request.document_id)
            elif request.action != "stop":
                if device["document_id"] is None:
                    raise CONFLICT
                self._authorized_document(connection, context, device["document_id"])
            existing = (
                connection.execute(
                    text("""SELECT * FROM recorder_commands WHERE user_id=:actor
                  AND operation_key=:key"""),
                    {"actor": context.principal_id, "key": request.operation_key},
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if (
                    existing["device_id"] != device_id
                    or existing["action"] != request.action
                    or existing["document_id"] != request.document_id
                ):
                    raise CONFLICT
                return self._command(existing)
            self._expire(connection, device_id)
            if self._device(device).online is False:
                raise CONFLICT
            expected = {
                "start": {"idle", "finalizing", "uploading", "complete", "failed", "aborted"},
                "pause": {"recording"},
                "resume": {"paused"},
                "stop": {"recording", "paused", "interrupted"},
            }
            if device["state"] not in expected[request.action]:
                raise CONFLICT
            open_command = connection.execute(
                text("""SELECT id FROM recorder_commands WHERE device_id=:device
                  AND status IN ('pending','running')"""),
                {"device": device_id},
            ).scalar_one_or_none()
            if open_command is not None:
                raise CONFLICT
            row = (
                connection.execute(
                    text("""INSERT INTO recorder_commands
                  (id,tenant_id,workspace_id,user_id,device_id,document_id,project_id,
                   capture_session_id,action,status,operation_key,expires_at)
                  VALUES (:id,:tenant,:workspace,:actor,:device,:document,:project,
                    :capture,:action,'pending',:key,now()+interval '2 minutes')
                  RETURNING *"""),
                    {
                        "id": uuid4(),
                        "tenant": context.tenant_id,
                        "workspace": context.workspace_id,
                        "actor": context.principal_id,
                        "device": device_id,
                        "document": request.document_id,
                        "project": project_id,
                        "capture": device["capture_session_id"],
                        "action": request.action,
                        "key": request.operation_key,
                    },
                )
                .mappings()
                .one()
            )
            self._audit(
                connection,
                context,
                f"recorder.command.{request.action}",
                project_id,
                request.document_id,
            )
            return self._command(row)

    def poll(self, context: AuthContext, device_id: UUID, token: str) -> RecorderCommandPoll:
        self._employee(context)
        with scoped_transaction(self._engine, context) as connection:
            device = (
                connection.execute(
                    text("""SELECT id,document_id FROM recorder_devices
                  WHERE id=:id AND user_id=:actor AND token_sha256=:digest"""),
                    {
                        "id": device_id,
                        "actor": context.principal_id,
                        "digest": self._token_digest(token),
                    },
                )
                .mappings()
                .one_or_none()
            )
            if device is None:
                raise NOT_FOUND
            self._expire(connection, device_id)
            row = (
                connection.execute(
                    text("""SELECT * FROM recorder_commands WHERE device_id=:device
                  AND status='pending' ORDER BY created_at,id LIMIT 1 FOR UPDATE"""),
                    {"device": device_id},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return RecorderCommandPoll(command=None)
            if row["action"] != "stop":
                document_id = (
                    row["document_id"] if row["action"] == "start" else device["document_id"]
                )
                try:
                    if document_id is None:
                        raise NOT_FOUND
                    self._authorized_document(connection, context, document_id)
                except DomainError:
                    connection.execute(
                        text("""UPDATE recorder_commands SET status='failed',
                          safe_error_code='permission_revoked',updated_at=now()
                          WHERE id=:id"""),
                        {"id": row["id"]},
                    )
                    self._audit(connection, context, "recorder.command.failed")
                    return RecorderCommandPoll(command=None)
            claimed = (
                connection.execute(
                    text("""UPDATE recorder_commands SET status='running',updated_at=now()
                  WHERE id=:id RETURNING *"""),
                    {"id": row["id"]},
                )
                .mappings()
                .one()
            )
            return RecorderCommandPoll(command=self._command(claimed))

    def get_command(self, context: AuthContext, command_id: UUID) -> RecorderCommand:
        self._employee(context)
        with scoped_transaction(self._engine, context) as connection:
            row = (
                connection.execute(
                    text("SELECT * FROM recorder_commands WHERE id=:id AND user_id=:actor"),
                    {"id": command_id, "actor": context.principal_id},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise NOT_FOUND
            self._expire(connection, row["device_id"])
            updated = (
                connection.execute(
                    text("SELECT * FROM recorder_commands WHERE id=:id"),
                    {"id": command_id},
                )
                .mappings()
                .one()
            )
            return self._command(updated)

    def complete(
        self,
        context: AuthContext,
        command_id: UUID,
        result: RecorderCommandResult,
        token: str,
    ) -> RecorderCommand:
        self._employee(context)
        if (result.status == "completed") != (result.safe_error_code is None):
            raise CONFLICT
        if result.status == "completed" and result.capture_session_id is None:
            raise CONFLICT
        with scoped_transaction(self._engine, context) as connection:
            row = (
                connection.execute(
                    text("""SELECT c.* FROM recorder_commands c JOIN recorder_devices d
                  ON d.id=c.device_id WHERE c.id=:id AND c.user_id=:actor
                    AND d.token_sha256=:digest FOR UPDATE OF c"""),
                    {
                        "id": command_id,
                        "actor": context.principal_id,
                        "digest": self._token_digest(token),
                    },
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise NOT_FOUND
            if row["status"] in {"completed", "failed"}:
                if (
                    row["status"] != result.status
                    or row["safe_error_code"] != result.safe_error_code
                ):
                    raise CONFLICT
                return self._command(row)
            if row["status"] != "running" or row["expires_at"] <= datetime.now(UTC):
                raise CONFLICT
            if result.status == "completed":
                capture = (
                    connection.execute(
                        text("""SELECT state,document_id,created_by FROM capture_sessions
                      WHERE id=:capture AND tenant_id=:tenant AND workspace_id=:workspace"""),
                        {
                            "capture": result.capture_session_id,
                            "tenant": context.tenant_id,
                            "workspace": context.workspace_id,
                        },
                    )
                    .mappings()
                    .one_or_none()
                )
                expected_states = {
                    "start": {"recording"},
                    "pause": {"paused"},
                    "resume": {"recording"},
                    "stop": {"finalizing", "uploading", "complete"},
                }
                if (
                    capture is None
                    or capture["created_by"] != context.principal_id
                    or capture["state"] not in expected_states[row["action"]]
                    or (row["action"] == "start" and capture["document_id"] != row["document_id"])
                    or (
                        row["action"] != "start"
                        and result.capture_session_id != row["capture_session_id"]
                    )
                ):
                    raise CONFLICT
            updated = (
                connection.execute(
                    text("""UPDATE recorder_commands SET status=:status,
                  safe_error_code=:error,updated_at=now() WHERE id=:id RETURNING *"""),
                    {"id": command_id, "status": result.status, "error": result.safe_error_code},
                )
                .mappings()
                .one()
            )
            self._audit(connection, context, f"recorder.command.{result.status}")
            return self._command(updated)
