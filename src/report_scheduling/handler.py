"""
Report Scheduling Lambda Handler

This Lambda function manages scheduled report generation and distribution.
It creates, updates, and manages EventBridge rules for automated report generation.

Validates: Requirements 14.1, 17.1, 17.5
"""

import json
import os
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

import boto3
from botocore.exceptions import ClientError

from src.shared.logger import get_logger
from src.shared.decorators import with_error_handling, with_audit_logging
from src.shared.errors import ValidationError, NotFoundError

logger = get_logger(__name__)

# Environment variables
REPORT_SCHEDULES_TABLE = os.environ.get('REPORT_SCHEDULES_TABLE', 'ai-sw-pm-report-schedules')
EVENT_BUS_NAME = os.environ.get('EVENT_BUS_NAME', 'default')
REPORT_GENERATION_LAMBDA_ARN = os.environ.get('REPORT_GENERATION_LAMBDA_ARN')
EMAIL_DISTRIBUTION_LAMBDA_ARN = os.environ.get('EMAIL_DISTRIBUTION_LAMBDA_ARN')

# AWS clients
dynamodb = boto3.resource('dynamodb')
events_client = boto3.client('events')
lambda_client = boto3.client('lambda')


@with_error_handling
@with_audit_logging
def schedule_report_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for creating a scheduled report.
    
    Validates: Requirements 14.1, 17.1, 17.5
    
    Request body:
    {
        "tenantId": "tenant-123",
        "reportType": "WEEKLY_STATUS",
        "schedule": "cron(0 8 ? * MON *)",  // Every Monday at 8:00 AM UTC
        "recipients": ["user1@example.com", "user2@example.com"],
        "projectIds": ["proj-1", "proj-2"],  // Optional
        "format": "PDF"  // Optional, default PDF
    }
    
    Returns:
        API Gateway response with schedule details
    """
    logger.info("Schedule report Lambda invoked", extra={"event": event})
    
    # Parse request body
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError as e:
        raise ValidationError(f"Invalid JSON in request body: {str(e)}")
    
    tenant_id = body.get('tenantId')
    report_type = body.get('reportType')
    schedule = body.get('schedule')
    recipients = body.get('recipients', [])
    project_ids = body.get('projectIds')
    format_type = body.get('format', 'PDF')
    
    # Validate required fields
    if not tenant_id:
        raise ValidationError("tenantId is required")
    
    if not report_type:
        raise ValidationError("reportType is required")
    
    if report_type not in ['WEEKLY_STATUS', 'EXECUTIVE_SUMMARY']:
        raise ValidationError(f"Invalid reportType: {report_type}")
    
    if not schedule:
        raise ValidationError("schedule is required")
    
    if not recipients or not isinstance(recipients, list):
        raise ValidationError("recipients must be a non-empty list")
    
    # Validate schedule format (cron or rate expression)
    if not _validate_schedule_expression(schedule):
        raise ValidationError(f"Invalid schedule expression: {schedule}")
    
    logger.info(
        f"Creating schedule for {report_type} report",
        extra={
            "tenant_id": tenant_id,
            "report_type": report_type,
            "schedule": schedule,
            "recipient_count": len(recipients)
        }
    )
    
    try:
        # Generate schedule ID
        schedule_id = str(uuid.uuid4())
        
        # Create EventBridge rule
        rule_name = f"report-schedule-{schedule_id}"
        _create_eventbridge_rule(
            rule_name=rule_name,
            schedule_expression=schedule,
            tenant_id=tenant_id,
            schedule_id=schedule_id,
            report_type=report_type,
            recipients=recipients,
            project_ids=project_ids,
            format_type=format_type
        )
        
        # Calculate next run time
        next_run_time = _calculate_next_run_time(schedule)
        
        # Store schedule in DynamoDB
        schedule_data = _store_schedule(
            tenant_id=tenant_id,
            schedule_id=schedule_id,
            report_type=report_type,
            schedule=schedule,
            recipients=recipients,
            project_ids=project_ids,
            format_type=format_type,
            rule_name=rule_name,
            next_run_time=next_run_time
        )
        
        logger.info(
            f"Schedule created successfully: {schedule_id}",
            extra={
                "schedule_id": schedule_id,
                "tenant_id": tenant_id,
                "next_run_time": next_run_time
            }
        )
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'scheduleId': schedule_id,
                'reportType': report_type,
                'schedule': schedule,
                'recipients': recipients,
                'projectIds': project_ids,
                'format': format_type,
                'status': 'ACTIVE',
                'nextRunTime': next_run_time,
                'createdAt': schedule_data.get('createdAt')
            })
        }
        
    except Exception as e:
        logger.error(
            f"Failed to create schedule: {str(e)}",
            extra={"tenant_id": tenant_id, "error": str(e)}
        )
        raise


@with_error_handling
@with_audit_logging
def get_schedule_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for retrieving a schedule.
    
    Path parameters:
    - scheduleId: Schedule ID to retrieve
    
    Returns:
        API Gateway response with schedule details
    """
    logger.info("Get schedule Lambda invoked", extra={"event": event})
    
    # Extract path parameters
    path_params = event.get('pathParameters', {})
    schedule_id = path_params.get('scheduleId')
    
    # Extract tenant_id from authorizer context
    authorizer_context = event.get('requestContext', {}).get('authorizer', {})
    tenant_id = authorizer_context.get('tenantId')
    
    if not schedule_id:
        raise ValidationError("scheduleId is required")
    
    if not tenant_id:
        raise ValidationError("tenantId is required")
    
    logger.info(
        f"Retrieving schedule {schedule_id}",
        extra={"schedule_id": schedule_id, "tenant_id": tenant_id}
    )
    
    try:
        schedule_data = _get_schedule(tenant_id, schedule_id)
        
        if not schedule_data:
            raise NotFoundError(f"Schedule {schedule_id} not found")
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'scheduleId': schedule_data.get('scheduleId'),
                'reportType': schedule_data.get('reportType'),
                'schedule': schedule_data.get('schedule'),
                'recipients': schedule_data.get('recipients', []),
                'projectIds': schedule_data.get('projectIds'),
                'format': schedule_data.get('format'),
                'status': schedule_data.get('status'),
                'nextRunTime': schedule_data.get('nextRunTime'),
                'lastRunTime': schedule_data.get('lastRunTime'),
                'createdAt': schedule_data.get('createdAt')
            })
        }
        
    except Exception as e:
        logger.error(
            f"Failed to retrieve schedule: {str(e)}",
            extra={"schedule_id": schedule_id, "tenant_id": tenant_id, "error": str(e)}
        )
        raise


