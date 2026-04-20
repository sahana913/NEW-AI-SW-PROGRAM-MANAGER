"""Risk alert storage and retrieval using DynamoDB."""

from shared.logger import get_logger
from shared.errors import DataError
from botocore.exceptions import ClientError
import boto3
import json
import os
import sys
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


logger = get_logger()

# Environment variables
RISKS_TABLE_NAME = os.environ.get("RISKS_TABLE_NAME", "ai-sw-pm-risks")
EVENT_BUS_NAME = os.environ.get("EVENT_BUS_NAME", "ai-sw-pm-events")

# AWS clients (initialized lazily)
_dynamodb = None
_eventbridge = None


def get_dynamodb_resource():
    """Get or create DynamoDB resource."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb


def get_eventbridge_client():
    """Get or create EventBridge client."""
    global _eventbridge
    if _eventbridge is None:
        _eventbridge = boto3.client("events")
    return _eventbridge


def convert_floats_to_decimals(obj: Any) -> Any:
    """
    Recursively convert floats to Decimals for DynamoDB storage.

    Args:
        obj: Object to convert

    Returns:
        Converted object
    """
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimals(item) for item in obj]
    return obj


def convert_decimals_to_floats(obj: Any) -> Any:
    """
    Recursively convert Decimals to floats for JSON serialization.

    Args:
        obj: Object to convert

    Returns:
        Converted object
    """
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: convert_decimals_to_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals_to_floats(item) for item in obj]
    return obj


def store_risk_alert(risk: Dict[str, Any]) -> str:
    """
    Store a risk alert in DynamoDB.

    Validates: Property 21 - Risk Alert Content Completeness

    Args:
        risk: Risk alert dictionary with required fields:
            - tenant_id
            - project_id
            - type
            - severity
            - title
            - description
            - metrics
            - recommendations
            - detected_at

    Returns:
        Risk ID (UUID)

    Raises:
        DataError: If storage fails
    """
    try:
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(RISKS_TABLE_NAME)

        # Generate risk ID
        risk_id = str(uuid.uuid4())

        # Prepare item for DynamoDB
        item = {
            "PK": f"TENANT#{risk['tenant_id']}",
            "SK": f"RISK#{risk_id}",
            "risk_id": risk_id,
            "project_id": risk["project_id"],
            "type": risk["type"],
            "severity": risk["severity"],
            "title": risk["title"],
            "description": risk.get("description", ""),
            "detected_at": risk.get("detected_at", datetime.utcnow().isoformat()),
            "status": "ACTIVE",
            "metrics": convert_floats_to_decimals(risk.get("metrics", {})),
            "recommendations": risk.get("recommendations", []),
            "GSI1PK": f"PROJECT#{risk['project_id']}",
            "GSI1SK": f"RISK#{risk.get('detected_at', datetime.utcnow().isoformat())}",
            "GSI2PK": f"TENANT#{risk['tenant_id']}#SEVERITY#{risk['severity']}",
            "GSI2SK": f"RISK#{risk.get('detected_at', datetime.utcnow().isoformat())}",
        }

        # Add optional fields
        if "milestone_id" in risk:
            item["milestone_id"] = risk["milestone_id"]
        if "milestone_name" in risk:
            item["milestone_name"] = risk["milestone_name"]

        # Store in DynamoDB
        table.put_item(Item=item)

        logger.info(
            f"Risk alert stored successfully",
            extra={
                "risk_id": risk_id,
                "project_id": risk["project_id"],
                "type": risk["type"],
                "severity": risk["severity"],
            },
        )

        return risk_id

    except ClientError as e:
        raise DataError(
            f"Failed to store risk alert: {str(e)}",
            data_source="DynamoDB",
            details={"table": RISKS_TABLE_NAME},
        )
    except Exception as e:
        raise DataError(f"Failed to store risk alert: {str(e)}", data_source="DynamoDB")


def list_risks(
    tenant_id: str,
    project_id: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    List risk alerts with optional filtering.

    Args:
        tenant_id: Tenant ID to filter by
        project_id: Optional project ID filter
        severity: Optional severity filter (LOW, MEDIUM, HIGH, CRITICAL)
        status: Optional status filter (ACTIVE, DISMISSED, RESOLVED)
        limit: Maximum number of results

    Returns:
        List of risk alert dictionaries

    Raises:
        DataError: If query fails
    """
    try:
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(RISKS_TABLE_NAME)

        # Build query based on filters
        if project_id:
            # Query by project using GSI1
            response = table.query(
                IndexName="GSI1",
                KeyConditionExpression="GSI1PK = :pk",
                ExpressionAttributeValues={":pk": f"PROJECT#{project_id}"},
                Limit=limit,
                ScanIndexForward=False,  # Most recent first
            )
        elif severity:
            # Query by tenant and severity using GSI2
            response = table.query(
                IndexName="GSI2",
                KeyConditionExpression="GSI2PK = :pk",
                ExpressionAttributeValues={
                    ":pk": f"TENANT#{tenant_id}#SEVERITY#{severity}"
                },
                Limit=limit,
                ScanIndexForward=False,
            )
        else:
            # Query by tenant
            response = table.query(
                KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
                ExpressionAttributeValues={
                    ":pk": f"TENANT#{tenant_id}",
                    ":sk": "RISK#",
                },
                Limit=limit,
                ScanIndexForward=False,
            )

        items = response.get("Items", [])

        # Apply status filter if specified
        if status:
            items = [item for item in items if item.get("status") == status]

        # Convert Decimals to floats
        risks = [convert_decimals_to_floats(item) for item in items]

        logger.info(
            f"Listed {len(risks)} risks",
            extra={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "severity": severity,
                "status": status,
            },
        )

        return risks

    except ClientError as e:
        raise DataError(
            f"Failed to list risks: {str(e)}",
            data_source="DynamoDB",
            details={"table": RISKS_TABLE_NAME},
        )
    except Exception as e:
        raise DataError(f"Failed to list risks: {str(e)}", data_source="DynamoDB")


