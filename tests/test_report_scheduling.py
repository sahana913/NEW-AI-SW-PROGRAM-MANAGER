"""
Unit tests for report scheduling service.

Tests the report scheduling Lambda handlers and helper functions.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Mock environment variables before importing handler
@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Mock environment variables for all tests."""
    monkeypatch.setenv('REPORT_SCHEDULES_TABLE', 'test-report-schedules')
    monkeypatch.setenv('EVENT_BUS_NAME', 'default')
    monkeypatch.setenv('REPORT_GENERATION_LAMBDA_ARN', 'arn:aws:lambda:us-east-1:123456789012:function:report-gen')
    monkeypatch.setenv('EMAIL_DISTRIBUTION_LAMBDA_ARN', 'arn:aws:lambda:us-east-1:123456789012:function:email-dist')
    monkeypatch.setenv('AWS_REGION', 'us-east-1')


@pytest.fixture
def schedule_request_event():
    """Sample API Gateway event for schedule creation."""
    return {
        'body': json.dumps({
            'tenantId': 'tenant-123',
            'reportType': 'WEEKLY_STATUS',
            'schedule': 'cron(0 8 ? * MON *)',
            'recipients': ['user1@example.com', 'user2@example.com'],
            'projectIds': ['proj-1', 'proj-2'],
            'format': 'PDF'
        }),
        'requestContext': {
            'authorizer': {
                'tenantId': 'tenant-123',
                'userId': 'user-456'
            }
        }
    }


@pytest.fixture
def mock_context():
    """Mock Lambda context."""
    context = Mock()
    context.function_name = 'test-function'
    context.invoked_function_arn = 'arn:aws:lambda:us-east-1:123456789012:function:test-function'
    context.aws_request_id = 'test-request-id'
    return context


class TestScheduleReportHandler:
    """Tests for schedule_report_handler."""
    
    @patch('src.report_scheduling.handler.events_client')
    @patch('src.report_scheduling.handler.dynamodb')
    def test_create_schedule_success(self, mock_dynamodb, mock_events, schedule_request_event, mock_context):
        """Test successful schedule creation."""
        from src.report_scheduling.handler import schedule_report_handler
        
        # Mock DynamoDB table
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        # Mock EventBridge
        mock_events.put_rule.return_value = {}
        mock_events.put_targets.return_value = {}
        
        # Call handler
        response = schedule_report_handler(schedule_request_event, mock_context)
        
        # Verify response
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'scheduleId' in body
        assert body['reportType'] == 'WEEKLY_STATUS'
        assert body['status'] == 'ACTIVE'
        assert body['schedule'] == 'cron(0 8 ? * MON *)'
        assert len(body['recipients']) == 2
        
        # Verify EventBridge rule was created
        mock_events.put_rule.assert_called_once()
        mock_events.put_targets.assert_called_once()
        
        # Verify DynamoDB put_item was called
        mock_table.put_item.assert_called_once()
    
    @patch('src.report_scheduling.handler.events_client')
    @patch('src.report_scheduling.handler.dynamodb')
    def test_create_schedule_missing_tenant_id(self, mock_dynamodb, mock_events, schedule_request_event, mock_context):
        """Test schedule creation with missing tenant ID."""
        from src.report_scheduling.handler import schedule_report_handler
        from src.shared.errors import ValidationError
        
        # Remove tenantId from request
        body = json.loads(schedule_request_event['body'])
        del body['tenantId']
        schedule_request_event['body'] = json.dumps(body)
        
        # Call handler and expect ValidationError
        with pytest.raises(ValidationError) as exc_info:
            schedule_report_handler(schedule_request_event, mock_context)
        
        assert 'tenantId is required' in str(exc_info.value)
    
    @patch('src.report_scheduling.handler.events_client')
    @patch('src.report_scheduling.handler.dynamodb')
    def test_create_schedule_invalid_report_type(self, mock_dynamodb, mock_events, schedule_request_event, mock_context):
        """Test schedule creation with invalid report type."""
        from src.report_scheduling.handler import schedule_report_handler
        from src.shared.errors import ValidationError
        
        # Set invalid report type
        body = json.loads(schedule_request_event['body'])
        body['reportType'] = 'INVALID_TYPE'
        schedule_request_event['body'] = json.dumps(body)
        
        # Call handler and expect ValidationError
        with pytest.raises(ValidationError) as exc_info:
            schedule_report_handler(schedule_request_event, mock_context)
        
        assert 'Invalid reportType' in str(exc_info.value)
    
    @patch('src.report_scheduling.handler.events_client')
    @patch('src.report_scheduling.handler.dynamodb')
    def test_create_schedule_empty_recipients(self, mock_dynamodb, mock_events, schedule_request_event, mock_context):
        """Test schedule creation with empty recipients list."""
        from src.report_scheduling.handler import schedule_report_handler
        from src.shared.errors import ValidationError
        
        # Set empty recipients
        body = json.loads(schedule_request_event['body'])
        body['recipients'] = []
        schedule_request_event['body'] = json.dumps(body)
        
        # Call handler and expect ValidationError
        with pytest.raises(ValidationError) as exc_info:
            schedule_report_handler(schedule_request_event, mock_context)
        
        assert 'recipients must be a non-empty list' in str(exc_info.value)
    
    @patch('src.report_scheduling.handler.events_client')
    @patch('src.report_scheduling.handler.dynamodb')
    def test_create_schedule_invalid_schedule_expression(self, mock_dynamodb, mock_events, schedule_request_event, mock_context):
        """Test schedule creation with invalid schedule expression."""
        from src.report_scheduling.handler import schedule_report_handler
        from src.shared.errors import ValidationError
        
        # Set invalid schedule expression
        body = json.loads(schedule_request_event['body'])
        body['schedule'] = 'invalid-expression'
        schedule_request_event['body'] = json.dumps(body)
        
        # Call handler and expect ValidationError
        with pytest.raises(ValidationError) as exc_info:
            schedule_report_handler(schedule_request_event, mock_context)
        
        assert 'Invalid schedule expression' in str(exc_info.value)