@with_error_handling
@with_audit_logging
def list_schedules_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for listing schedules.
    
    Query parameters:
    - status (optional): Filter by status (ACTIVE, PAUSED)
    - reportType (optional): Filter by report type
    
    Returns:
        API Gateway response with schedule list
    """
    logger.info("List schedules Lambda invoked", extra={"event": event})
    
    # Extract tenant_id from authorizer context
    authorizer_context = event.get('requestContext', {}).get('authorizer', {})
    tenant_id = authorizer_context.get('tenantId')
    
    if not tenant_id:
        raise ValidationError("tenantId is required")
    
    # Extract query parameters
    query_params = event.get('queryStringParameters') or {}
    status_filter = query_params.get('status')
    report_type_filter = query_params.get('reportType')
    
    logger.info(
        "Listing schedules",
        extra={
            "tenant_id": tenant_id,
            "status_filter": status_filter,
            "report_type_filter": report_type_filter
        }
    )
    
    try:
        schedules = _list_schedules(tenant_id, status_filter, report_type_filter)
        
        formatted_schedules = [
            {
                'scheduleId': s.get('scheduleId'),
                'reportType': s.get('reportType'),
                'schedule': s.get('schedule'),
                'recipients': s.get('recipients', []),
                'status': s.get('status'),
                'nextRunTime': s.get('nextRunTime'),
                'lastRunTime': s.get('lastRunTime')
            }
            for s in schedules
        ]
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'schedules': formatted_schedules,
                'count': len(formatted_schedules)
            })
        }
        
    except Exception as e:
        logger.error(
            f"Failed to list schedules: {str(e)}",
            extra={"tenant_id": tenant_id, "error": str(e)}
        )
        raise


@with_error_handling
@with_audit_logging
def update_schedule_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for updating a schedule.
    
    Path parameters:
    - scheduleId: Schedule ID to update
    
    Request body:
    {
        "status": "PAUSED",  // Optional: ACTIVE or PAUSED
        "recipients": ["new@example.com"],  // Optional
        "schedule": "cron(0 9 ? * MON *)"  // Optional
    }
    
    Returns:
        API Gateway response with updated schedule details
    """
    logger.info("Update schedule Lambda invoked", extra={"event": event})
    
    # Extract path parameters
    path_params = event.get('pathParameters', {})
    schedule_id = path_params.get('scheduleId')
    
    # Extract tenant_id from authorizer context
    authorizer_context = event.get('requestContext', {}).get('authorizer', {})
    tenant_id = authorizer_context.get('tenantId')
    
    if not schedule_id:
        raise ValidationError("scheduleId is required")
    
    if not tenant_id:
        raise ValidationError("tenantId is required")
    
    # Parse request body
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError as e:
        raise ValidationError(f"Invalid JSON in request body: {str(e)}")
    
    new_status = body.get('status')
    new_recipients = body.get('recipients')
    new_schedule = body.get('schedule')
    
    logger.info(
        f"Updating schedule {schedule_id}",
        extra={
            "schedule_id": schedule_id,
            "tenant_id": tenant_id,
            "new_status": new_status
        }
    )
    
    try:
        # Get existing schedule
        schedule_data = _get_schedule(tenant_id, schedule_id)
        
        if not schedule_data:
            raise NotFoundError(f"Schedule {schedule_id} not found")
        
        # Update fields
        updates = {}
        
        if new_status:
            if new_status not in ['ACTIVE', 'PAUSED']:
                raise ValidationError(f"Invalid status: {new_status}")
            updates['status'] = new_status
            
            # Enable/disable EventBridge rule
            rule_name = schedule_data.get('ruleName')
            if rule_name:
                if new_status == 'ACTIVE':
                    events_client.enable_rule(Name=rule_name)
                else:
                    events_client.disable_rule(Name=rule_name)
        
        if new_recipients:
            if not isinstance(new_recipients, list):
                raise ValidationError("recipients must be a list")
            updates['recipients'] = new_recipients
        
        if new_schedule:
            if not _validate_schedule_expression(new_schedule):
                raise ValidationError(f"Invalid schedule expression: {new_schedule}")
            updates['schedule'] = new_schedule
            
            # Update EventBridge rule
            rule_name = schedule_data.get('ruleName')
            if rule_name:
                events_client.put_rule(
                    Name=rule_name,
                    ScheduleExpression=new_schedule,
                    State='ENABLED' if schedule_data.get('status') == 'ACTIVE' else 'DISABLED'
                )
                updates['nextRunTime'] = _calculate_next_run_time(new_schedule)
        
        # Update DynamoDB
        updated_schedule = _update_schedule(tenant_id, schedule_id, updates)
        
        logger.info(
            f"Schedule updated successfully: {schedule_id}",
            extra={"schedule_id": schedule_id, "tenant_id": tenant_id}
        )
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'scheduleId': updated_schedule.get('scheduleId'),
                'reportType': updated_schedule.get('reportType'),
                'schedule': updated_schedule.get('schedule'),
                'recipients': updated_schedule.get('recipients', []),
                'status': updated_schedule.get('status'),
                'nextRunTime': updated_schedule.get('nextRunTime'),
                'updatedAt': updated_schedule.get('updatedAt')
            })
        }
        
    except Exception as e:
        logger.error(
            f"Failed to update schedule: {str(e)}",
            extra={"schedule_id": schedule_id, "tenant_id": tenant_id, "error": str(e)}
        )
        raise


