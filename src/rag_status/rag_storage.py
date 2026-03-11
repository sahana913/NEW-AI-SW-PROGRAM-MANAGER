"""RAG status storage and history management."""

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


def store_rag_status(
    project_id: str,
    tenant_id: str,
    rag_status_data: Dict[str, Any]
) -> str:
    """
    Store RAG status in database.
    
    Validates: Property 62 - RAG Status Update Triggering
    
    Args:
        project_id: Project ID
        tenant_id: Tenant ID
        rag_status_data: RAG status calculation result
        
    Returns:
        RAG status entry ID
        
    Raises:
        DataError: If storage fails
    """
    try:
        # Store in RDS for relational queries
        query = """
            INSERT INTO rag_status_history (
                project_id,
                tenant_id,
                rag_status,
                health_score,
                thresholds,
                calculated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id::text
        """
        
        # First, ensure the table exists (in production, this would be in schema.sql)
        create_table_query = """
            CREATE TABLE IF NOT EXISTS rag_status_history (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                project_id UUID NOT NULL,
                tenant_id UUID NOT NULL,
                rag_status VARCHAR(10) NOT NULL,
                health_score INTEGER NOT NULL,
                thresholds JSONB,
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
                rag_status_data['rag_status'],
                rag_status_data['health_score'],
                json.dumps(rag_status_data['thresholds']),
                rag_status_data['calculated_at']
            ),
            fetch=True,
            commit=True
        )
        
        if results:
            status_id = results[0]['id']
            logger.info(
                f"RAG status stored",
                extra={
                    "project_id": project_id,
                    "status_id": status_id,
                    "rag_status": rag_status_data['rag_status']
                }
            )
            return status_id
        
        raise DataError("Failed to store RAG status", data_source="Database")
        
    except Exception as e:
        raise DataError(
            f"Failed to store RAG status: {str(e)}",
            data_source="Database"
        )


def get_rag_status_history(
    project_id: str,
    tenant_id: str,
    limit: int = 30
) -> List[Dict[str, Any]]:
    """
    Retrieve RAG status history for a project.
    
    Args:
        project_id: Project ID
        tenant_id: Tenant ID
        limit: Maximum number of history entries to retrieve
        
    Returns:
        List of RAG status history entries
        
    Raises:
        DataError: If query fails
    """
    query = """
        SELECT 
            id::text,
            rag_status,
            health_score,
            thresholds,
            calculated_at,
            created_at
        FROM rag_status_history
        WHERE project_id = %s AND tenant_id = %s
        ORDER BY calculated_at DESC
        LIMIT %s
    """
    
    try:
        results = execute_query(query, (project_id, tenant_id, limit), fetch=True)
        
        # Parse thresholds JSON
        for entry in results:
            if entry.get('thresholds'):
                if isinstance(entry['thresholds'], str):
                    entry['thresholds'] = json.loads(entry['thresholds'])
        
        return results
        
    except Exception as e:
        logger.error(
            f"Failed to retrieve RAG status history",
            extra={"project_id": project_id, "error": str(e)}
        )
        return []


def get_latest_rag_status(project_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    """
    Get the most recent RAG status for a project.
    
    Args:
        project_id: Project ID
        tenant_id: Tenant ID
        
    Returns:
        Latest RAG status entry or None
    """
    history = get_rag_status_history(project_id, tenant_id, limit=1)
    return history[0] if history else None


def get_previous_rag_status(project_id: str, tenant_id: str) -> Optional[str]:
    """
    Get the previous RAG status for a project (second most recent).
    
    Used to detect status degradation.
    
    Args:
        project_id: Project ID
        tenant_id: Tenant ID
        
    Returns:
        Previous RAG status or None
    """
    history = get_rag_status_history(project_id, tenant_id, limit=2)
    return history[1]['rag_status'] if len(history) > 1 else None


def detect_status_degradation(
    current_status: str,
    previous_status: Optional[str]
) -> bool:
    """
    Detect if RAG status has degraded from Green to Amber/Red.
    
    Validates: Property 63 - RAG Degradation Notification
    
    Args:
        current_status: Current RAG status
        previous_status: Previous RAG status (or None)
        
    Returns:
        True if status degraded from Green to Amber/Red
    """
    if previous_status is None:
        return False
    
    # Degradation occurs when moving from GREEN to AMBER or RED
    if previous_status == 'GREEN' and current_status in ['AMBER', 'RED']:
        return True
    
    return False


def publish_rag_status_event(
    project_id: str,
    tenant_id: str,
    rag_status_data: Dict[str, Any],
    event_type: str = 'RagStatusCalculated'
) -> None:
    """
    Publish RAG status event to EventBridge.
    
    Args:
        project_id: Project ID
        tenant_id: Tenant ID
        rag_status_data: RAG status calculation result
        event_type: Event type name
    """
    try:
        eventbridge = boto3.client('events')
        
        event_detail = {
            'project_id': project_id,
            'tenant_id': tenant_id,
            'rag_status': rag_status_data['rag_status'],
            'health_score': rag_status_data['health_score'],
            'calculated_at': rag_status_data['calculated_at']
        }
        
        response = eventbridge.put_events(
            Entries=[
                {
                    'Source': 'ai-sw-pm.rag-status',
                    'DetailType': event_type,
                    'Detail': json.dumps(event_detail),
                    'EventBusName': 'default'
                }
            ]
        )
        
        if response.get('FailedEntryCount', 0) > 0:
            logger.error(
                f"Failed to publish RAG status event",
                extra={"response": response}
            )
        else:
            logger.info(
                f"RAG status event published",
                extra={
                    "project_id": project_id,
                    "event_type": event_type,
                    "rag_status": rag_status_data['rag_status']
                }
            )
            
    except Exception as e:
        logger.error(
            f"Failed to publish RAG status event: {str(e)}",
            extra={"project_id": project_id}
        )
        # Don't raise - event publishing is non-critical


def publish_degradation_notification(
    project_id: str,
    tenant_id: str,
    current_status: str,
    previous_status: str,
    health_score: int
) -> None:
    """
    Publish notification event when RAG status degrades.
    
    Validates: Property 63 - RAG Degradation Notification
    
    Args:
        project_id: Project ID
        tenant_id: Tenant ID
        current_status: Current RAG status
        previous_status: Previous RAG status
        health_score: Current health score
    """
    try:
        eventbridge = boto3.client('events')
        
        event_detail = {
            'project_id': project_id,
            'tenant_id': tenant_id,
            'current_status': current_status,
            'previous_status': previous_status,
            'health_score': health_score,
            'notification_type': 'RAG_DEGRADATION',
            'severity': 'HIGH' if current_status == 'RED' else 'MEDIUM',
            'message': f"Project RAG status degraded from {previous_status} to {current_status}",
            'timestamp': datetime.utcnow().isoformat()
        }
        
        response = eventbridge.put_events(
            Entries=[
                {
                    'Source': 'ai-sw-pm.rag-status',
                    'DetailType': 'RagStatusDegradation',
                    'Detail': json.dumps(event_detail),
                    'EventBusName': 'default'
                }
            ]
        )
        
        if response.get('FailedEntryCount', 0) > 0:
            logger.error(
                f"Failed to publish degradation notification",
                extra={"response": response}
            )
        else:
            logger.info(
                f"RAG degradation notification published",
                extra={
                    "project_id": project_id,
                    "current_status": current_status,
                    "previous_status": previous_status
                }
            )
            
    except Exception as e:
        logger.error(
            f"Failed to publish degradation notification: {str(e)}",
            extra={"project_id": project_id}
        )
        # Don't raise - notification publishing is non-critical
