"""Thin FastAPI routes for the published foundation-v1 contract."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from api.auth import AuthSession, require_csrf, resolve_session
from contracts.models import (
    Document,
    DocumentCreate,
    DocumentPage,
    MemberPage,
    Membership,
    MembershipByEmailPut,
    MembershipPut,
    MeResponse,
    ProfileUpdate,
    Project,
    ProjectCreate,
    ProjectPage,
)
from domain.foundation import FoundationService

SessionDep = Annotated[AuthSession, Depends(resolve_session)]
CsrfSessionDep = Annotated[AuthSession, Depends(require_csrf)]


def create_foundation_router(service: FoundationService) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/me", response_model=MeResponse, operation_id="get_me")
    def get_me(session: SessionDep) -> MeResponse:
        return service.get_me(session.context, session.csrf_token)

    @router.patch("/me", response_model=MeResponse, operation_id="update_me")
    def update_me(request: ProfileUpdate, session: CsrfSessionDep) -> MeResponse:
        return service.update_me(session.context, session.csrf_token, request)

    @router.get("/projects", response_model=ProjectPage, operation_id="list_projects")
    def list_projects(
        session: SessionDep,
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = None,
    ) -> ProjectPage:
        del cursor
        return service.list_projects(session.context, limit)

    @router.post(
        "/projects", response_model=Project, status_code=201, operation_id="create_project"
    )
    def create_project(
        request: ProjectCreate,
        response: Response,
        session: CsrfSessionDep,
    ) -> Project:
        project = service.create_project(session.context, request)
        response.headers["Location"] = f"/api/v1/projects/{project.project_id}"
        return project

    @router.get("/projects/{project_id}", response_model=Project, operation_id="get_project")
    def get_project(project_id: UUID, session: SessionDep) -> Project:
        return service.get_project(session.context, project_id)

    @router.get(
        "/projects/{project_id}/members",
        response_model=MemberPage,
        operation_id="list_project_members",
    )
    def list_project_members(project_id: UUID, session: SessionDep) -> MemberPage:
        return service.list_members(session.context, project_id)

    @router.put(
        "/projects/{project_id}/members/by-email",
        response_model=Membership,
        operation_id="set_project_member_by_email",
    )
    def set_project_member_by_email(
        project_id: UUID,
        request: MembershipByEmailPut,
        session: CsrfSessionDep,
    ) -> Membership:
        return service.set_membership_by_email(session.context, project_id, request)

    @router.put(
        "/projects/{project_id}/members/{user_id}",
        response_model=Membership,
        operation_id="set_project_member",
    )
    def set_project_member(
        project_id: UUID,
        user_id: UUID,
        request: MembershipPut,
        session: CsrfSessionDep,
    ) -> Membership:
        return service.set_membership(session.context, project_id, user_id, request)

    @router.get(
        "/projects/{project_id}/members/{user_id}",
        response_model=Membership,
        operation_id="get_project_member",
    )
    def get_project_member(project_id: UUID, user_id: UUID, session: SessionDep) -> Membership:
        return service.get_membership(session.context, project_id, user_id)

    @router.get(
        "/projects/{project_id}/documents",
        response_model=DocumentPage,
        operation_id="list_documents",
    )
    def list_documents(
        project_id: UUID,
        session: SessionDep,
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = None,
    ) -> DocumentPage:
        del cursor
        return service.list_documents(session.context, project_id, limit)

    @router.post(
        "/projects/{project_id}/documents",
        response_model=Document,
        status_code=201,
        operation_id="create_document",
    )
    def create_document(
        project_id: UUID,
        request: DocumentCreate,
        response: Response,
        session: CsrfSessionDep,
    ) -> Document:
        document = service.create_document(session.context, project_id, request)
        response.headers["Location"] = f"/api/v1/documents/{document.document_id}"
        return document

    @router.get("/documents/{document_id}", response_model=Document, operation_id="get_document")
    def get_document(document_id: UUID, session: SessionDep) -> Document:
        return service.get_document(session.context, document_id)

    return router
