"""DynamoDB Streams handler for cache invalidation."""

import sys
import os
import json
from typing import Dict, Any, List

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logger import get_logger
from shared.decorators import with_logging

from .cache_manager import invalidate_project_cache, invalidate_tenant_cache

logger = get_logger()


@with_logging
def handle_dynamodb_stream(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for DynamoDB Streams to invalidate cache on data updates.
    
    Validates: Requirement 20.3 (cache invalidation on data changes)
    
    This handler processes DynamoDB stream events and invalidates relevant
    cache entries when data is updated.
    
    Args:
        event: DynamoDB Streams event
        context: Lambda context
        
    Returns:
        Processing result
    """
    logger.info(f"Processing {len(event.get('Records', []))} DynamoDB stream records")
    
    processed_count = 0
    error_count = 0
    
    for record in event.get('Records', []):
        try:
            process_stream_record(record)
            processed_count += 1
        except Exception as e:
            logger.error(f"Failed to process stream record: {str(e)}")
            error_count += 1
    
    logger.info(
        f"Stream processing completed",
        extra={
            "processed": processed_count,
            "errors": error_count
        }
    )
    
    return {
        "statusCode": 200,
        "body": json.dumps({
            "processed": processed_count,
            "errors": error_count
        })
    }


def process_stream_record(record: Dict[str, Any]) -> None:
    """
    Process a single DynamoDB stream record.
    
    Args:
        record: DynamoDB stream record
    """
    event_name = record.get('eventName')  # INSERT, MODIFY, REMOVE
    table_name = record.get('eventSourceARN', '').split('/')[-3] if 'eventSourceARN' in record else 'unknown'
    
    logger.debug(f"Processing {event_name} event from table: {table_name}")
    
    # Only process MODIFY and INSERT events (data changes)
    if event_name not in ['MODIFY', 'INSERT']:
        return
    
    # Get new image (updated data)
    new_image = record.get('dynamodb', {}).get('NewImage', {})
    
    if not new_image:
        return
    
    # Extract tenant_id and project_id from the record
    tenant_id = extract_attribute_value(new_image.get('tenant_id'))
    project_id = extract_attribute_value(new_image.get('project_id'))
    
    # Determine which cache to invalidate based on table
    if 'Risks' in table_name:
        invalidate_risk_cache(tenant_id, project_id)
    elif 'Predictions' in table_name:
        invalidate_prediction_cache(tenant_id, project_id)
    elif 'health_score' in table_name.lower():
        invalidate_health_score_cache(tenant_id, project_id)
    else:
        # For other tables, invalidate general project cache
        if tenant_id and project_id:
            invalidate_project_cache(tenant_id, project_id)


def extract_attribute_value(attribute: Dict[str, Any]) -> str:
    """
    Extract value from DynamoDB attribute format.
    
    DynamoDB stream records use format like: {'S': 'value'} or {'N': '123'}
    
    Args:
        attribute: DynamoDB attribute dictionary
        
    Returns:
        Extracted value as string
    """
    if not attribute:
        return ''
    
    # Handle different DynamoDB types
    if 'S' in attribute:
        return attribute['S']
    elif 'N' in attribute:
        return attribute['N']
    elif 'BOOL' in attribute:
        return str(attribute['BOOL'])
    elif 'NULL' in attribute:
        return ''
    
    return ''


def invalidate_risk_cache(tenant_id: str, project_id: str) -> None:
    """
    Invalidate cache when risk data changes.
    
    Args:
        tenant_id: Tenant ID
        project_id: Project ID
    """
    if not tenant_id or not project_id:
        return
    
    logger.info(
        f"Invalidating risk cache",
        extra={"tenant_id": tenant_id, "project_id": project_id}
    )
    
    # Invalidate project dashboard cache (includes risks)
    count = invalidate_project_cache(tenant_id, project_id)
    
    logger.info(f"Invalidated {count} cache entries for risk update")


def invalidate_prediction_cache(tenant_id: str, project_id: str) -> None:
    """
    Invalidate cache when prediction data changes.
    
    Args:
        tenant_id: Tenant ID
        project_id: Project ID
    """
    if not tenant_id or not project_id:
        return
    
    logger.info(
        f"Invalidating prediction cache",
        extra={"tenant_id": tenant_id, "project_id": project_id}
    )
    
    # Invalidate project dashboard cache (includes predictions)
    count = invalidate_project_cache(tenant_id, project_id)
    
    logger.info(f"Invalidated {count} cache entries for prediction update")


def invalidate_health_score_cache(tenant_id: str, project_id: str) -> None:
    """
    Invalidate cache when health score changes.
    
    Args:
        tenant_id: Tenant ID
        project_id: Project ID
    """
    if not tenant_id or not project_id:
        return
    
    logger.info(
        f"Invalidating health score cache",
        extra={"tenant_id": tenant_id, "project_id": project_id}
    )
    
    # Invalidate both project and overview caches (health score affects both)
    count = invalidate_project_cache(tenant_id, project_id)
    
    logger.info(f"Invalidated {count} cache entries for health score update")
