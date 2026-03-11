"""Health score storage and history management."""

import sys
import os
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logger import get_logger
from shared.database import execute_query
from shared.errors import DataError

logger = get_logger()

# DynamoDB client (initialized lazily)
_dynamodb = None


def get_dynamodb():
    """Get or create DynamoDB client."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource('dynamodb')
    return _dynamodb


def store_health_score_history(
    project_id: str,
    tenant_id: str,
    health_score_data: Dict[str, Any]
) -> str:
    """
    Store health score in history for trend analysis.
    
    Validates: Property 57 - Health Score History Persistence
    
    Args:
        project_id: Project ID
        tenant_id: Tenant ID
        health_score_data: Health score calculation result
        
    Returns:
        History entry ID
        
    Raises:
        DataError: If storage fails
    """
    try:
        # Store in RDS for relational queries
        query = """
            INSERT INTO health_score_history (
                project_id,
                tenant_id,
                health_score,
                velocity_score,
                backlog_score,
                milestone_score,
                risk_score,
                weights,
                calculated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id::text
        """
        
        component_scores = health_score_data['component_scores']
        
        # First, ensure the table exists (in production, this would be in schema.sql)
        create_table_query = """
            CREATE TABLE IF NOT EXISTS health_score_history (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                project_id UUID NOT NULL,
                tenant_id UUID NOT NULL,
                health_score INTEGER NOT NULL,
                velocity_score DECIMAL(5,2),
                backlog_score DECIMAL(5,2),
                milestone_score DECIMAL(5,2),
                risk_score DECIMAL(5,2),
                weights JSONB,
                calculated_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """
        
        try:
            execute_query(create_table_query, fetch=False, commit=True)
        except Exception as e:
            # Table might already exist, continue
            logger.debug(f"Table creation skipped: {str(e)}")
        
        results = execute_query(
            query,
            (
                project_id,
                tenant_id,
                health_score_data['health_score'],
                component_scores['velocity'],
                component_scores['backlog'],
                component_scores['milestones'],
                component_scores['risks'],
                json.dumps(health_score_data['weights']),
                health_score_data['calculated_at']
            ),
            fetch=True,
            commit=True
        )
        
        if results:
            history_id = results[0]['id']
            logger.info(
                f"Health score history stored",
                extra={
                    "project_id": project_id,
                    "history_id": history_id,
                    "health_score": health_score_data['health_score']
                }
            )
            return history_id
        
        raise DataError("Failed to store health score history", data_source="Database")
        
    except Exception as e:
        raise DataError(
            f"Failed to store health score history: {str(e)}",
            data_source="Database"
        )


def get_health_score_history(
    project_id: str,
    tenant_id: str,
    limit: int = 30
) -> List[Dict[str, Any]]:
    """
    Retrieve health score history for a project.
    
    Args:
        project_id: Project ID
        tenant_id: Tenant ID
        limit: Maximum number of history entries to retrieve
        
    Returns:
        List of health score history entries
        
    Raises:
        DataError: If query fails
    """
    query = """
        SELECT 
            id::text,
            health_score,
            velocity_score,
            backlog_score,
            milestone_score,
            risk_score,
            weights,
            calculated_at,
            created_at
        FROM health_score_history
        WHERE project_id = %s AND tenant_id = %s
        ORDER BY calculated_at DESC
        LIMIT %s
    """
    
    try:
        results = execute_query(query, (project_id, tenant_id, limit), fetch=True)
        
        # Convert Decimal to float
        for entry in results:
            if entry.get('velocity_score') is not None:
                entry['velocity_score'] = float(entry['velocity_score'])
            if entry.get('backlog_score') is not None:
                entry['backlog_score'] = float(entry['backlog_score'])
            if entry.get('milestone_score') is not None:
                entry['milestone_score'] = float(entry['milestone_score'])
            if entry.get('risk_score') is not None:
                entry['risk_score'] = float(entry['risk_score'])
            
            # Parse weights JSON
            if entry.get('weights'):
                if isinstance(entry['weights'], str):
                    entry['weights'] = json.loads(entry['weights'])
        
        return results
        
    except Exception as e:
        logger.error(
            f"Failed to retrieve health score history",
            extra={"project_id": project_id, "error": str(e)}
        )
        return []


def get_latest_health_score(project_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    """
    Get the most recent health score for a project.
    
    Args:
        project_id: Project ID
        tenant_id: Tenant ID
        
    Returns:
        Latest health score entry or None
    """
    history = get_health_score_history(project_id, tenant_id, limit=1)
    return history[0] if history else None


def publish_health_score_event(
    project_id: str,
    tenant_id: str,
    health_score_data: Dict[str, Any],
    event_type: str = 'HealthScoreCalculated'
) -> None:
    """
    Publish health score event to EventBridge.
    
    Args:
        project_id: Project ID
        tenant_id: Tenant ID
        health_score_data: Health score calculation result
        event_type: Event type name
    """
    try:
        eventbridge = boto3.client('events')
        
        event_detail = {
            'project_id': project_id,
            'tenant_id': tenant_id,
            'health_score': health_score_data['health_score'],
            'component_scores': health_score_data['component_scores'],
            'calculated_at': health_score_data['calculated_at']
        }
        
        response = eventbridge.put_events(
            Entries=[
                {
                    'Source': 'ai-sw-pm.health-score',
                    'DetailType': event_type,
                    'Detail': json.dumps(event_detail),
                    'EventBusName': 'default'
                }
            ]
        )
        
        if response.get('FailedEntryCount', 0) > 0:
            logger.error(
                f"Failed to publish health score event",
                extra={"response": response}
            )
        else:
            logger.info(
                f"Health score event published",
                extra={
                    "project_id": project_id,
                    "event_type": event_type,
                    "health_score": health_score_data['health_score']
                }
            )
            
    except Exception as e:
        logger.error(
            f"Failed to publish health score event: {str(e)}",
            extra={"project_id": project_id}
        )
        # Don't raise - event publishing is non-critical
