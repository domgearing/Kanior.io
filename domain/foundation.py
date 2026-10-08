"""Authorized PostgreSQL services for Phase 1 foundation resources."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from api.database import scoped_transaction
from contracts.models import (
    AuthContext,
    Document,
    DocumentCreate,
    DocumentPage,
    MemberPage,
    Membership,
    MembershipByEmailPut,
    MembershipPut,
    MemberSummary,
    MeResponse,
    ProfileUpdate,
    Project,
    ProjectCreate,
    ProjectPage,
)
from domain.errors import CONFLICT, FORBIDDEN, NOT_FOUND


def _project(row: object) -> Project:
    value = row  # typing stays at the SQL boundary
    return Project(
        project_id=value["id"],  # type: ignore[index]
        tenant_id=value["tenant_id"],  # type: ignore[index]
        workspace_id=value["workspace_id"],  # type: ignore[index]
        name=value["name"],  # type: ignore[index]
        owner_user_id=value["owner_user_id"],  # type: ignore[index]
        my_role=value["my_role"],  # type: ignore[index]
        authorization_epoch=value["authorization_epoch"],  # type: ignore[index]
        state="active",
        created_at=value["created_at"],  # type: ignore[index]
        updated_at=value["updated_at"],  # type: ignore[index]
    )


def _document(row: object) -> Document:
    value = row
    return Document(
        document_id=value["id"],  # type: ignore[index]
        tenant_id=value["tenant_id"],  # type: ignore[index]
        workspace_id=value["workspace_id"],  # type: ignore[index]
        project_id=value["project_id"],  # type: ignore[index]
        title=value["title"],  # type: ignore[index]
        meeting_date=value["meeting_date"],  # type: ignore[index]
        language=value["language"],  # type: ignore[index]
        created_by=value["created_by"],  # type: ignore[index]
        consent_policy_version=value["consent_policy_version"],  # type: ignore[index]
        consent_acknowledged_by=value["consent_acknowledged_by"],  # type: ignore[index]
        consent_acknowledged_at=value["consent_acknowledged_at"],  # type: ignore[index]
        state="created",
        created_at=value["created_at"],  # type: ignore[index]
        updated_at=value["updated_at"],  # type: ignore[index]
    )


class FoundationService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_me(self, context: AuthContext, csrf_token: str) -> MeResponse:
        with scoped_transaction(self._engine, context) as connection:
            row = (
                connection.execute(
                    text("SELECT display_name,email FROM users WHERE id=:id AND enabled"),
                    {"id": context.principal_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise NOT_FOUND
        return MeResponse(
            user_id=context.principal_id,
            tenant_id=context.tenant_id,
            workspace_id=context.workspace_id,
            display_name=row["display_name"],
            email=row["email"],
            capabilities=context.capabilities,
            csrf_token=csrf_token,
        )

    def update_me(
        self, context: AuthContext, csrf_token: str, request: ProfileUpdate
    ) -> MeResponse:
        with scoped_transaction(self._engine, context) as connection:
            updated = connection.execute(
                text(
                    """UPDATE users SET display_name=:display_name,updated_at=now()
                    WHERE id=:id AND enabled RETURNING id"""
                ),
                {"display_name": request.display_name, "id": context.principal_id},
            ).scalar_one_or_none()
            if updated is None:
                raise NOT_FOUND
        return self.get_me(context, csrf_token)

    def _audit(
        self,
        connection: object,
        context: AuthContext,
        action: str,
        *,
        project_id: UUID | None = None,
        document_id: UUID | None = None,
    ) -> None:
        connection.execute(  # type: ignore[attr-defined]
            text(
                """INSERT INTO audit_events
                (id,tenant_id,workspace_id,project_id,document_id,actor_kind,actor_id,
                 action,outcome,request_id,authorization_epoch,occurred_at)
                VALUES (:id,:tenant,:workspace,:project,:document,:kind,:actor,
                  :action,'allowed',:request,:epoch,:now)"""
            ),
            {
                "id": uuid4(),
                "tenant": context.tenant_id,
                "workspace": context.workspace_id,
                "project": project_id,
                "document": document_id,
                "kind": context.principal_kind,
                "actor": context.principal_id,
                "action": action,
                "request": context.request_id,
                "epoch": context.authorization_epoch,
                "now": datetime.now(UTC),
            },
        )

    def list_projects(self, context: AuthContext, limit: int) -> ProjectPage:
        with scoped_transaction(self._engine, context) as connection:
            rows = connection.execute(
                text(
                    """SELECT p.*,m.role AS my_role FROM projects p
                    JOIN project_memberships m ON m.project_id=p.id
                      AND m.user_id=:user AND m.enabled
                    WHERE p.state='active' ORDER BY p.created_at,p.id LIMIT :limit"""
                ),
                {"limit": limit, "user": context.principal_id},
            ).mappings()
            return ProjectPage(items=[_project(row) for row in rows], next_cursor=None)

    def get_project(self, context: AuthContext, project_id: UUID) -> Project:
        with scoped_transaction(self._engine, context, project_id) as connection:
            row = (
                connection.execute(
                    text(
                        """SELECT p.*,m.role AS my_role FROM projects p
                        JOIN project_memberships m ON m.project_id=p.id
                          AND m.user_id=:user AND m.enabled
                        WHERE p.id=:id AND p.state='active'"""
                    ),
                    {"id": project_id, "user": context.principal_id},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise NOT_FOUND
            return _project(row)

    def create_project(self, context: AuthContext, request: ProjectCreate) -> Project:
        if "projects:create" not in context.capabilities:
            raise FORBIDDEN
        project_id, membership_id = uuid4(), uuid4()
        with scoped_transaction(self._engine, context, project_id) as connection:
            connection.execute(
                text(
                    """INSERT INTO projects
                    (id,tenant_id,workspace_id,name,owner_user_id,retention_policy_ref,
                     transcript_approval_policy_ref)
                    VALUES (:id,:tenant,:workspace,:name,:owner,'synthetic-retention-open',
                            'controlled-cleanup-v2')"""
                ),
                {
                    "id": project_id,
                    "tenant": context.tenant_id,
                    "workspace": context.workspace_id,
                    "name": request.name,
                    "owner": context.principal_id,
                },
            )
            self._audit(connection, context, "project.created", project_id=project_id)
            connection.execute(
                text(
                    """INSERT INTO project_memberships
                    (id,tenant_id,workspace_id,project_id,user_id,role,enabled)
                    VALUES (:id,:tenant,:workspace,:project,:user,'project_owner',true)"""
                ),
                {
                    "id": membership_id,
                    "tenant": context.tenant_id,
                    "workspace": context.workspace_id,
                    "project": project_id,
                    "user": context.principal_id,
                },
            )
            row = (
                connection.execute(
                    text(
                        "SELECT p.*,'project_owner'::text AS my_role FROM projects p WHERE id=:id"
                    ),
                    {"id": project_id},
                )
                .mappings()
                .one()
            )
            return _project(row)

    def _require_owner(self, connection: object, context: AuthContext, project_id: UUID) -> None:
        row = connection.execute(  # type: ignore[attr-defined]
            text(
                """SELECT role FROM project_memberships
                WHERE project_id=:project AND user_id=:user AND enabled"""
            ),
            {"project": project_id, "user": context.principal_id},
        ).scalar_one_or_none()
        if row != "project_owner":
            raise FORBIDDEN

    def get_membership(self, context: AuthContext, project_id: UUID, user_id: UUID) -> Membership:
        with scoped_transaction(self._engine, context, project_id) as connection:
            self._require_owner(connection, context, project_id)
            row = (
                connection.execute(
                    text(
                        """SELECT m.*,p.authorization_epoch project_authorization_epoch
                    FROM project_memberships m JOIN projects p ON p.id=m.project_id
                    WHERE m.project_id=:project AND m.user_id=:user"""
                    ),
                    {"project": project_id, "user": user_id},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise NOT_FOUND
            return Membership(
                project_membership_id=row["id"],
                tenant_id=row["tenant_id"],
                workspace_id=row["workspace_id"],
                project_id=row["project_id"],
                user_id=row["user_id"],
                role=row["role"],
                enabled=row["enabled"],
                revision=row["revision"],
                project_authorization_epoch=row["project_authorization_epoch"],
            )

    def list_members(self, context: AuthContext, project_id: UUID) -> MemberPage:
        with scoped_transaction(self._engine, context, project_id) as connection:
            self._require_owner(connection, context, project_id)
            rows = connection.execute(
                text(
                    """SELECT u.id AS user_id,u.display_name,u.email,m.role,m.enabled,m.revision
                    FROM project_memberships m JOIN users u ON u.id=m.user_id
                    WHERE m.project_id=:project ORDER BY u.display_name,u.id LIMIT 100"""
                ),
                {"project": project_id},
            ).mappings()
            return MemberPage(
                items=[
                    MemberSummary(
                        user_id=row["user_id"],
                        display_name=row["display_name"],
                        email=row["email"],
                        role=row["role"],
                        enabled=row["enabled"],
                        revision=row["revision"],
                    )
                    for row in rows
                ]
            )

    def set_membership_by_email(
        self, context: AuthContext, project_id: UUID, request: MembershipByEmailPut
    ) -> Membership:
        with scoped_transaction(self._engine, context, project_id) as connection:
            self._require_owner(connection, context, project_id)
            normalized = request.email.strip().casefold()
            user_id = connection.execute(
                text(
                    """SELECT id FROM users
                    WHERE lower(email)=:email AND enabled
                    LIMIT 1"""
                ),
                {"email": normalized},
            ).scalar_one_or_none()
        if user_id is None:
            raise NOT_FOUND
        return self.set_membership(
            context,
            project_id,
            user_id,
            MembershipPut(
                role=request.role,
                enabled=request.enabled,
                expected_revision=request.expected_revision,
            ),
        )

    def set_membership(
        self, context: AuthContext, project_id: UUID, user_id: UUID, request: MembershipPut
    ) -> Membership:
        with scoped_transaction(self._engine, context, project_id) as connection:
            self._require_owner(connection, context, project_id)
            project = connection.execute(
                text("SELECT owner_user_id FROM projects WHERE id=:id"), {"id": project_id}
            ).scalar_one_or_none()
            if project is None:
                raise NOT_FOUND
            if user_id == project and (not request.enabled or request.role != "project_owner"):
                raise CONFLICT
            target = connection.execute(
                text("SELECT id FROM users WHERE id=:id AND enabled"), {"id": user_id}
            ).scalar_one_or_none()
            if target is None:
                raise NOT_FOUND
            current = (
                connection.execute(
                    text(
                        """SELECT id,revision FROM project_memberships
                        WHERE project_id=:project AND user_id=:user"""
                    ),
                    {"project": project_id, "user": user_id},
                )
                .mappings()
                .one_or_none()
            )
            if current is None:
                if request.expected_revision != 0:
                    raise CONFLICT
                membership_id, revision = uuid4(), 1
                connection.execute(
                    text("""INSERT INTO project_memberships
                    (id,tenant_id,workspace_id,project_id,user_id,role,enabled,revision)
                    VALUES (:id,:tenant,:workspace,:project,:user,:role,:enabled,1)"""),
                    {
                        "id": membership_id,
                        "tenant": context.tenant_id,
                        "workspace": context.workspace_id,
                        "project": project_id,
                        "user": user_id,
                        "role": request.role,
                        "enabled": request.enabled,
                    },
                )
            else:
                if current["revision"] != request.expected_revision:
                    raise CONFLICT
                membership_id, revision = current["id"], current["revision"] + 1
                connection.execute(
                    text("""UPDATE project_memberships SET role=:role,enabled=:enabled,
                    revision=:revision,updated_at=now() WHERE id=:id"""),
                    {
                        "role": request.role,
                        "enabled": request.enabled,
                        "revision": revision,
                        "id": membership_id,
                    },
                )
            epoch = connection.execute(
                text(
                    """UPDATE projects SET authorization_epoch=authorization_epoch+1,
                    updated_at=now()
                    WHERE id=:id RETURNING authorization_epoch"""
                ),
                {"id": project_id},
            ).scalar_one()
            event_id = uuid4()
            connection.execute(
                text("""INSERT INTO outbox_events
                (id,tenant_id,workspace_id,project_id,aggregate_id,event_type,schema_version,payload)
                VALUES (:id,:tenant,:workspace,:project,:project,'access.changed',1,
                jsonb_build_object('project_membership_id',:membership,'user_id',:user,
                  'membership_revision',:revision,'authorization_epoch',:epoch))"""),
                {
                    "id": event_id,
                    "tenant": context.tenant_id,
                    "workspace": context.workspace_id,
                    "project": project_id,
                    "membership": membership_id,
                    "user": user_id,
                    "revision": revision,
                    "epoch": epoch,
                },
            )
            self._audit(connection, context, "membership.changed", project_id=project_id)
            return Membership(
                project_membership_id=membership_id,
                tenant_id=context.tenant_id,
                workspace_id=context.workspace_id,
                project_id=project_id,
                user_id=user_id,
                role=request.role,
                enabled=request.enabled,
                revision=revision,
                project_authorization_epoch=epoch,
            )

    def list_documents(self, context: AuthContext, project_id: UUID, limit: int) -> DocumentPage:
        with scoped_transaction(self._engine, context, project_id) as connection:
            rows = connection.execute(
                text(
                    """SELECT * FROM documents WHERE project_id=:project AND state='created'
                    ORDER BY created_at,id LIMIT :limit"""
                ),
                {"project": project_id, "limit": limit},
            ).mappings()
            return DocumentPage(items=[_document(row) for row in rows], next_cursor=None)

    def create_document(
        self, context: AuthContext, project_id: UUID, request: DocumentCreate
    ) -> Document:
        document_id, now = uuid4(), datetime.now(UTC)
        with scoped_transaction(self._engine, context, project_id) as connection:
            role = connection.execute(
                text(
                    """SELECT role FROM project_memberships
                    WHERE project_id=:project AND user_id=:user AND enabled"""
                ),
                {"project": project_id, "user": context.principal_id},
            ).scalar_one_or_none()
            if role not in {"contributor", "project_owner"}:
                raise FORBIDDEN
            connection.execute(
                text("""INSERT INTO documents
                (id,tenant_id,workspace_id,project_id,title,meeting_date,language,created_by,
                 consent_policy_version,consent_acknowledged_by,consent_acknowledged_at)
                VALUES (:id,:tenant,:workspace,:project,:title,:meeting,:language,:actor,
                        :policy,:actor,:now)"""),
                {
                    "id": document_id,
                    "tenant": context.tenant_id,
                    "workspace": context.workspace_id,
                    "project": project_id,
                    "title": request.title,
                    "meeting": request.meeting_date,
                    "language": request.language,
                    "actor": context.principal_id,
                    "policy": request.consent_policy_version,
                    "now": now,
                },
            )
            self._audit(
                connection,
                context,
                "document.created",
                project_id=project_id,
                document_id=document_id,
            )
            row = (
                connection.execute(
                    text("SELECT * FROM documents WHERE id=:id"), {"id": document_id}
                )
                .mappings()
                .one()
            )
            return _document(row)

    def get_document(self, context: AuthContext, document_id: UUID) -> Document:
        # Resolve within tenant/workspace first without exposing metadata; project
        # RLS still requires an authorized project context, so use a scoped lookup.
        with scoped_transaction(self._engine, context) as connection:
            project_id = connection.execute(
                text("SELECT project_id FROM documents WHERE id=:id"), {"id": document_id}
            ).scalar_one_or_none()
        if project_id is None:
            raise NOT_FOUND
        with scoped_transaction(self._engine, context, project_id) as connection:
            row = (
                connection.execute(
                    text("SELECT * FROM documents WHERE id=:id"), {"id": document_id}
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise NOT_FOUND
            return _document(row)
