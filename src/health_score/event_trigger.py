"""EventBridge trigger handler for health score recalculation."""

import sys
import os
import json
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logger import get_logger
from shared.decorators import with_logging, with_error_handling

from .score_calculator import calculate_health_score
from .score_storage import store_health_score_history, publish_health_score_event

logger = get_logger()


@with_logging
@with_error_handling
def data_refresh_trigger_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    EventBridge handler for triggering health score recalculation after data refresh.
    
    Validates: Property 56 - Health Score Update Triggering
    
    This handler is triggered by EventBridge when:
    - DataIngestionCompleted event is published
    - RiskDetectionCompleted event is published
    
    Event format (from EventBridge):
    {
        "version": "0",
        "id": "event-id",
        "detail-type": "DataIngestionCompleted",
        "source": "ai-sw-pm.data-ingestion",
        "detail": {
            "project_id": "uuid",
            "tenant_id": "uuid",
            "ingestion_type": "JIRA",
            "completed_at": "2024-01-15T10:30:00Z"
        }
    }
    
    Returns:
        Success response
    """
    try:
        # Extract event details
        detail = event.get('detail', {})
        project_id = detail.get('project_id')
        tenant_id = detail.get('tenant_id')
        event_type = event.get('detail-type', 'Unknown')
        
        if not project_id or not tenant_id:
            logger.warning(
                f"Missing project_id or tenant_id in event",
                extra={"event": event}
            )
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "message": "Missing required fields in event"
                })
            }
        
        logger.info(
            f"Health score recalculation triggered by {event_type}",
            extra={
                "project_id": project_id,
                "tenant_id": tenant_id,
                "event_type": event_type
            }
        )
        
        # Calculate health score
        health_score_data = calculate_health_score(
            project_id=project_id,
            tenant_id=tenant_id
        )
        
        # Store in history
        history_id = store_health_score_history(
            project_id=project_id,
            tenant_id=tenant_id,
            health_score_data=health_score_data
        )
        
        # Publish event for downstream processing
        publish_health_score_event(
            project_id=project_id,
            tenant_id=tenant_id,
            health_score_data=health_score_data
        )
        
        logger.info(
            f"Health score recalculation completed",
            extra={
                "project_id": project_id,
                "health_score": health_score_data['health_score'],
                "history_id": history_id,
                "triggered_by": event_type
            }
        )
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Health score recalculated successfully",
                "project_id": project_id,
                "health_score": health_score_data['health_score'],
                "history_id": history_id
            })
        }
        
    except Exception as e:
        logger.error(
            f"Health score recalculation failed",
            extra={
                "event": event,
                "error": str(e)
            }
        )
        raise


@with_logging
@with_error_handling
def scheduled_recalculation_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    EventBridge scheduled handler for periodic health score recalculation.
    
    This handler runs on a schedule (e.g., every hour) to ensure all projects
    have up-to-date health scores even if events are missed.
    
    Event format (from EventBridge scheduled rule):
    {
        "version": "0",
        "id": "event-id",
        "detail-type": "Scheduled Event",
        "source": "aws.events",
        "detail": {}
    }
    
    Returns:
        Success response with count of projects processed
    """
    try:
        from shared.database import execute_query
        
        logger.info("Starting scheduled health score recalculation for all projects")
        
        # Query all active projects
        query = """
            SELECT DISTINCT 
                p.project_id::text,
                p.tenant_id::text
            FROM projects p
            WHERE p.last_sync_at IS NOT NULL
            ORDER BY p.last_sync_at DESC
        """
        
        projects = execute_query(query, fetch=True)
        
        if not projects:
            logger.info("No projects found for health score recalculation")
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": "No projects to process",
                    "projects_processed": 0
                })
            }
        
        logger.info(
            f"Found {len(projects)} projects for health score recalculation"
        )
        
        processed_count = 0
        failed_count = 0
        
        for project in projects:
            project_id = project['project_id']
            tenant_id = project['tenant_id']
            
            try:
                # Calculate health score
                health_score_data = calculate_health_score(
                    project_id=project_id,
                    tenant_id=tenant_id
                )
                
                # Store in history
                store_health_score_history(
                    project_id=project_id,
                    tenant_id=tenant_id,
                    health_score_data=health_score_data
                )
                
                # Publish event
                publish_health_score_event(
                    project_id=project_id,
                    tenant_id=tenant_id,
                    health_score_data=health_score_data
                )
                
                processed_count += 1
                
                logger.info(
                    f"Health score recalculated for project",
                    extra={
                        "project_id": project_id,
                        "health_score": health_score_data['health_score']
                    }
                )
                
            except Exception as e:
                failed_count += 1
                logger.error(
                    f"Failed to recalculate health score for project",
                    extra={
                        "project_id": project_id,
                        "error": str(e)
                    }
                )
                # Continue processing other projects
        
        logger.info(
            f"Scheduled health score recalculation completed",
            extra={
                "total_projects": len(projects),
                "processed": processed_count,
                "failed": failed_count
            }
        )
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Scheduled health score recalculation completed",
                "total_projects": len(projects),
                "projects_processed": processed_count,
                "projects_failed": failed_count
            })
        }
        
    except Exception as e:
        logger.error(
            f"Scheduled health score recalculation failed",
            extra={"error": str(e)}
        )
        raise