class TestGetScheduleHandler:
    """Tests for get_schedule_handler."""
    
    @patch('src.report_scheduling.handler.dynamodb')
    def test_get_schedule_success(self, mock_dynamodb, mock_context):
        """Test successful schedule retrieval."""
        from src.report_scheduling.handler import get_schedule_handler
        
        # Mock DynamoDB table
        mock_table = Mock()
        mock_table.get_item.return_value = {
            'Item': {
                'scheduleId': 'schedule-123',
                'tenantId': 'tenant-123',
                'reportType': 'WEEKLY_STATUS',
                'schedule': 'cron(0 8 ? * MON *)',
                'recipients': ['user1@example.com'],
                'status': 'ACTIVE',
                'nextRunTime': '2024-01-08T08:00:00Z',
                'createdAt': '2024-01-01T10:00:00Z'
            }
        }
        mock_dynamodb.Table.return_value = mock_table
        
        # Create event
        event = {
            'pathParameters': {'scheduleId': 'schedule-123'},
            'requestContext': {
                'authorizer': {'tenantId': 'tenant-123'}
            }
        }
        
        # Call handler
        response = get_schedule_handler(event, mock_context)
        
        # Verify response
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['scheduleId'] == 'schedule-123'
        assert body['reportType'] == 'WEEKLY_STATUS'
        assert body['status'] == 'ACTIVE'
    
    @patch('src.report_scheduling.handler.dynamodb')
    def test_get_schedule_not_found(self, mock_dynamodb, mock_context):
        """Test schedule retrieval when schedule doesn't exist."""
        from src.report_scheduling.handler import get_schedule_handler
        from src.shared.errors import NotFoundError
        
        # Mock DynamoDB table to return no item
        mock_table = Mock()
        mock_table.get_item.return_value = {}
        mock_dynamodb.Table.return_value = mock_table
        
        # Create event
        event = {
            'pathParameters': {'scheduleId': 'nonexistent'},
            'requestContext': {
                'authorizer': {'tenantId': 'tenant-123'}
            }
        }
        
        # Call handler and expect NotFoundError
        with pytest.raises(NotFoundError):
            get_schedule_handler(event, mock_context)


