"""
Audit Logging Lambda Handler

This Lambda function processes audit events from EventBridge and CloudWatch Logs,
ensuring all authentication attempts, data modifications, and administrative actions
are properly logged to CloudWatch and CloudTrail.

Validates: Requirements 28.1, 28.2, 28.3
"""

import json
from datetime import datetime
from typing import Any, Dict

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext

from shared.decorators import with_error_handling
from shared.logger import (
    log_administrative_action,
    log_authentication_attempt,
    log_data_modification,
    log_error,
)

logger = Logger(service="audit-logging")


@with_error_handling
def handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    """
    Process audit events and log them to CloudWatch and CloudTrail.

    This handler receives events from:
    - EventBridge (authentication events, data modification events, admin actions)
    - Direct invocations from other Lambda functions

    Args:
        event: Event data containing audit information
        context: Lambda context

    Returns:
        Response with processing status
    """
    try:
        # Determine event source
        event_source = event.get("source", "direct")

        if event_source == "aws.cognito":
            # Authentication event from Cognito
            return process_authentication_event(event)
        elif event_source == "custom.datamodification":
            # Data modification event
            return process_data_modification_event(event)
        elif event_source == "custom.adminaction":
            # Administrative action event
            return process_admin_action_event(event)
        elif "detail-type" in event:
            # EventBridge event
            return process_eventbridge_event(event)
        else:
            # Direct invocation
            return process_direct_invocation(event)

    except Exception as e:
        log_error(
            logger,
            e,
            context={
                "function": "audit_logging_handler",
                "event_source": event.get("source", "unknown"),
            },
        )
        raise


def process_authentication_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process authentication events from Cognito.

    Validates: Requirement 28.1 - Log all authentication attempts

    Args:
        event: Cognito authentication event

    Returns:
        Processing result
    """
    detail = event.get("detail", {})

    # Extract authentication details
    user_id = detail.get("userId", "unknown")
    email = detail.get("email", "unknown")
    success = detail.get("success", False)
    reason = detail.get("reason")

    # Log to CloudWatch
    log_authentication_attempt(
        logger, user_id=user_id, email=email, success=success, reason=reason
    )

    # Also log to CloudTrail via structured logging
    logger.info(
        "Authentication audit event",
        extra={
            "audit_type": "authentication",
            "user_id": user_id,
            "email": email,
            "success": success,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
            "cloudtrail_event": True,
        },
    )

    return {
        "statusCode": 200,
        "body": json.dumps(
            {"message": "Authentication event logged", "user_id": user_id}
        ),
    }


def process_data_modification_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process data modification events.

    Validates: Requirement 28.2 - Log all data modification operations

    Args:
        event: Data modification event

    Returns:
        Processing result
    """
    detail = event.get("detail", {})

    # Extract modification details
    user_id = detail.get("userId")
    tenant_id = detail.get("tenantId")
    operation_type = detail.get("operationType")
    entity_type = detail.get("entityType")
    entity_id = detail.get("entityId")
    changes = detail.get("changes")

    # Validate required fields
    if not all([user_id, tenant_id, operation_type, entity_type, entity_id]):
        logger.warning("Incomplete data modification event", extra={"event": event})
        return {
            "statusCode": 400,
            "body": json.dumps(
                {"error": "Missing required fields in data modification event"}
            ),
        }

    # Log to CloudWatch
    log_data_modification(
        logger,
        user_id=user_id,
        tenant_id=tenant_id,
        operation_type=operation_type,
        entity_type=entity_type,
        entity_id=entity_id,
        changes=changes,
    )

    # Also log to CloudTrail via structured logging
    logger.info(
        "Data modification audit event",
        extra={
            "audit_type": "data_modification",
            "user_id": user_id,
            "tenant_id": tenant_id,
            "operation_type": operation_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "changes": changes,
            "timestamp": datetime.utcnow().isoformat(),
            "cloudtrail_event": True,
        },
    )

    return {
        "statusCode": 200,
        "body": json.dumps(
            {"message": "Data modification event logged", "entity_id": entity_id}
        ),
    }


def process_admin_action_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process administrative action events.

    Validates: Requirement 28.3 - Log all administrative actions

    Args:
        event: Administrative action event

    Returns:
        Processing result
    """
    detail = event.get("detail", {})

    # Extract admin action details
    admin_user_id = detail.get("adminUserId")
    action_type = detail.get("actionType")
    affected_entities = detail.get("affectedEntities", {})
    details = detail.get("details")

    # Validate required fields
    if not all([admin_user_id, action_type, affected_entities]):
        logger.warning("Incomplete administrative action event", extra={"event": event})
        return {
            "statusCode": 400,
            "body": json.dumps(
                {"error": "Missing required fields in administrative action event"}
            ),
        }

    # Log to CloudWatch
    log_administrative_action(
        logger,
        admin_user_id=admin_user_id,
        action_type=action_type,
        affected_entities=affected_entities,
        details=details,
    )

    # Also log to CloudTrail via structured logging
    logger.info(
        "Administrative action audit event",
        extra={
            "audit_type": "administrative_action",
            "admin_user_id": admin_user_id,
            "action_type": action_type,
            "affected_entities": affected_entities,
            "details": details,
            "timestamp": datetime.utcnow().isoformat(),
            "cloudtrail_event": True,
        },
    )

    return {
        "statusCode": 200,
        "body": json.dumps(
            {"message": "Administrative action logged", "action_type": action_type}
        ),
    }


def process_eventbridge_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process generic EventBridge events.

    Args:
        event: EventBridge event

    Returns:
        Processing result
    """
    detail_type = event.get("detail-type")

    if "Authentication" in detail_type:
        return process_authentication_event(event)
    elif "DataModification" in detail_type:
        return process_data_modification_event(event)
    elif "AdminAction" in detail_type:
        return process_admin_action_event(event)
    else:
        logger.warning(
            "Unknown EventBridge event type", extra={"detail_type": detail_type}
        )
        return {
            "statusCode": 400,
            "body": json.dumps({"error": f"Unknown event type: {detail_type}"}),
        }


def process_direct_invocation(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process direct Lambda invocations.

    Args:
        event: Direct invocation event

    Returns:
        Processing result
    """
    audit_type = event.get("auditType")

    if audit_type == "authentication":
        return process_authentication_event({"detail": event})
    elif audit_type == "data_modification":
        return process_data_modification_event({"detail": event})
    elif audit_type == "admin_action":
        return process_admin_action_event({"detail": event})
    else:
        logger.warning(
            "Unknown audit type in direct invocation", extra={"audit_type": audit_type}
        )
        return {
            "statusCode": 400,
            "body": json.dumps({"error": f"Unknown audit type: {audit_type}"}),
        }
