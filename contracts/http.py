"""Editable operation registry; contains no handlers or running server."""

from dataclasses import dataclass

from pydantic import BaseModel

from contracts import models as m


@dataclass(frozen=True)
class Operation:
    method: str
    path: str
    operation_id: str
    response: type[BaseModel]
    summary: str
    request: type[BaseModel] | None = None
    success: int = 200
    paginated: bool = False


OPERATIONS = (
    Operation("get", "/me", "get_me", m.MeResponse, "Resolve current enabled employee"),
    Operation(
        "get",
        "/projects",
        "list_projects",
        m.ProjectPage,
        "List permitted projects",
        paginated=True,
    ),
    Operation(
        "post",
        "/projects",
        "create_project",
        m.Project,
        "Create project and creator owner membership",
        m.ProjectCreate,
        201,
    ),
    Operation("get", "/projects/{project_id}", "get_project", m.Project, "Read permitted project"),
    Operation(
        "get",
        "/projects/{project_id}/members/{user_id}",
        "get_project_member",
        m.Membership,
        "Owner reads current membership revision",
    ),
    Operation(
        "put",
        "/projects/{project_id}/members/{user_id}",
        "set_project_member",
        m.Membership,
        "Owner changes membership using revision CAS",
        m.MembershipPut,
    ),
    Operation(
        "get",
        "/projects/{project_id}/documents",
        "list_documents",
        m.DocumentPage,
        "List permitted document metadata",
        paginated=True,
    ),
    Operation(
        "post",
        "/projects/{project_id}/documents",
        "create_document",
        m.Document,
        "Contributor creates document metadata with consent",
        m.DocumentCreate,
        201,
    ),
    Operation(
        "get",
        "/documents/{document_id}",
        "get_document",
        m.Document,
        "Read permitted document metadata",
    ),
)
