"""Shared utilities for AI SW Program Manager."""

from .constants import (
    RAG_STATUS_AMBER,
    RAG_STATUS_GREEN,
    RAG_STATUS_RED,
    ROLE_ADMIN,
    ROLE_EXECUTIVE,
    ROLE_PROGRAM_MANAGER,
    ROLE_TEAM_MEMBER,
)
from .decorators import (
    with_audit_logging,
    with_error_handling,
    with_logging,
    with_tenant_isolation,
)
from .errors import (
    AppError,
    AuthenticationError,
    AuthorizationError,
    DataError,
    ExternalAPIError,
    ProcessingError,
    ValidationError,
)

__all__ = [
    "get_logger",
    "log_error",
    "log_api_request",
    "AppError",
    "AuthenticationError",
    "AuthorizationError",
    "ValidationError",
    "ExternalAPIError",
    "ProcessingError",
    "DataError",
    "with_logging",
    "with_error_handling",
    "with_tenant_isolation",
    "with_audit_logging",
    "validate_tenant_id",
    "validate_uuid",
    "validate_email",
    "ROLE_ADMIN",
    "ROLE_PROGRAM_MANAGER",
    "ROLE_EXECUTIVE",
    "ROLE_TEAM_MEMBER",
    "RAG_STATUS_GREEN",
    "RAG_STATUS_AMBER",
    "RAG_STATUS_RED",
]
