"""Main Lambda handler for RAG status determination service."""

from .rag_storage import (
    detect_status_degradation,
    get_latest_rag_status,
    get_previous_rag_status,
    get_rag_status_history,
    publish_degradation_notification,
    publish_rag_status_event,
    store_rag_status,
)
from .rag_calculator import calculate_rag_status
from shared.logger import get_logger
from shared.errors import ValidationError
from shared.decorators import with_error_handling, with_logging, with_tenant_isolation
import json
import os
import sys
from typing import Any, Dict

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


logger = get_logger()


@with_logging
@with_error_handling
def calculate_rag_status_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for calculating RAG status for a project.

    This is triggered by EventBridge when health score is updated.

    Validates:
    - Property 60: RAG Status Determination
    - Property 61: Custom Threshold Application
    - Property 62: RAG Status Update Triggering
    - Property 63: RAG Degradation Notification

    Event format (from EventBridge):
    {
        "detail": {
            "project_id": "uuid",
            "tenant_id": "uuid",
            "health_score": 75,
            "component_scores": {...},
            "calculated_at": "2024-01-01T00:00:00Z"
        }
    }

    Or direct invocation:
    {
        "project_id": "uuid",
        "tenant_id": "uuid",
        "health_score": 75,
        "custom_thresholds": {  # Optional
            "green": 80,
            "amber": 60
        }
    }

    Returns:
        API Gateway response with RAG status
    """
    # Handle EventBridge event format
    if "detail" in event:
        detail = event["detail"]
        project_id = detail.get("project_id")
        tenant_id = detail.get("tenant_id")
        health_score = detail.get("health_score")
        custom_thresholds = detail.get("custom_thresholds")
    else:
        # Direct invocation
        project_id = event.get("project_id")
        tenant_id = event.get("tenant_id")
        health_score = event.get("health_score")
        custom_thresholds = event.get("custom_thresholds")

    if not project_id or not tenant_id or health_score is None:
        raise ValidationError(
            "Missing required parameters: project_id, tenant_id, and health_score"
        )

    logger.info(
        f"Starting RAG status calculation",
        extra={
            "project_id": project_id,
            "tenant_id": tenant_id,
            "health_score": health_score,
        },
    )

    try:
        # Get previous RAG status for degradation detection
        previous_status = get_previous_rag_status(project_id, tenant_id)

        # Calculate RAG status
        rag_status_data = calculate_rag_status(
            project_id=project_id,
            tenant_id=tenant_id,
            health_score=health_score,
            custom_thresholds=custom_thresholds,
        )

        # Store RAG status
        status_id = store_rag_status(
            project_id=project_id, tenant_id=tenant_id, rag_status_data=rag_status_data
        )

        rag_status_data["status_id"] = status_id

        # Publish RAG status event
        publish_rag_status_event(
            project_id=project_id, tenant_id=tenant_id, rag_status_data=rag_status_data
        )

        # Check for status degradation and publish notification
        current_status = rag_status_data["rag_status"]
        if detect_status_degradation(current_status, previous_status):
            logger.warning(
                f"RAG status degradation detected",
                extra={
                    "project_id": project_id,
                    "previous_status": previous_status,
                    "current_status": current_status,
                },
            )

            publish_degradation_notification(
                project_id=project_id,
                tenant_id=tenant_id,
                current_status=current_status,
                previous_status=previous_status,
                health_score=health_score,
            )

        logger.info(
            f"RAG status calculation completed",
            extra={
                "project_id": project_id,
                "rag_status": rag_status_data["rag_status"],
                "degradation_detected": detect_status_degradation(
                    current_status, previous_status
                ),
            },
        )

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(rag_status_data),
        }

    except Exception as e:
        logger.error(
            f"RAG status calculation failed",
            extra={"project_id": project_id, "error": str(e)},
        )
        raise


@with_logging
@with_error_handling
@with_tenant_isolation
def get_rag_status_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for retrieving current RAG status for a project.

    Path parameters:
    - projectId: Project ID

    Returns:
        API Gateway response with latest RAG status
    """
    # Extract tenant_id from event (injected by with_tenant_isolation)
    tenant_id = event.get("tenant_id")

    # Extract path parameters
    path_params = event.get("pathParameters") or {}
    project_id = path_params.get("projectId")

    if not project_id:
        raise ValidationError("Missing required parameter: projectId")

    logger.info(
        f"Retrieving RAG status",
        extra={"project_id": project_id, "tenant_id": tenant_id},
    )

    try:
        rag_status = get_latest_rag_status(project_id, tenant_id)

        if not rag_status:
            return {
                "statusCode": 404,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({"message": "No RAG status found for project"}),
            }

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(rag_status),
        }

    except Exception as e:
        logger.error(
            f"Failed to retrieve RAG status",
            extra={"project_id": project_id, "error": str(e)},
        )
        raise


@with_logging
@with_error_handling
@with_tenant_isolation
def get_rag_status_history_handler(
    event: Dict[str, Any], context: Any
) -> Dict[str, Any]:
    """
    Lambda handler for retrieving RAG status history for a project.

    Path parameters:
    - projectId: Project ID

    Query parameters:
    - limit: Maximum number of history entries (default 30)

    Returns:
        API Gateway response with RAG status history
    """
    # Extract tenant_id from event (injected by with_tenant_isolation)
    tenant_id = event.get("tenant_id")

    # Extract path parameters
    path_params = event.get("pathParameters") or {}
    project_id = path_params.get("projectId")

    if not project_id:
        raise ValidationError("Missing required parameter: projectId")

    # Extract query parameters
    query_params = event.get("queryStringParameters") or {}
    limit = int(query_params.get("limit", 30))

    logger.info(
        f"Retrieving RAG status history",
        extra={"project_id": project_id, "tenant_id": tenant_id, "limit": limit},
    )

    try:
        history = get_rag_status_history(
            project_id=project_id, tenant_id=tenant_id, limit=limit
        )

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"history": history, "count": len(history)}),
        }

    except Exception as e:
        logger.error(
            f"Failed to retrieve RAG status history",
            extra={"project_id": project_id, "error": str(e)},
        )
        raise