@with_error_handling
@with_audit_logging
def delete_schedule_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for deleting a schedule.
    
    Path parameters:
    - scheduleId: Schedule ID to delete
    
    Returns:
        API Gateway response confirming deletion
    """
    logger.info("Delete schedule Lambda invoked", extra={"event": event})
    
    # Extract path parameters
    path_params = event.get('pathParameters', {})
    schedule_id = path_params.get('scheduleId')
    
    # Extract tenant_id from authorizer context
    authorizer_context = event.get('requestContext', {}).get('authorizer', {})
    tenant_id = authorizer_context.get('tenantId')
    
    if not schedule_id:
        raise ValidationError("scheduleId is required")
    
    if not tenant_id:
        raise ValidationError("tenantId is required")
    
    logger.info(
        f"Deleting schedule {schedule_id}",
        extra={"schedule_id": schedule_id, "tenant_id": tenant_id}
    )
    
    try:
        # Get existing schedule
        schedule_data = _get_schedule(tenant_id, schedule_id)
        
        if not schedule_data:
            raise NotFoundError(f"Schedule {schedule_id} not found")
        
        # Delete EventBridge rule
        rule_name = schedule_data.get('ruleName')
        if rule_name:
            try:
                # Remove targets first
                targets_response = events_client.list_targets_by_rule(Rule=rule_name)
                if targets_response.get('Targets'):
                    target_ids = [t['Id'] for t in targets_response['Targets']]
                    events_client.remove_targets(Rule=rule_name, Ids=target_ids)
                
                # Delete rule
                events_client.delete_rule(Name=rule_name)
                
                logger.info(
                    f"Deleted EventBridge rule: {rule_name}",
                    extra={"rule_name": rule_name}
                )
            except ClientError as e:
                logger.warning(
                    f"Failed to delete EventBridge rule: {str(e)}",
                    extra={"rule_name": rule_name, "error": str(e)}
                )
        
        # Delete from DynamoDB
        _delete_schedule(tenant_id, schedule_id)
        
        logger.info(
            f"Schedule deleted successfully: {schedule_id}",
            extra={"schedule_id": schedule_id, "tenant_id": tenant_id}
        )
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'message': 'Schedule deleted successfully',
                'scheduleId': schedule_id
            })
        }
        
    except Exception as e:
        logger.error(
            f"Failed to delete schedule: {str(e)}",
            extra={"schedule_id": schedule_id, "tenant_id": tenant_id, "error": str(e)}
        )
        raise


# Helper functions

def _validate_schedule_expression(schedule: str) -> bool:
    """
    Validate EventBridge schedule expression.
    
    Args:
        schedule: Schedule expression (cron or rate)
        
    Returns:
        True if valid, False otherwise
    """
    if not schedule:
        return False
    
    # Check if it's a cron or rate expression
    if schedule.startswith('cron(') and schedule.endswith(')'):
        return True
    
    if schedule.startswith('rate(') and schedule.endswith(')'):
        return True
    
    return False


def _create_eventbridge_rule(
    rule_name: str,
    schedule_expression: str,
    tenant_id: str,
    schedule_id: str,
    report_type: str,
    recipients: List[str],
    project_ids: Optional[List[str]],
    format_type: str
) -> None:
    """
    Create EventBridge rule for scheduled report generation.
    
    Args:
        rule_name: EventBridge rule name
        schedule_expression: Cron or rate expression
        tenant_id: Tenant ID
        schedule_id: Schedule ID
        report_type: Report type
        recipients: List of recipient email addresses
        project_ids: Optional list of project IDs
        format_type: Report format
    """
    # Create rule
    events_client.put_rule(
        Name=rule_name,
        ScheduleExpression=schedule_expression,
        State='ENABLED',
        Description=f"Scheduled {report_type} report for tenant {tenant_id}"
    )
    
    # Add Lambda target (email distribution Lambda)
    target_input = {
        'tenant_id': tenant_id,
        'schedule_id': schedule_id,
        'report_type': report_type,
        'recipients': recipients,
        'project_ids': project_ids,
        'format': format_type
    }
    
    events_client.put_targets(
        Rule=rule_name,
        Targets=[
            {
                'Id': '1',
                'Arn': EMAIL_DISTRIBUTION_LAMBDA_ARN,
                'Input': json.dumps(target_input)
            }
        ]
    )
    
    logger.info(
        f"Created EventBridge rule: {rule_name}",
        extra={"rule_name": rule_name, "schedule": schedule_expression}
    )


def _calculate_next_run_time(schedule: str) -> str:
    """
    Calculate next run time from schedule expression.
    
    This is a simplified implementation. In production, use a library
    like croniter for accurate cron parsing.
    
    Args:
        schedule: Schedule expression
        
    Returns:
        ISO 8601 timestamp of next run
    """
    # For now, return a placeholder
    # In production, parse the cron/rate expression and calculate next run
    from datetime import datetime, timedelta
    
    # Simple heuristic: assume next run is tomorrow at the same time
    next_run = datetime.utcnow() + timedelta(days=1)
    return next_run.isoformat() + 'Z'


def _store_schedule(
    tenant_id: str,
    schedule_id: str,
    report_type: str,
    schedule: str,
    recipients: List[str],
    project_ids: Optional[List[str]],
    format_type: str,
    rule_name: str,
    next_run_time: str
) -> Dict[str, Any]:
    """
    Store schedule in DynamoDB.
    
    Args:
        tenant_id: Tenant ID
        schedule_id: Schedule ID
        report_type: Report type
        schedule: Schedule expression
        recipients: List of recipients
        project_ids: Optional list of project IDs
        format_type: Report format
        rule_name: EventBridge rule name
        next_run_time: Next run time
        
    Returns:
        Stored schedule data
    """
    table = dynamodb.Table(REPORT_SCHEDULES_TABLE)
    
    timestamp = datetime.utcnow().isoformat() + 'Z'
    
    item = {
        'PK': f"TENANT#{tenant_id}",
        'SK': f"SCHEDULE#{schedule_id}",
        'scheduleId': schedule_id,
        'tenantId': tenant_id,
        'reportType': report_type,
        'schedule': schedule,
        'recipients': recipients,
        'format': format_type,
        'status': 'ACTIVE',
        'ruleName': rule_name,
        'nextRunTime': next_run_time,
        'createdAt': timestamp,
        'updatedAt': timestamp
    }
    
    if project_ids:
        item['projectIds'] = project_ids
    
    table.put_item(Item=item)
    
    logger.info(
        f"Stored schedule in DynamoDB: {schedule_id}",
        extra={"schedule_id": schedule_id, "tenant_id": tenant_id}
    )
    
    return item


def _get_schedule(tenant_id: str, schedule_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve schedule from DynamoDB.
    
    Args:
        tenant_id: Tenant ID
        schedule_id: Schedule ID
        
    Returns:
        Schedule data or None if not found
    """
    table = dynamodb.Table(REPORT_SCHEDULES_TABLE)
    
    try:
        response = table.get_item(
            Key={
                'PK': f"TENANT#{tenant_id}",
                'SK': f"SCHEDULE#{schedule_id}"
            }
        )
        
        return response.get('Item')
        
    except ClientError as e:
        logger.error(
            f"Failed to retrieve schedule: {str(e)}",
            extra={"schedule_id": schedule_id, "tenant_id": tenant_id}
        )
        return None


