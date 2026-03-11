"""Custom exception classes for error handling."""

from typing import Any, Dict, Optional


class AppError(Exception):
    """Base exception class for application errors."""
    
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize application error.
        
        Args:
            message: Human-readable error message
            status_code: HTTP status code
            error_code: Machine-readable error code
            details: Additional error details
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for API response."""
        return {
            "error": {
                "code": self.error_code,
                "message": self.message,
                "details": self.details
            }
        }


class AuthenticationError(AppError):
    """Exception raised for authentication failures."""
    
    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=401,
            error_code="AUTHENTICATION_FAILED",
            details=details
        )


class AuthorizationError(AppError):
    """Exception raised for authorization failures."""
    
    def __init__(self, message: str = "Insufficient permissions", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=403,
            error_code="AUTHORIZATION_FAILED",
            details=details
        )


class ValidationError(AppError):
    """Exception raised for input validation failures."""
    
    def __init__(self, message: str, field: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        error_details = details or {}
        if field:
            error_details["field"] = field
        
        super().__init__(
            message=message,
            status_code=400,
            error_code="VALIDATION_ERROR",
            details=error_details
        )


class ExternalAPIError(AppError):
    """Exception raised for external API failures."""
    
    def __init__(
        self,
        message: str,
        api_name: str,
        status_code: int = 502,
        details: Optional[Dict[str, Any]] = None
    ):
        error_details = details or {}
        error_details["api_name"] = api_name
        
        super().__init__(
            message=message,
            status_code=status_code,
            error_code="EXTERNAL_API_ERROR",
            details=error_details
        )


class ProcessingError(AppError):
    """Exception raised for processing failures."""
    
    def __init__(
        self,
        message: str,
        processing_type: str,
        details: Optional[Dict[str, Any]] = None
    ):
        error_details = details or {}
        error_details["processing_type"] = processing_type
        
        super().__init__(
            message=message,
            status_code=500,
            error_code="PROCESSING_ERROR",
            details=error_details
        )


class DataError(AppError):
    """Exception raised for data-related failures."""
    
    def __init__(
        self,
        message: str,
        data_source: str,
        details: Optional[Dict[str, Any]] = None
    ):
        error_details = details or {}
        error_details["data_source"] = data_source
        
        super().__init__(
            message=message,
            status_code=500,
            error_code="DATA_ERROR",
            details=error_details
        )


class TenantIsolationError(AppError):
    """Exception raised for tenant isolation violations."""
    
    def __init__(
        self,
        message: str = "Cross-tenant access attempt detected",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=403,
            error_code="TENANT_ISOLATION_VIOLATION",
            details=details
        )
