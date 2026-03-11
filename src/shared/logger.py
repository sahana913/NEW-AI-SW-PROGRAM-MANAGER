"""Logging utilities for structured JSON logging."""

import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from aws_lambda_powertools import Logger

# Initialize AWS Lambda Powertools logger
logger = Logger(service="ai-sw-program-manager")


def get_logger(service_name: str = "ai-sw-program-manager") -> Logger:
    """
    Get a configured logger instance.
    
    Args:
        service_name: Name of the service for logging context
        
    Returns:
        Configured Logger instance
    """
    return Logger(service=service_name)


def log_error(
    logger_instance: Logger,
    error: Exception,
    context: Optional[Dict[str, Any]] = None,
    severity: str = "ERROR"
) -> None:
    """
    Log an error with structured context and stack trace.
    
    Validates: Property 64 - Error Logging Completeness
    Validates: Requirement 27.1 - Log all errors with severity, timestamp, context
    
    Args:
        logger_instance: Logger instance to use
        error: Exception that occurred
        context: Additional context information
        severity: Error severity level
    """
    import traceback
    
    error_data = {
        "severity": severity,
        "timestamp": datetime.utcnow().isoformat(),
        "error_type": type(error).__name__,
        "error_message": str(error),
        "stack_trace": traceback.format_exc(),
        "context": context or {}
    }
    
    logger_instance.error(
        "Error occurred",
        extra=error_data
    )


def log_api_request(
    logger_instance: Logger,
    request_id: str,
    user_id: str,
    tenant_id: str,
    endpoint: str,
    method: str,
    response_time_ms: float,
    status_code: int,
    error: Optional[str] = None
) -> None:
    """
    Log an API request with all required metadata.
    
    Validates: Property 65 - API Request Logging
    
    Args:
        logger_instance: Logger instance to use
        request_id: Unique request identifier
        user_id: User making the request
        tenant_id: Tenant context
        endpoint: API endpoint called
        method: HTTP method
        response_time_ms: Response time in milliseconds
        status_code: HTTP status code
        error: Error message if request failed
    """
    request_data = {
        "request_id": request_id,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "endpoint": endpoint,
        "method": method,
        "response_time_ms": response_time_ms,
        "status_code": status_code,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if error:
        request_data["error"] = error
        logger_instance.error("API request failed", extra=request_data)
    else:
        logger_instance.info("API request completed", extra=request_data)


def log_authentication_attempt(
    logger_instance: Logger,
    user_id: str,
    email: str,
    success: bool,
    reason: Optional[str] = None
) -> None:
    """
    Log an authentication attempt for audit trail.
    
    Validates: Property 66 - Authentication Audit Logging
    
    Args:
        logger_instance: Logger instance to use
        user_id: User attempting authentication
        email: User email
        success: Whether authentication succeeded
        reason: Failure reason if applicable
    """
    auth_data = {
        "user_id": user_id,
        "email": email,
        "success": success,
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": "authentication_attempt"
    }
    
    if not success and reason:
        auth_data["failure_reason"] = reason
    
    logger_instance.info("Authentication attempt", extra=auth_data)


def log_data_modification(
    logger_instance: Logger,
    user_id: str,
    tenant_id: str,
    operation_type: str,
    entity_type: str,
    entity_id: str,
    changes: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log a data modification operation for audit trail.
    
    Validates: Property 67 - Data Modification Audit Logging
    
    Args:
        logger_instance: Logger instance to use
        user_id: User performing the modification
        tenant_id: Tenant context
        operation_type: Type of operation (CREATE, UPDATE, DELETE)
        entity_type: Type of entity modified
        entity_id: Identifier of modified entity
        changes: Details of changes made
    """
    modification_data = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "operation_type": operation_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": "data_modification"
    }
    
    if changes:
        modification_data["changes"] = changes
    
    logger_instance.info("Data modification", extra=modification_data)


def log_administrative_action(
    logger_instance: Logger,
    admin_user_id: str,
    action_type: str,
    affected_entities: Dict[str, Any],
    details: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log an administrative action for audit trail.
    
    Validates: Property 68 - Administrative Action Audit Logging
    
    Args:
        logger_instance: Logger instance to use
        admin_user_id: Administrator performing the action
        action_type: Type of administrative action
        affected_entities: Entities affected by the action
        details: Additional action details
    """
    admin_data = {
        "admin_user_id": admin_user_id,
        "action_type": action_type,
        "affected_entities": affected_entities,
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": "administrative_action"
    }
    
    if details:
        admin_data["details"] = details
    
    logger_instance.info("Administrative action", extra=admin_data)