def _list_schedules(
    tenant_id: str,
    status_filter: Optional[str] = None,
    report_type_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    List schedules for a tenant.
    
    Args:
        tenant_id: Tenant ID
        status_filter: Optional status filter
        report_type_filter: Optional report type filter
        
    Returns:
        List of schedules
    """
    table = dynamodb.Table(REPORT_SCHEDULES_TABLE)
    
    try:
        response = table.query(
            KeyConditionExpression='PK = :pk AND begins_with(SK, :sk_prefix)',
            ExpressionAttributeValues={
                ':pk': f"TENANT#{tenant_id}",
                ':sk_prefix': 'SCHEDULE#'
            }
        )
        
        schedules = response.get('Items', [])
        
        # Apply filters
        if status_filter:
            schedules = [s for s in schedules if s.get('status') == status_filter]
        
        if report_type_filter:
            schedules = [s for s in schedules if s.get('reportType') == report_type_filter]
        
        return schedules
        
    except ClientError as e:
        logger.error(
            f"Failed to list schedules: {str(e)}",
            extra={"tenant_id": tenant_id}
        )
        return []


def _update_schedule(
    tenant_id: str,
    schedule_id: str,
    updates: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Update schedule in DynamoDB.
    
    Args:
        tenant_id: Tenant ID
        schedule_id: Schedule ID
        updates: Dictionary of fields to update
        
    Returns:
        Updated schedule data
    """
    table = dynamodb.Table(REPORT_SCHEDULES_TABLE)
    
    timestamp = datetime.utcnow().isoformat() + 'Z'
    updates['updatedAt'] = timestamp
    
    # Build update expression
    update_expr_parts = []
    expr_attr_values = {}
    
    for key, value in updates.items():
        update_expr_parts.append(f"{key} = :{key}")
        expr_attr_values[f":{key}"] = value
    
    update_expression = "SET " + ", ".join(update_expr_parts)
    
    try:
        response = table.update_item(
            Key={
                'PK': f"TENANT#{tenant_id}",
                'SK': f"SCHEDULE#{schedule_id}"
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expr_attr_values,
            ReturnValues='ALL_NEW'
        )
        
        return response.get('Attributes', {})
        
    except ClientError as e:
        logger.error(
            f"Failed to update schedule: {str(e)}",
            extra={"schedule_id": schedule_id, "tenant_id": tenant_id}
        )
        raise


def _delete_schedule(tenant_id: str, schedule_id: str) -> None:
    """
    Delete schedule from DynamoDB.
    
    Args:
        tenant_id: Tenant ID
        schedule_id: Schedule ID
    """
    table = dynamodb.Table(REPORT_SCHEDULES_TABLE)
    
    try:
        table.delete_item(
            Key={
                'PK': f"TENANT#{tenant_id}",
                'SK': f"SCHEDULE#{schedule_id}"
            }
        )
        
        logger.info(
            f"Deleted schedule from DynamoDB: {schedule_id}",
            extra={"schedule_id": schedule_id, "tenant_id": tenant_id}
        )
        
    except ClientError as e:
        logger.error(
            f"Failed to delete schedule: {str(e)}",
            extra={"schedule_id": schedule_id, "tenant_id": tenant_id}
        )
        raise
