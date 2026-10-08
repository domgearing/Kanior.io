"""Safe domain failures shared by API service boundaries."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DomainError(Exception):
    code: str
    status_code: int
    message: str
    retryable: bool = False


NOT_FOUND = DomainError("not_found", 404, "The requested resource was not found.")
FORBIDDEN = DomainError("forbidden", 403, "The requested action is not permitted.")
CONFLICT = DomainError("conflict", 409, "The resource changed or conflicts with this request.")
