"""Input validation utilities."""

import re
import uuid
from typing import Any, Optional
from .errors import ValidationError


def validate_tenant_id(tenant_id: Any) -> str:
    """
    Validate tenant ID format.
    
    Args:
        tenant_id: Tenant ID to validate
        
    Returns:
        Validated tenant ID string
        
    Raises:
        ValidationError: If tenant ID is invalid
    """
    if not tenant_id:
        raise ValidationError("Tenant ID is required", field="tenantId")
    
    tenant_id_str = str(tenant_id)
    
    try:
        uuid.UUID(tenant_id_str)
    except ValueError:
        raise ValidationError("Invalid tenant ID format", field="tenantId")
    
    return tenant_id_str


def validate_uuid(value: Any, field_name: str) -> str:
    """
    Validate UUID format.
    
    Args:
        value: Value to validate
        field_name: Name of the field for error messages
        
    Returns:
        Validated UUID string
        
    Raises:
        ValidationError: If UUID is invalid
    """
    if not value:
        raise ValidationError(f"{field_name} is required", field=field_name)
    
    value_str = str(value)
    
    try:
        uuid.UUID(value_str)
    except ValueError:
        raise ValidationError(f"Invalid {field_name} format", field=field_name)
    
    return value_str


def validate_email(email: Any) -> str:
    """
    Validate email format.
    
    Args:
        email: Email to validate
        
    Returns:
        Validated email string
        
    Raises:
        ValidationError: If email is invalid
    """
    if not email:
        raise ValidationError("Email is required", field="email")
    
    email_str = str(email).strip()
    
    # Basic email regex pattern
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(email_pattern, email_str):
        raise ValidationError("Invalid email format", field="email")
    
    return email_str


def validate_role(role: Any, allowed_roles: Optional[list] = None) -> str:
    """
    Validate user role.
    
    Args:
        role: Role to validate
        allowed_roles: List of allowed roles
        
    Returns:
        Validated role string
        
    Raises:
        ValidationError: If role is invalid
    """
    if not role:
        raise ValidationError("Role is required", field="role")
    
    role_str = str(role).upper()
    
    if allowed_roles is None:
        from .constants import VALID_ROLES
        allowed_roles = VALID_ROLES
    
    if role_str not in allowed_roles:
        raise ValidationError(
            f"Invalid role. Must be one of: {', '.join(allowed_roles)}",
            field="role"
        )
    
    return role_str


def validate_file_format(filename: str, allowed_formats: list) -> str:
    """
    Validate file format.
    
    Validates: Property 11 - File Format Validation
    
    Args:
        filename: Filename to validate
        allowed_formats: List of allowed file extensions (e.g., ['.pdf', '.docx'])
        
    Returns:
        Validated filename
        
    Raises:
        ValidationError: If file format is not allowed
    """
    if not filename:
        raise ValidationError("Filename is required", field="filename")
    
    filename_lower = filename.lower()
    
    if not any(filename_lower.endswith(fmt) for fmt in allowed_formats):
        raise ValidationError(
            f"Invalid file format. Allowed formats: {', '.join(allowed_formats)}",
            field="filename"
        )
    
    return filename


def validate_file_size(file_size: int, max_size_mb: int = 50) -> int:
    """
    Validate file size.
    
    Args:
        file_size: File size in bytes
        max_size_mb: Maximum allowed size in MB
        
    Returns:
        Validated file size
        
    Raises:
        ValidationError: If file size exceeds limit
    """
    max_size_bytes = max_size_mb * 1024 * 1024
    
    if file_size > max_size_bytes:
        raise ValidationError(
            f"File size exceeds maximum allowed size of {max_size_mb}MB",
            field="fileSize"
        )
    
    return file_size


def validate_required_fields(data: dict, required_fields: list, parent_field: Optional[str] = None) -> None:
    """
    Validate that all required fields are present.
    
    Args:
        data: Data dictionary to validate
        required_fields: List of required field names
        parent_field: Optional parent field name for nested validation
        
    Raises:
        ValidationError: If any required field is missing
    """
    missing_fields = [field for field in required_fields if field not in data or data[field] is None]
    
    if missing_fields:
        field_path = f"{parent_field}." if parent_field else ""
        raise ValidationError(
            f"Missing required fields: {', '.join([field_path + f for f in missing_fields])}",
            details={"missing_fields": missing_fields}
        )


def validate_url(url: Any, field_name: str = "url") -> str:
    """
    Validate URL format.
    
    Args:
        url: URL to validate
        field_name: Name of the field for error messages
        
    Returns:
        Validated URL string
        
    Raises:
        ValidationError: If URL is invalid
    """
    if not url:
        raise ValidationError(f"{field_name} is required", field=field_name)
    
    url_str = str(url).strip()
    
    # Basic URL validation pattern
    url_pattern = r'^https?://[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*(/.*)?$'
    
    if not re.match(url_pattern, url_str):
        raise ValidationError(f"Invalid {field_name} format", field=field_name)
    
    return url_str


def validate_date_range(start_date: str, end_date: str) -> tuple:
    """
    Validate date range.
    
    Args:
        start_date: Start date in ISO format
        end_date: End date in ISO format
        
    Returns:
        Tuple of (start_date, end_date)
        
    Raises:
        ValidationError: If date range is invalid
    """
    from datetime import datetime
    
    try:
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    except ValueError as e:
        raise ValidationError(f"Invalid date format: {str(e)}")
    
    if start > end:
        raise ValidationError("Start date must be before end date")
    
    return (start_date, end_date)