def dismiss_risk(
    risk_id: str, tenant_id: str, dismissed_by: str, reason: str
) -> Dict[str, Any]:
    """
    Dismiss a risk alert.

    Args:
        risk_id: Risk ID to dismiss
        tenant_id: Tenant ID for validation
        dismissed_by: User ID who dismissed the risk
        reason: Reason for dismissal

    Returns:
        Updated risk dictionary

    Raises:
        DataError: If update fails
    """
    try:
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(RISKS_TABLE_NAME)

        # Update risk status
        response = table.update_item(
            Key={"PK": f"TENANT#{tenant_id}", "SK": f"RISK#{risk_id}"},
            UpdateExpression="SET #status = :status, dismissed_by = :user, dismissed_at = :timestamp, dismissal_reason = :reason",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":status": "DISMISSED",
                ":user": dismissed_by,
                ":timestamp": datetime.utcnow().isoformat(),
                ":reason": reason,
            },
            ReturnValues="ALL_NEW",
        )

        updated_item = response.get("Attributes", {})

        logger.info(
            f"Risk dismissed", extra={"risk_id": risk_id, "dismissed_by": dismissed_by}
        )

        return convert_decimals_to_floats(updated_item)

    except ClientError as e:
        raise DataError(
            f"Failed to dismiss risk: {str(e)}",
            data_source="DynamoDB",
            details={"risk_id": risk_id},
        )
    except Exception as e:
        raise DataError(f"Failed to dismiss risk: {str(e)}", data_source="DynamoDB")


def publish_risk_event(risk: Dict[str, Any], event_type: str = "RiskDetected") -> None:
    """
    Publish risk event to EventBridge.

    Args:
        risk: Risk alert dictionary
        event_type: Type of event (RiskDetected, RiskDismissed, etc.)

    Raises:
        DataError: If event publishing fails
    """
    try:
        eventbridge = get_eventbridge_client()

        # Prepare event
        event = {
            "Source": "ai-sw-program-manager.risk-detection",
            "DetailType": event_type,
            "Detail": json.dumps(convert_decimals_to_floats(risk)),
            "EventBusName": EVENT_BUS_NAME,
        }

        # Publish event
        response = eventbridge.put_events(Entries=[event])

        # Check for failures
        if response.get("FailedEntryCount", 0) > 0:
            failed_entries = response.get("Entries", [])
            raise DataError(
                f"Failed to publish risk event: {failed_entries}",
                data_source="EventBridge",
            )

        logger.info(
            f"Risk event published",
            extra={
                "event_type": event_type,
                "risk_id": risk.get("risk_id"),
                "project_id": risk.get("project_id"),
            },
        )

    except ClientError as e:
        raise DataError(
            f"Failed to publish risk event: {str(e)}", data_source="EventBridge"
        )
    except DataError:
        # Re-raise DataError (from FailedEntryCount check)
        raise
    except Exception as e:
        logger.error(
            f"Failed to publish risk event: {str(e)}",
            extra={"risk_id": risk.get("risk_id")},
        )
        # Don't raise - event publishing is non-critical
