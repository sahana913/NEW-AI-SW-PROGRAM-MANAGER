"""Main Lambda handler for dashboard API service."""

import sys
import os
import json
from typing import Dict, Any, List, Optional

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logger import get_logger
from shared.decorators import with_logging, with_error_handling, with_tenant_isolation
from shared.errors import ValidationError

from .dashboard_aggregator import (
    get_dashboard_overview,
    get_project_dashboard,
    get_metrics
)
from .cache_manager import get_cached_data, cache_dashboard_data, invalidate_cache

logger = get_logger()


@with_logging
@with_error_handling
@with_tenant_isolation
def get_dashboard_overview_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for retrieving dashboard overview.
    
    Aggregates project summaries with health scores and RAG status,
    recent risk alerts, and upcoming milestones.
    
    Validates: Requirement 20.1, 20.2, 20.3
    
    Query parameters:
    - projectIds: Optional comma-separated list of project IDs
    
    Returns:
        API Gateway response with dashboard overview
    """
    # Extract tenant_id from event (injected by with_tenant_isolation)
    tenant_id = event.get('tenant_id')
    
    # Extract query parameters
    query_params = event.get('queryStringParameters') or {}
    project_ids_str = query_params.get('projectIds')
    project_ids = project_ids_str.split(',') if project_ids_str else None
    
    logger.info(
        f"Retrieving dashboard overview",
        extra={"tenant_id": tenant_id, "project_ids": project_ids}
    )
    
    try:
        # Check cache first
        cache_key = f"dashboard:overview:{tenant_id}"
        if project_ids:
            cache_key += f":{','.join(sorted(project_ids))}"
        
        cached_data = get_cached_data(cache_key)
        if cached_data:
            logger.info("Returning cached dashboard overview")
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps(cached_data)
            }
        
        # Get fresh data
        dashboard_data = get_dashboard_overview(tenant_id, project_ids)
        
        # Cache for 5 minutes using dashboard cache TTL
        cache_dashboard_data(cache_key, dashboard_data)
        
        logger.info(
            f"Dashboard overview retrieved",
            extra={
                "tenant_id": tenant_id,
                "project_count": len(dashboard_data.get('projects', []))
            }
        )
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps(dashboard_data)
        }
        
    except Exception as e:
        logger.error(
            f"Failed to retrieve dashboard overview",
            extra={"tenant_id": tenant_id, "error": str(e)}
        )
        raise


@with_logging
@with_error_handling
@with_tenant_isolation
def get_project_dashboard_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for retrieving project-specific dashboard.
    
    Queries project details, health score, RAG status, velocity trends,
    backlog trends, milestone timeline, active risks, and predictions.
    
    Validates: Requirement 20.1, 20.4, 20.5
    
    Path parameters:
    - projectId: Project ID
    
    Returns:
        API Gateway response with project dashboard
    """
    # Extract tenant_id from event (injected by with_tenant_isolation)
    tenant_id = event.get('tenant_id')
    
    # Extract path parameters
    path_params = event.get('pathParameters') or {}
    project_id = path_params.get('projectId')
    
    if not project_id:
        raise ValidationError("Missing required parameter: projectId")
    
    logger.info(
        f"Retrieving project dashboard",
        extra={"tenant_id": tenant_id, "project_id": project_id}
    )
    
    try:
        # Check cache first
        cache_key = f"dashboard:project:{tenant_id}:{project_id}"
        
        cached_data = get_cached_data(cache_key)
        if cached_data:
            logger.info("Returning cached project dashboard")
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps(cached_data)
            }
        
        # Get fresh data
        dashboard_data = get_project_dashboard(tenant_id, project_id)
        
        if not dashboard_data:
            return {
                "statusCode": 404,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps({
                    "message": "Project not found"
                })
            }
        
        # Cache for 5 minutes using dashboard cache TTL
        cache_dashboard_data(cache_key, dashboard_data)
        
        logger.info(
            f"Project dashboard retrieved",
            extra={"tenant_id": tenant_id, "project_id": project_id}
        )
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps(dashboard_data)
        }
        
    except Exception as e:
        logger.error(
            f"Failed to retrieve project dashboard",
            extra={"tenant_id": tenant_id, "project_id": project_id, "error": str(e)}
        )
        raise


@with_logging
@with_error_handling
@with_tenant_isolation
def get_metrics_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for retrieving metrics.
    
    Supports metric types: velocity, backlog, utilization
    Supports time ranges: 7d, 30d, 90d, all
    
    Validates: Requirement 20.6
    
    Path parameters:
    - projectId: Project ID
    
    Query parameters:
    - metricType: velocity, backlog, or utilization (required)
    - timeRange: 7d, 30d, 90d, or all (default: 30d)
    
    Returns:
        API Gateway response with metrics data
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
    metric_type = query_params.get('metricType')
    time_range = query_params.get('timeRange', '30d')
    
    if not metric_type:
        raise ValidationError("Missing required parameter: metricType")
    
    if metric_type not in ['velocity', 'backlog', 'utilization']:
        raise ValidationError(f"Invalid metricType: {metric_type}. Must be velocity, backlog, or utilization")
    
    if time_range not in ['7d', '30d', '90d', 'all']:
        raise ValidationError(f"Invalid timeRange: {time_range}. Must be 7d, 30d, 90d, or all")
    
    logger.info(
        f"Retrieving metrics",
        extra={
            "tenant_id": tenant_id,
            "project_id": project_id,
            "metric_type": metric_type,
            "time_range": time_range
        }
    )
    
    try:
        # Get metrics data
        metrics_data = get_metrics(tenant_id, project_id, metric_type, time_range)
        
        if not metrics_data:
            return {
                "statusCode": 404,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps({
                    "message": "No metrics data found"
                })
            }
        
        logger.info(
            f"Metrics retrieved",
            extra={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "metric_type": metric_type
            }
        )
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps(metrics_data)
        }
        
    except Exception as e:
        logger.error(
            f"Failed to retrieve metrics",
            extra={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "metric_type": metric_type,
                "error": str(e)
            }
        )
        raise
