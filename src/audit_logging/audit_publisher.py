"""
Audit Event Publisher

Helper module for publishing audit events to EventBridge for processing
by the audit logging Lambda.
"""

import json
import os
from typing import Any, Dict, Optional
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

from shared.logger import get_logger, log_error

logger = get_logger("audit-publisher")

# Initialize EventBridge client lazily
_eventbridge = None

def get_eventbridge_client():
    """Get or create EventBridge client."""
    global _eventbridge
    if _eventbridge is None:
        _eventbridge = boto3.client('events')
    return _eventbridge

EVENT_BUS_NAME = os.environ.get('EVENT_BUS_NAME', 'default')


def publish_authentication_event(
    user_id: str,
    email: str,
    success: bool,
    reason: Optional[str] = None
) -> bool:
    """
    Publish an authentication event to EventBridge.
    
    Args:
        user_id: User attempting authentication
        email: User email
        success: Whether authentication succeeded
        reason: Failure reason if applicable
        
    Returns:
        True if event published successfully, False otherwise
    """
    try:
        eventbridge = get_eventbridge_client()
        
        event = {
            'Source': 'aws.cognito',
            'DetailType': 'Authentication Attempt',
            'Detail': json.dumps({
                'userId': user_id,
                'email': email,
                'success': success,
                'reason': reason,
                'timestamp': datetime.utcnow().isoformat()
            }),
            'EventBusName': EVENT_BUS_NAME
        }
        
        response = eventbridge.put_events(Entries=[event])
        
        if response['FailedEntryCount'] > 0:
            logger.error(
                "Failed to publish authentication event",
                extra={
                    'user_id': user_id,
                    'failed_entries': response['Entries']
                }
            )
            return False
        
        return True
        
    except ClientError as e:
        log_error(logger, e, context={
            'function': 'publish_authentication_event',
            'user_id': user_id
        })
        return False


def publish_data_modification_event(
    user_id: str,
    tenant_id: str,
    operation_type: str,
    entity_type: str,
    entity_id: str,
    changes: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Publish a data modification event to EventBridge.
    
    Args:
        user_id: User performing the modification
        tenant_id: Tenant context
        operation_type: Type of operation (CREATE, UPDATE, DELETE)
        entity_type: Type of entity modified
        entity_id: Identifier of modified entity
        changes: Details of changes made
        
    Returns:
        True if event published successfully, False otherwise
    """
    try:
        eventbridge = get_eventbridge_client()
        
        event = {
            'Source': 'custom.datamodification',
            'DetailType': 'Data Modification',
            'Detail': json.dumps({
                'userId': user_id,
                'tenantId': tenant_id,
                'operationType': operation_type,
                'entityType': entity_type,
                'entityId': entity_id,
                'changes': changes,
                'timestamp': datetime.utcnow().isoformat()
            }),
            'EventBusName': EVENT_BUS_NAME
        }
        
        response = eventbridge.put_events(Entries=[event])
        
        if response['FailedEntryCount'] > 0:
            logger.error(
                "Failed to publish data modification event",
                extra={
                    'user_id': user_id,
                    'entity_id': entity_id,
                    'failed_entries': response['Entries']
                }
            )
            return False
        
        return True
        
    except ClientError as e:
        log_error(logger, e, context={
            'function': 'publish_data_modification_event',
            'user_id': user_id,
            'entity_id': entity_id
        })
        return False


def publish_admin_action_event(
    admin_user_id: str,
    action_type: str,
    affected_entities: Dict[str, Any],
    details: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Publish an administrative action event to EventBridge.
    
    Args:
        admin_user_id: Administrator performing the action
        action_type: Type of administrative action
        affected_entities: Entities affected by the action
        details: Additional action details
        
    Returns:
        True if event published successfully, False otherwise
    """
    try:
        eventbridge = get_eventbridge_client()
        
        event = {
            'Source': 'custom.adminaction',
            'DetailType': 'Administrative Action',
            'Detail': json.dumps({
                'adminUserId': admin_user_id,
                'actionType': action_type,
                'affectedEntities': affected_entities,
                'details': details,
                'timestamp': datetime.utcnow().isoformat()
            }),
            'EventBusName': EVENT_BUS_NAME
        }
        
        response = eventbridge.put_events(Entries=[event])
        
        if response['FailedEntryCount'] > 0:
            logger.error(
                "Failed to publish admin action event",
                extra={
                    'admin_user_id': admin_user_id,
                    'action_type': action_type,
                    'failed_entries': response['Entries']
                }
            )
            return False
        
        return True
        
    except ClientError as e:
        log_error(logger, e, context={
            'function': 'publish_admin_action_event',
            'admin_user_id': admin_user_id,
            'action_type': action_type
        })
        return False



def publish_security_violation_event(
    violation_id: str,
    violation_type: str,
    user_id: str,
    user_tenant_id: str,
    requested_tenant_id: str,
    endpoint: str,
    request_context: Dict[str, Any]
) -> bool:
    """
    Publish a security violation event to EventBridge.
    
    Validates: Requirement 25.6 - Security violation detection and alerting
    
    Args:
        violation_id: Unique identifier for the violation
        violation_type: Type of security violation
        user_id: User who attempted the violation
        user_tenant_id: Tenant ID from user's context
        requested_tenant_id: Tenant ID that was requested
        endpoint: API endpoint accessed
        request_context: Full request context
        
    Returns:
        True if event published successfully, False otherwise
    """
    try:
        eventbridge = get_eventbridge_client()
        
        event = {
            'Source': 'custom.security',
            'DetailType': 'Security Violation',
            'Detail': json.dumps({
                'violation_id': violation_id,
                'violation_type': violation_type,
                'severity': 'CRITICAL',
                'user_id': user_id,
                'user_tenant_id': user_tenant_id,
                'requested_tenant_id': requested_tenant_id,
                'endpoint': endpoint,
                'timestamp': datetime.utcnow().isoformat(),
                'request_context': request_context
            }),
            'EventBusName': EVENT_BUS_NAME
        }
        
        response = eventbridge.put_events(Entries=[event])
        
        if response['FailedEntryCount'] > 0:
            logger.error(
                "Failed to publish security violation event",
                extra={
                    'violation_id': violation_id,
                    'failed_entries': response['Entries']
                }
            )
            return False
        
        return True
        
    except ClientError as e:
        log_error(logger, e, context={
            'function': 'publish_security_violation_event',
            'violation_id': violation_id
        })
        return False
