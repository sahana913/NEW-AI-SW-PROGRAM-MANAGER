"""Main Lambda handler for health score calculation service."""

import sys
import os
import json
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logger import get_logger
from shared.decorators import with_logging, with_error_handling, with_tenant_isolation
from shared.errors import ValidationError

from .score_calculator import calculate_health_score
from .score_storage import (
    store_health_score_history,
    get_health_score_history,
    get_latest_health_score,
    publish_health_score_event
)

logger = get_logger()


@with_logging
@with_error_handling
def calculate_health_score_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for calculating health score for a project.
    
    This is triggered after data ingestion completes or on-demand.
    
    Validates:
    - Property 54: Health Score Composition
    - Property 55: Health Score Range
    - Property 56: Health Score Update Triggering
    - Property 57: Health Score History Persistence
    - Property 58: Default Weight Application
    - Property 59: Custom Weight Application
    
    Event format:
    {
        "project_id": "uuid",
        "tenant_id": "uuid",
        "custom_weights": {  # Optional
            "velocity": 0.30,
            "backlog": 0.25,
            "milestones": 0.30,
            "risks": 0.15
        }
    }
    
    Returns:
        API Gateway response with health score
    """
    # Extract parameters
    project_id = event.get('project_id')
    tenant_id = event.get('tenant_id')
    custom_weights = event.get('custom_weights')
    
    if not project_id or not tenant_id:
        raise ValidationError("Missing required parameters: project_id and tenant_id")
    
    logger.info(
        f"Starting health score calculation",
        extra={"project_id": project_id, "tenant_id": tenant_id}
    )
    
    try:
        # Calculate health score
        health_score_data = calculate_health_score(
            project_id=project_id,
            tenant_id=tenant_id,
            custom_weights=custom_weights
        )
        
        # Store in history
        history_id = store_health_score_history(
            project_id=project_id,
            tenant_id=tenant_id,
            health_score_data=health_score_data
        )
        
        health_score_data['history_id'] = history_id
        
        # Publish event for downstream processing (RAG status, notifications, etc.)
        publish_health_score_event(
            project_id=project_id,
            tenant_id=tenant_id,
            health_score_data=health_score_data
        )
        
        logger.info(
            f"Health score calculation completed",
            extra={
                "project_id": project_id,
                "health_score": health_score_data['health_score']
            }
        )
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps(health_score_data)
        }
        
    except Exception as e:
        logger.error(
            f"Health score calculation failed",
            extra={"project_id": project_id, "error": str(e)}
        )
        raise


@with_logging
@with_error_handling
@with_tenant_isolation
def get_health_score_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for retrieving current health score for a project.
    
    Path parameters:
    - projectId: Project ID
    
    Returns:
        API Gateway response with latest health score
    """
    # Extract tenant_id from event (injected by with_tenant_isolation)
    tenant_id = event.get('tenant_id')
    
    # Extract path parameters
    path_params = event.get('pathParameters') or {}
    project_id = path_params.get('projectId')
    
    if not project_id:
        raise ValidationError("Missing required parameter: projectId")
    
    logger.info(
        f"Retrieving health score",
        extra={"project_id": project_id, "tenant_id": tenant_id}
    )
    
    try:
        health_score = get_latest_health_score(project_id, tenant_id)
        
        if not health_score:
            return {
                "statusCode": 404,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps({
                    "message": "No health score found for project"
                })
            }
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps(health_score)
        }
        
    except Exception as e:
        logger.error(
            f"Failed to retrieve health score",
            extra={"project_id": project_id, "error": str(e)}
        )
        raise


@with_logging
@with_error_handling
@with_tenant_isolation
def get_health_score_history_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for retrieving health score history for a project.
    
    Path parameters:
    - projectId: Project ID
    
    Query parameters:
    - limit: Maximum number of history entries (default 30)
    
    Returns:
        API Gateway response with health score history
    """
    # Extract tenant_id from event (injected by with_tenant_isolation)
    tenant_id = event.get('tenant_id')
    
    # Extract path parameters
    path_params = event.get('pathParameters') or {}
    project_id = path_params.get('projectId')
    
    if not project_id:
        raise ValidationError("Missing required parameter: projectId")
    
    # Extract query parameters
    query_params = event.get('queryStringParameters') or {}
    limit = int(query_params.get('limit', 30))
    
    logger.info(
        f"Retrieving health score history",
        extra={"project_id": project_id, "tenant_id": tenant_id, "limit": limit}
    )
    
    try:
        history = get_health_score_history(
            project_id=project_id,
            tenant_id=tenant_id,
            limit=limit
        )
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "history": history,
                "count": len(history)
            })
        }
        
    except Exception as e:
        logger.error(
            f"Failed to retrieve health score history",
            extra={"project_id": project_id, "error": str(e)}
        )
        raise
