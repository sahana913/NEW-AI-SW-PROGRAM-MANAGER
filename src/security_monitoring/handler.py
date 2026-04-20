"""
Security Monitoring Lambda Handler

Processes security violation events from EventBridge and maintains
violation records for audit and compliance purposes.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

from shared.decorators import with_error_handling, with_logging
from shared.logger import get_logger, log_error

logger = get_logger("security-monitoring-handler")

# Initialize DynamoDB client lazily
_dynamodb = None


def get_dynamodb_client():
    """Get or create DynamoDB client."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb


VIOLATIONS_TABLE_NAME = os.environ.get("VIOLATIONS_TABLE_NAME", "SecurityViolations")


@with_logging
@with_error_handling
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Process security violation events from EventBridge.

    This Lambda is triggered by EventBridge when security violations are detected.
    It stores violation records in DynamoDB for audit and compliance tracking.

    Args:
        event: EventBridge event containing violation details
        context: Lambda context

    Returns:
        Response dictionary
    """
    logger.info("Processing security violation event", extra={"event": event})

    # Extract violation details from EventBridge event
    detail = event.get("detail", {})

    if not detail:
        logger.error("No detail found in event")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid event format"}),
        }

    violation_id = detail.get("violation_id")

    try:
        # Store violation record
        store_violation_record(detail)

        logger.info(
            "Security violation processed successfully",
            extra={"violation_id": violation_id},
        )

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Violation processed successfully",
                    "violation_id": violation_id,
                }
            ),
        }

    except Exception as e:
        log_error(
            logger,
            e,
            context={"function": "lambda_handler", "violation_id": violation_id},
        )
        raise


def store_violation_record(violation_details: Dict[str, Any]) -> None:
    """
    Store security violation record in DynamoDB.

    Args:
        violation_details: Details of the security violation

    Raises:
        ClientError: If DynamoDB operation fails
    """
    dynamodb = get_dynamodb_client()
    table = dynamodb.Table(VIOLATIONS_TABLE_NAME)

    # Prepare item for DynamoDB
    item = {
        "PK": f"VIOLATION#{violation_details['violation_id']}",
        "SK": f"TIMESTAMP#{violation_details['timestamp']}",
        "violation_id": violation_details["violation_id"],
        "violation_type": violation_details["violation_type"],
        "severity": violation_details["severity"],
        "user_id": violation_details["user_id"],
        "user_tenant_id": violation_details["user_tenant_id"],
        "requested_tenant_id": violation_details.get("requested_tenant_id", ""),
        "endpoint": violation_details["endpoint"],
        "timestamp": violation_details["timestamp"],
        "request_context": violation_details.get("request_context", {}),
        "status": "BLOCKED",
        "created_at": datetime.utcnow().isoformat(),
        "GSI1PK": f"TENANT#{violation_details['user_tenant_id']}",
        "GSI1SK": f"VIOLATION#{violation_details['timestamp']}",
        "GSI2PK": f"USER#{violation_details['user_id']}",
        "GSI2SK": f"VIOLATION#{violation_details['timestamp']}",
    }

    try:
        table.put_item(Item=item)
        logger.info(
            "Violation record stored",
            extra={"violation_id": violation_details["violation_id"]},
        )
    except ClientError as e:
        log_error(
            logger,
            e,
            context={
                "function": "store_violation_record",
                "violation_id": violation_details["violation_id"],
            },
        )
        raise


def get_violations_by_tenant(tenant_id: str, limit: int = 100) -> list:
    """
    Retrieve security violations for a specific tenant.

    Args:
        tenant_id: Tenant ID to query
        limit: Maximum number of records to return

    Returns:
        List of violation records
    """
    dynamodb = get_dynamodb_client()
    table = dynamodb.Table(VIOLATIONS_TABLE_NAME)

    try:
        response = table.query(
            IndexName="GSI1",
            KeyConditionExpression="GSI1PK = :pk",
            ExpressionAttributeValues={":pk": f"TENANT#{tenant_id}"},
            Limit=limit,
            ScanIndexForward=False,  # Most recent first
        )

        return response.get("Items", [])

    except ClientError as e:
        log_error(
            logger,
            e,
            context={"function": "get_violations_by_tenant", "tenant_id": tenant_id},
        )
        return []


def get_violations_by_user(user_id: str, limit: int = 100) -> list:
    """
    Retrieve security violations for a specific user.

    Args:
        user_id: User ID to query
        limit: Maximum number of records to return

    Returns:
        List of violation records
    """
    dynamodb = get_dynamodb_client()
    table = dynamodb.Table(VIOLATIONS_TABLE_NAME)

    try:
        response = table.query(
            IndexName="GSI2",
            KeyConditionExpression="GSI2PK = :pk",
            ExpressionAttributeValues={":pk": f"USER#{user_id}"},
            Limit=limit,
            ScanIndexForward=False,  # Most recent first
        )

        return response.get("Items", [])

    except ClientError as e:
        log_error(
            logger,
            e,
            context={"function": "get_violations_by_user", "user_id": user_id},
        )
        return []
