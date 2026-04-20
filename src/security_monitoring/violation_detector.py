"""
Security Violation Detector

Detects and handles security violations including cross-tenant data access attempts.
Integrates with the tenant isolation decorator to monitor and block violations.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

from shared.logger import get_logger, log_error

logger = get_logger("security-violation-detector")

# Initialize clients lazily
_sns = None
_eventbridge = None


def get_sns_client():
    """Get or create SNS client."""
    global _sns
    if _sns is None:
        _sns = boto3.client("sns")
    return _sns


def get_eventbridge_client():
    """Get or create EventBridge client."""
    global _eventbridge
    if _eventbridge is None:
        _eventbridge = boto3.client("events")
    return _eventbridge


# Environment variables
SECURITY_ALERT_TOPIC_ARN = os.environ.get("SECURITY_ALERT_TOPIC_ARN", "")
EVENT_BUS_NAME = os.environ.get("EVENT_BUS_NAME", "default")


def detect_cross_tenant_access(
    user_tenant_id: str,
    requested_tenant_id: str,
    user_id: str,
    endpoint: str,
    request_context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Detect cross-tenant data access attempt.

    This function is called when a potential cross-tenant access is detected.
    It logs the violation, publishes an event, and alerts administrators.

    Validates: Requirement 25.6 - Cross-tenant access detection and blocking

    Args:
        user_tenant_id: Tenant ID from user's authentication context
        requested_tenant_id: Tenant ID requested in the API call
        user_id: User attempting the access
        endpoint: API endpoint being accessed
        request_context: Full request context for logging

    Returns:
        Violation details dictionary
    """
    violation_id = (
        f"VIOLATION-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{user_id[:8]}"
    )

    violation_details = {
        "violation_id": violation_id,
        "violation_type": "CROSS_TENANT_ACCESS",
        "severity": "CRITICAL",
        "user_id": user_id,
        "user_tenant_id": user_tenant_id,
        "requested_tenant_id": requested_tenant_id,
        "endpoint": endpoint,
        "timestamp": datetime.utcnow().isoformat(),
        "request_context": {
            "http_method": request_context.get("httpMethod"),
            "path": request_context.get("path"),
            "source_ip": request_context.get("requestContext", {})
            .get("identity", {})
            .get("sourceIp"),
            "user_agent": request_context.get("requestContext", {})
            .get("identity", {})
            .get("userAgent"),
        },
    }

    # Log violation with full context
    logger.error(
        "SECURITY VIOLATION: Cross-tenant access attempt detected",
        extra={
            "violation_id": violation_id,
            "violation_type": "CROSS_TENANT_ACCESS",
            "severity": "CRITICAL",
            "user_id": user_id,
            "user_tenant_id": user_tenant_id,
            "requested_tenant_id": requested_tenant_id,
            "endpoint": endpoint,
            "source_ip": violation_details["request_context"]["source_ip"],
            "user_agent": violation_details["request_context"]["user_agent"],
        },
    )

    # Publish violation event
    publish_violation_event(violation_details)

    # Alert administrator
    alert_administrator(violation_details)

    return violation_details


def publish_violation_event(violation_details: Dict[str, Any]) -> bool:
    """
    Publish security violation event to EventBridge.

    Args:
        violation_details: Details of the security violation

    Returns:
        True if event published successfully, False otherwise
    """
    try:
        eventbridge = get_eventbridge_client()

        event = {
            "Source": "custom.security",
            "DetailType": "Security Violation",
            "Detail": json.dumps(violation_details),
            "EventBusName": EVENT_BUS_NAME,
        }

        response = eventbridge.put_events(Entries=[event])

        if response["FailedEntryCount"] > 0:
            logger.error(
                "Failed to publish security violation event",
                extra={
                    "violation_id": violation_details.get("violation_id"),
                    "failed_entries": response["Entries"],
                },
            )
            return False

        logger.info(
            "Security violation event published",
            extra={"violation_id": violation_details.get("violation_id")},
        )
        return True

    except ClientError as e:
        log_error(
            logger,
            e,
            context={
                "function": "publish_violation_event",
                "violation_id": violation_details.get("violation_id"),
            },
        )
        return False


def alert_administrator(violation_details: Dict[str, Any]) -> bool:
    """
    Send immediate alert to administrators via SNS.

    Args:
        violation_details: Details of the security violation

    Returns:
        True if alert sent successfully, False otherwise
    """
    if not SECURITY_ALERT_TOPIC_ARN:
        logger.warning("SECURITY_ALERT_TOPIC_ARN not configured, skipping SNS alert")
        return False

    try:
        sns = get_sns_client()

        # Format alert message
        subject = f"CRITICAL: Security Violation Detected - {violation_details['violation_type']}"

        message = f"""
SECURITY VIOLATION ALERT

Violation ID: {violation_details['violation_id']}
Type: {violation_details['violation_type']}
Severity: {violation_details['severity']}
Timestamp: {violation_details['timestamp']}

User Details:
- User ID: {violation_details['user_id']}
- User Tenant: {violation_details['user_tenant_id']}
- Requested Tenant: {violation_details['requested_tenant_id']}

Request Details:
- Endpoint: {violation_details['endpoint']}
- Method: {violation_details['request_context']['http_method']}
- Path: {violation_details['request_context']['path']}
- Source IP: {violation_details['request_context']['source_ip']}
- User Agent: {violation_details['request_context']['user_agent']}

Action Taken: Request blocked at API Gateway level

This is an automated security alert. Please investigate immediately.
"""

        response = sns.publish(
            TopicArn=SECURITY_ALERT_TOPIC_ARN,
            Subject=subject,
            Message=message,
            MessageAttributes={
                "violation_type": {
                    "DataType": "String",
                    "StringValue": violation_details["violation_type"],
                },
                "severity": {
                    "DataType": "String",
                    "StringValue": violation_details["severity"],
                },
                "user_id": {
                    "DataType": "String",
                    "StringValue": violation_details["user_id"],
                },
            },
        )

        logger.info(
            "Administrator alert sent",
            extra={
                "violation_id": violation_details["violation_id"],
                "message_id": response["MessageId"],
            },
        )
        return True

    except ClientError as e:
        log_error(
            logger,
            e,
            context={
                "function": "alert_administrator",
                "violation_id": violation_details.get("violation_id"),
            },
        )
        return False


def log_violation_attempt(
    violation_type: str, user_id: str, tenant_id: str, details: Dict[str, Any]
) -> None:
    """
    Log a security violation attempt with full context.

    This function provides structured logging for all types of security violations.

    Args:
        violation_type: Type of violation (e.g., CROSS_TENANT_ACCESS, UNAUTHORIZED_ACCESS)
        user_id: User attempting the violation
        tenant_id: Tenant context
        details: Additional violation details
    """
    logger.error(
        f"Security violation: {violation_type}",
        extra={
            "violation_type": violation_type,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "timestamp": datetime.utcnow().isoformat(),
            **details,
        },
    )