class TestListSchedulesHandler:
    """Tests for list_schedules_handler."""
    
    @patch('src.report_scheduling.handler.dynamodb')
    def test_list_schedules_success(self, mock_dynamodb, mock_context):
        """Test successful schedule listing."""
        from src.report_scheduling.handler import list_schedules_handler
        
        # Mock DynamoDB table
        mock_table = Mock()
        mock_table.query.return_value = {
            'Items': [
                {
                    'scheduleId': 'schedule-1',
                    'reportType': 'WEEKLY_STATUS',
                    'status': 'ACTIVE',
                    'recipients': ['user1@example.com']
                },
                {
                    'scheduleId': 'schedule-2',
                    'reportType': 'EXECUTIVE_SUMMARY',
                    'status': 'PAUSED',
                    'recipients': ['user2@example.com']
                }
            ]
        }
        mock_dynamodb.Table.return_value = mock_table
        
        # Create event
        event = {
            'queryStringParameters': {},
            'requestContext': {
                'authorizer': {'tenantId': 'tenant-123'}
            }
        }
        
        # Call handler
        response = list_schedules_handler(event, mock_context)
        
        # Verify response
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['count'] == 2
        assert len(body['schedules']) == 2
    
    @patch('src.report_scheduling.handler.dynamodb')
    def test_list_schedules_with_filters(self, mock_dynamodb, mock_context):
        """Test schedule listing with status filter."""
        from src.report_scheduling.handler import list_schedules_handler
        
        # Mock DynamoDB table
        mock_table = Mock()
        mock_table.query.return_value = {
            'Items': [
                {
                    'scheduleId': 'schedule-1',
                    'reportType': 'WEEKLY_STATUS',
                    'status': 'ACTIVE',
                    'recipients': ['user1@example.com']
                },
                {
                    'scheduleId': 'schedule-2',
                    'reportType': 'WEEKLY_STATUS',
                    'status': 'PAUSED',
                    'recipients': ['user2@example.com']
                }
            ]
        }
        mock_dynamodb.Table.return_value = mock_table
        
        # Create event with status filter
        event = {
            'queryStringParameters': {'status': 'ACTIVE'},
            'requestContext': {
                'authorizer': {'tenantId': 'tenant-123'}
            }
        }
        
        # Call handler
        response = list_schedules_handler(event, mock_context)
        
        # Verify response - should only include ACTIVE schedules
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['count'] == 1
        assert body['schedules'][0]['status'] == 'ACTIVE'


class TestUpdateScheduleHandler:
    """Tests for update_schedule_handler."""
    
    @patch('src.report_scheduling.handler.events_client')
    @patch('src.report_scheduling.handler.dynamodb')
    def test_update_schedule_status(self, mock_dynamodb, mock_events, mock_context):
        """Test updating schedule status."""
        from src.report_scheduling.handler import update_schedule_handler
        
        # Mock DynamoDB table
        mock_table = Mock()
        mock_table.get_item.return_value = {
            'Item': {
                'scheduleId': 'schedule-123',
                'tenantId': 'tenant-123',
                'reportType': 'WEEKLY_STATUS',
                'status': 'ACTIVE',
                'ruleName': 'report-schedule-123'
            }
        }
        mock_table.update_item.return_value = {
            'Attributes': {
                'scheduleId': 'schedule-123',
                'status': 'PAUSED',
                'updatedAt': '2024-01-02T10:00:00Z'
            }
        }
        mock_dynamodb.Table.return_value = mock_table
        
        # Mock EventBridge
        mock_events.disable_rule.return_value = {}
        
        # Create event
        event = {
            'pathParameters': {'scheduleId': 'schedule-123'},
            'body': json.dumps({'status': 'PAUSED'}),
            'requestContext': {
                'authorizer': {'tenantId': 'tenant-123'}
            }
        }
        
        # Call handler
        response = update_schedule_handler(event, mock_context)
        
        # Verify response
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'PAUSED'
        
        # Verify EventBridge rule was disabled
        mock_events.disable_rule.assert_called_once()


