"""Shared utilities for AI SW Program Manager."""

from .logger import get_logger, log_error, log_api_request
from .errors import (
    AppError,
    AuthenticationError,
    AuthorizationError,
    ValidationError,
    ExternalAPIError,
    ProcessingError,
    DataError,
)
from .decorators import (
    with_logging,
    with_error_handling,
    with_tenant_isolation,
    with_audit_logging,
)
from .validators import validate_tenant_id, validate_uuid, validate_email
from .constants import (
    ROLE_ADMIN,
    ROLE_PROGRAM_MANAGER,
    ROLE_EXECUTIVE,
    ROLE_TEAM_MEMBER,
    RAG_STATUS_GREEN,
    RAG_STATUS_AMBER,
    RAG_STATUS_RED,
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
