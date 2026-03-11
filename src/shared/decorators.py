"""Decorators for cross-cutting concerns."""

import functools
import json
import time
import uuid
from typing import Any, Callable, Dict, Optional
from .logger import get_logger, log_error, log_api_request
from .errors import AppError, TenantIsolationError

logger = get_logger()


def with_logging(func: Callable) -> Callable:
    """
    Decorator to add structured logging to Lambda functions.
    
    Args:
        func: Function to decorate
        
    Returns:
        Decorated function with logging
    """
    @functools.wraps(func)
    def wrapper(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        request_id = str(uuid.uuid4())
        logger.info(
            f"Function {func.__name__} invoked",
            extra={
                "request_id": request_id,
                "function_name": func.__name__,
                "event": event
            }
        )
        
        try:
            result = func(event, context)
            logger.info(
                f"Function {func.__name__} completed successfully",
                extra={"request_id": request_id}
            )
            return result
        except Exception as e:
            log_error(logger, e, context={"request_id": request_id, "function_name": func.__name__})
            raise
    
    return wrapper


def with_error_handling(func: Callable) -> Callable:
    """
    Decorator to handle errors and return proper API responses.
    
    Args:
        func: Function to decorate
        
    Returns:
        Decorated function with error handling
    """
    @functools.wraps(func)
    def wrapper(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        try:
            return func(event, context)
        except AppError as e:
            return {
                "statusCode": e.status_code,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps(e.to_dict())
            }
        except Exception as e:
            log_error(logger, e, context={"function_name": func.__name__})
            return {
                "statusCode": 500,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps({
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "An unexpected error occurred"
                    }
                })
            }
    
    return wrapper


def with_tenant_isolation(func: Callable) -> Callable:
    """
    Decorator to enforce tenant isolation.
    
    Detects cross-tenant data access attempts, blocks violating requests,
    alerts administrators, and logs all violation attempts with full context.
    
    Validates: Property 1 - Tenant Data Isolation
    Validates: Property 69 - Access Violation Blocking (Requirement 25.6)
    
    Args:
        func: Function to decorate
        
    Returns:
        Decorated function with tenant isolation enforcement
    """
    @functools.wraps(func)
    def wrapper(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        # Extract tenant_id from authorizer context
        authorizer_context = event.get("requestContext", {}).get("authorizer", {})
        user_tenant_id = authorizer_context.get("tenantId")
        user_id = authorizer_context.get("userId", "unknown")
        
        if not user_tenant_id:
            raise TenantIsolationError("Missing tenant context")
        
        # Extract tenant_id from request (path, query, or body)
        request_tenant_id = None
        
        # Check path parameters
        path_params = event.get("pathParameters", {})
        if path_params and "tenantId" in path_params:
            request_tenant_id = path_params["tenantId"]
        
        # Check query parameters
        query_params = event.get("queryStringParameters", {})
        if query_params and "tenantId" in query_params:
            request_tenant_id = query_params["tenantId"]
        
        # Validate tenant isolation
        if request_tenant_id and request_tenant_id != user_tenant_id:
            # Import here to avoid circular dependency
            from security_monitoring.violation_detector import detect_cross_tenant_access
            
            # Construct endpoint for logging
            http_method = event.get("httpMethod", "UNKNOWN")
            path = event.get("path", "UNKNOWN")
            endpoint = f"{http_method} {path}"
            
            # Detect and handle the violation
            violation_details = detect_cross_tenant_access(
                user_tenant_id=user_tenant_id,
                requested_tenant_id=request_tenant_id,
                user_id=user_id,
                endpoint=endpoint,
                request_context=event
            )
            
            # Raise error to block the request
            raise TenantIsolationError(
                message="Cross-tenant access attempt detected and blocked",
                details={
                    "violation_id": violation_details["violation_id"],
                    "user_tenant": user_tenant_id,
                    "requested_tenant": request_tenant_id
                }
            )
        
        # Inject tenant_id into event for downstream use
        event["tenant_id"] = user_tenant_id
        
        return func(event, context)
    
    return wrapper


def with_audit_logging(func: Callable) -> Callable:
    """
    Decorator to add audit logging for API requests.
    
    Logs all API requests with request ID, user ID, tenant ID, and response time.
    Logs all errors with severity, timestamp, and context.
    Uses structured JSON logging format.
    
    Validates: Requirements 27.1, 27.2
    
    Args:
        func: Function to decorate
        
    Returns:
        Decorated function with audit logging
    """
    @functools.wraps(func)
    def wrapper(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        start_time = time.time()
        request_id = context.request_id if hasattr(context, "request_id") else str(uuid.uuid4())
        
        # Extract request metadata
        authorizer_context = event.get("requestContext", {}).get("authorizer", {})
        user_id = authorizer_context.get("userId", "unknown")
        tenant_id = authorizer_context.get("tenantId", "unknown")
        
        http_method = event.get("httpMethod", "unknown")
        path = event.get("path", "unknown")
        endpoint = f"{http_method} {path}"
        
        # Add request_id to logger context
        logger.append_keys(request_id=request_id)
        
        try:
            result = func(event, context)
            
            # Calculate response time
            response_time_ms = (time.time() - start_time) * 1000
            status_code = result.get("statusCode", 200)
            
            # Log API request
            log_api_request(
                logger,
                request_id=request_id,
                user_id=user_id,
                tenant_id=tenant_id,
                endpoint=endpoint,
                method=http_method,
                response_time_ms=response_time_ms,
                status_code=status_code
            )
            
            return result
        except Exception as e:
            # Calculate response time
            response_time_ms = (time.time() - start_time) * 1000
            
            # Log error with full context and stack trace
            log_error(
                logger,
                e,
                context={
                    "request_id": request_id,
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "endpoint": endpoint,
                    "method": http_method,
                    "function_name": func.__name__
                },
                severity="ERROR"
            )
            
            # Log failed request
            log_api_request(
                logger,
                request_id=request_id,
                user_id=user_id,
                tenant_id=tenant_id,
                endpoint=endpoint,
                method=http_method,
                response_time_ms=response_time_ms,
                status_code=500,
                error=str(e)
            )
            
            raise
    
    return wrapper


def with_performance_monitoring(threshold_ms: float = 2000) -> Callable:
    """
    Decorator to monitor function performance and log slow requests.
    
    Args:
        threshold_ms: Response time threshold in milliseconds
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
            start_time = time.time()
            
            result = func(event, context)
            
            response_time_ms = (time.time() - start_time) * 1000
            
            if response_time_ms > threshold_ms:
                logger.warning(
                    f"Slow request detected in {func.__name__}",
                    extra={
                        "function_name": func.__name__,
                        "response_time_ms": response_time_ms,
                        "threshold_ms": threshold_ms
                    }
                )
            
            return result
        
        return wrapper
    
    return decorator