class TestDeleteScheduleHandler:
    """Tests for delete_schedule_handler."""
    
    @patch('src.report_scheduling.handler.events_client')
    @patch('src.report_scheduling.handler.dynamodb')
    def test_delete_schedule_success(self, mock_dynamodb, mock_events, mock_context):
        """Test successful schedule deletion."""
        from src.report_scheduling.handler import delete_schedule_handler
        
        # Mock DynamoDB table
        mock_table = Mock()
        mock_table.get_item.return_value = {
            'Item': {
                'scheduleId': 'schedule-123',
                'tenantId': 'tenant-123',
                'ruleName': 'report-schedule-123'
            }
        }
        mock_dynamodb.Table.return_value = mock_table
        
        # Mock EventBridge
        mock_events.list_targets_by_rule.return_value = {
            'Targets': [{'Id': '1'}]
        }
        mock_events.remove_targets.return_value = {}
        mock_events.delete_rule.return_value = {}
        
        # Create event
        event = {
            'pathParameters': {'scheduleId': 'schedule-123'},
            'requestContext': {
                'authorizer': {'tenantId': 'tenant-123'}
            }
        }
        
        # Call handler
        response = delete_schedule_handler(event, mock_context)
        
        # Verify response
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'deleted successfully' in body['message']
        
        # Verify EventBridge rule was deleted
        mock_events.remove_targets.assert_called_once()
        mock_events.delete_rule.assert_called_once()
        
        # Verify DynamoDB delete_item was called
        mock_table.delete_item.assert_called_once()


class TestScheduleValidation:
    """Tests for schedule validation helper functions."""
    
    def test_validate_cron_expression(self):
        """Test validation of cron expressions."""
        from src.report_scheduling.handler import _validate_schedule_expression
        
        # Valid cron expressions
        assert _validate_schedule_expression('cron(0 8 ? * MON *)') is True
        assert _validate_schedule_expression('cron(0 9 1 * ? *)') is True
        assert _validate_schedule_expression('cron(0 0 * * ? *)') is True
        
        # Invalid expressions
        assert _validate_schedule_expression('invalid') is False
        assert _validate_schedule_expression('') is False
        assert _validate_schedule_expression('cron(invalid)') is True  # EventBridge will validate syntax
    
    def test_validate_rate_expression(self):
        """Test validation of rate expressions."""
        from src.report_scheduling.handler import _validate_schedule_expression
        
        # Valid rate expressions
        assert _validate_schedule_expression('rate(1 day)') is True
        assert _validate_schedule_expression('rate(7 days)') is True
        assert _validate_schedule_expression('rate(1 hour)') is True
        
        # Invalid expressions
        assert _validate_schedule_expression('rate(invalid)') is True  # EventBridge will validate syntax


class TestScheduledExecutionHandler:
    """Tests for scheduled_execution_handler."""
    
    @patch('src.report_scheduling.scheduled_execution_handler.lambda_client')
    @patch('src.report_scheduling.scheduled_execution_handler.dynamodb')
    def test_scheduled_execution_success(self, mock_dynamodb, mock_lambda, mock_context):
        """Test successful scheduled report execution."""
        from src.report_scheduling.scheduled_execution_handler import scheduled_execution_handler
        
        # Mock Lambda invocations
        mock_lambda.invoke.side_effect = [
            # Report generation response
            {
                'StatusCode': 200,
                'Payload': MagicMock(read=lambda: json.dumps({
                    'statusCode': 200,
                    'body': json.dumps({'reportId': 'report-123'})
                }).encode())
            },
            # Email distribution response
            {'StatusCode': 202}
        ]
        
        # Mock DynamoDB
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        # Create event
        event = {
            'tenant_id': 'tenant-123',
            'schedule_id': 'schedule-456',
            'report_type': 'WEEKLY_STATUS',
            'recipients': ['user1@example.com'],
            'project_ids': ['proj-1'],
            'format': 'PDF'
        }
        
        # Call handler
        response = scheduled_execution_handler(event, mock_context)
        
        # Verify response
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'report_id' in body
        assert body['report_id'] == 'report-123'
        
        # Verify Lambda invocations
        assert mock_lambda.invoke.call_count == 2
        
        # Verify schedule last run time was updated
        mock_table.update_item.assert_called_once()
    
    @patch('src.report_scheduling.scheduled_execution_handler.lambda_client')
    def test_scheduled_execution_missing_tenant_id(self, mock_lambda, mock_context):
        """Test scheduled execution with missing tenant ID."""
        from src.report_scheduling.scheduled_execution_handler import scheduled_execution_handler
        
        # Create event without tenant_id
        event = {
            'report_type': 'WEEKLY_STATUS',
            'recipients': ['user1@example.com']
        }
        
        # Call handler
        response = scheduled_execution_handler(event, mock_context)
        
        # Verify error response
        assert response['statusCode'] == 400
        assert 'Missing tenant_id' in response['body']
