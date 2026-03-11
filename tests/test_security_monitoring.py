"""
Unit tests for security monitoring module.

Tests cover:
- Cross-tenant access detection
- Violation logging
- EventBridge event publishing
- SNS alert sending
- DynamoDB storage
- Integration with tenant isolation decorator
"""

import json
import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

# Import modules to test
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from security_monitoring.violation_detector import (
    detect_cross_tenant_access,
    publish_violation_event,
    alert_administrator,
    log_violation_attempt
)
from security_monitoring.handler import (
    lambda_handler,
    store_violation_record,
    get_violations_by_tenant,
    get_violations_by_user
)
from shared.decorators import with_tenant_isolation
from shared.errors import TenantIsolationError


class TestViolationDetector:
    """Test suite for violation detector."""
    
    @patch('security_monitoring.violation_detector.publish_violation_event')
    @patch('security_monitoring.violation_detector.alert_administrator')
    def test_detect_cross_tenant_access_creates_violation(
        self,
        mock_alert,
        mock_publish
    ):
        """Test that cross-tenant access detection creates proper violation record."""
        # Arrange
        user_tenant_id = "tenant-A"
        requested_tenant_id = "tenant-B"
        user_id = "user-123"
        endpoint = "GET /api/projects"
        request_context = {
            'httpMethod': 'GET',
            'path': '/api/projects',
            'requestContext': {
                'identity': {
                    'sourceIp': '192.168.1.1',
                    'userAgent': 'Mozilla/5.0'
                }
            }
        }
        
        mock_publish.return_value = True
        mock_alert.return_value = True
        
        # Act
        result = detect_cross_tenant_access(
            user_tenant_id,
            requested_tenant_id,
            user_id,
            endpoint,
            request_context
        )
        
        # Assert
        assert result['violation_type'] == 'CROSS_TENANT_ACCESS'
        assert result['severity'] == 'CRITICAL'
        assert result['user_id'] == user_id
        assert result['user_tenant_id'] == user_tenant_id
        assert result['requested_tenant_id'] == requested_tenant_id
        assert result['endpoint'] == endpoint
        assert 'violation_id' in result
        assert 'timestamp' in result
        assert result['request_context']['source_ip'] == '192.168.1.1'
        
        # Verify publish and alert were called
        mock_publish.assert_called_once()
        mock_alert.assert_called_once()
    
    @patch('security_monitoring.violation_detector.get_eventbridge_client')
    def test_publish_violation_event_success(self, mock_get_client):
        """Test successful violation event publishing."""
        # Arrange
        mock_eventbridge = Mock()
        mock_eventbridge.put_events.return_value = {
            'FailedEntryCount': 0,
            'Entries': [{'EventId': 'event-123'}]
        }
        mock_get_client.return_value = mock_eventbridge
        
        violation_details = {
            'violation_id': 'VIOLATION-123',
            'violation_type': 'CROSS_TENANT_ACCESS',
            'severity': 'CRITICAL',
            'user_id': 'user-123',
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Act
        result = publish_violation_event(violation_details)
        
        # Assert
        assert result is True
        mock_eventbridge.put_events.assert_called_once()
        call_args = mock_eventbridge.put_events.call_args[1]
        assert call_args['Entries'][0]['Source'] == 'custom.security'
        assert call_args['Entries'][0]['DetailType'] == 'Security Violation'
    
    @patch('security_monitoring.violation_detector.get_eventbridge_client')
    def test_publish_violation_event_failure(self, mock_get_client):
        """Test violation event publishing failure handling."""
        # Arrange
        mock_eventbridge = Mock()
        mock_eventbridge.put_events.return_value = {
            'FailedEntryCount': 1,
            'Entries': [{'ErrorCode': 'InternalError'}]
        }
        mock_get_client.return_value = mock_eventbridge
        
        violation_details = {
            'violation_id': 'VIOLATION-123',
            'violation_type': 'CROSS_TENANT_ACCESS'
        }
        
        # Act
        result = publish_violation_event(violation_details)
        
        # Assert
        assert result is False
    
    @patch('security_monitoring.violation_detector.SECURITY_ALERT_TOPIC_ARN', 'arn:aws:sns:us-east-1:123456789012:security-alerts')
    @patch('security_monitoring.violation_detector.get_sns_client')
    def test_alert_administrator_success(self, mock_get_client):
        """Test successful administrator alert."""
        # Arrange
        mock_sns = Mock()
        mock_sns.publish.return_value = {'MessageId': 'msg-123'}
        mock_get_client.return_value = mock_sns
        
        violation_details = {
            'violation_id': 'VIOLATION-123',
            'violation_type': 'CROSS_TENANT_ACCESS',
            'severity': 'CRITICAL',
            'user_id': 'user-123',
            'user_tenant_id': 'tenant-A',
            'requested_tenant_id': 'tenant-B',
            'endpoint': 'GET /api/projects',
            'timestamp': datetime.utcnow().isoformat(),
            'request_context': {
                'http_method': 'GET',
                'path': '/api/projects',
                'source_ip': '192.168.1.1',
                'user_agent': 'Mozilla/5.0'
            }
        }
        
        # Act
        result = alert_administrator(violation_details)
        
        # Assert
        assert result is True
        mock_sns.publish.assert_called_once()
        call_args = mock_sns.publish.call_args[1]
        assert 'CRITICAL' in call_args['Subject']
        assert 'VIOLATION-123' in call_args['Message']
        assert call_args['MessageAttributes']['severity']['StringValue'] == 'CRITICAL'
    
    @patch('security_monitoring.violation_detector.SECURITY_ALERT_TOPIC_ARN', '')
    @patch('security_monitoring.violation_detector.get_sns_client')
    def test_alert_administrator_no_topic_configured(self, mock_get_client):
        """Test alert when SNS topic is not configured."""
        # Arrange
        violation_details = {'violation_id': 'VIOLATION-123'}
        
        # Act
        result = alert_administrator(violation_details)
        
        # Assert
        assert result is False
        mock_get_client.assert_not_called()
    
    @patch('security_monitoring.violation_detector.SECURITY_ALERT_TOPIC_ARN', 'arn:aws:sns:us-east-1:123456789012:security-alerts')
    @patch('security_monitoring.violation_detector.get_sns_client')
    def test_alert_administrator_sns_error(self, mock_get_client):
        """Test alert when SNS publish fails."""
        # Arrange
        mock_sns = Mock()
        mock_sns.publish.side_effect = ClientError(
            {'Error': {'Code': 'InternalError', 'Message': 'Service error'}},
            'publish'
        )
        mock_get_client.return_value = mock_sns
        
        violation_details = {
            'violation_id': 'VIOLATION-123',
            'violation_type': 'CROSS_TENANT_ACCESS',
            'severity': 'CRITICAL',
            'user_id': 'user-123',
            'user_tenant_id': 'tenant-A',
            'requested_tenant_id': 'tenant-B',
            'endpoint': 'GET /api/projects',
            'timestamp': datetime.utcnow().isoformat(),
            'request_context': {
                'http_method': 'GET',
                'path': '/api/projects',
                'source_ip': '192.168.1.1',
                'user_agent': 'Mozilla/5.0'
            }
        }
        
        # Act
        result = alert_administrator(violation_details)
        
        # Assert
        assert result is False


class TestSecurityMonitoringHandler:
    """Test suite for security monitoring Lambda handler."""
    
    @patch('security_monitoring.handler.store_violation_record')
    def test_lambda_handler_success(self, mock_store):
        """Test successful event processing."""
        # Arrange
        event = {
            'detail': {
                'violation_id': 'VIOLATION-123',
                'violation_type': 'CROSS_TENANT_ACCESS',
                'severity': 'CRITICAL',
                'user_id': 'user-123',
                'timestamp': datetime.utcnow().isoformat()
            }
        }
        context = Mock()
        
        # Act
        result = lambda_handler(event, context)
        
        # Assert
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['violation_id'] == 'VIOLATION-123'
        mock_store.assert_called_once()
    
    def test_lambda_handler_invalid_event(self):
        """Test handler with invalid event format."""
        # Arrange
        event = {}  # No detail
        context = Mock()
        
        # Act
        result = lambda_handler(event, context)
        
        # Assert
        assert result['statusCode'] == 400
    
    @patch('security_monitoring.handler.get_dynamodb_client')
    def test_store_violation_record_success(self, mock_get_client):
        """Test successful violation record storage."""
        # Arrange
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_get_client.return_value = mock_dynamodb
        
        violation_details = {
            'violation_id': 'VIOLATION-123',
            'violation_type': 'CROSS_TENANT_ACCESS',
            'severity': 'CRITICAL',
            'user_id': 'user-123',
            'user_tenant_id': 'tenant-A',
            'requested_tenant_id': 'tenant-B',
            'endpoint': 'GET /api/projects',
            'timestamp': datetime.utcnow().isoformat(),
            'request_context': {}
        }
        
        # Act
        store_violation_record(violation_details)
        
        # Assert
        mock_table.put_item.assert_called_once()
        call_args = mock_table.put_item.call_args[1]
        item = call_args['Item']
        assert item['PK'] == 'VIOLATION#VIOLATION-123'
        assert item['violation_type'] == 'CROSS_TENANT_ACCESS'
        assert item['status'] == 'BLOCKED'
        assert item['GSI1PK'] == 'TENANT#tenant-A'
        assert item['GSI2PK'] == 'USER#user-123'
    
    @patch('security_monitoring.handler.get_dynamodb_client')
    def test_get_violations_by_tenant(self, mock_get_client):
        """Test retrieving violations by tenant."""
        # Arrange
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_table.query.return_value = {
            'Items': [
                {'violation_id': 'VIOLATION-1', 'user_id': 'user-123'},
                {'violation_id': 'VIOLATION-2', 'user_id': 'user-456'}
            ]
        }
        mock_dynamodb.Table.return_value = mock_table
        mock_get_client.return_value = mock_dynamodb
        
        # Act
        result = get_violations_by_tenant('tenant-A', limit=50)
        
        # Assert
        assert len(result) == 2
        assert result[0]['violation_id'] == 'VIOLATION-1'
        mock_table.query.assert_called_once()
        call_args = mock_table.query.call_args[1]
        assert call_args['IndexName'] == 'GSI1'
        assert call_args['Limit'] == 50
    
    @patch('security_monitoring.handler.get_dynamodb_client')
    def test_get_violations_by_user(self, mock_get_client):
        """Test retrieving violations by user."""
        # Arrange
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_table.query.return_value = {
            'Items': [
                {'violation_id': 'VIOLATION-1', 'endpoint': 'GET /api/projects'}
            ]
        }
        mock_dynamodb.Table.return_value = mock_table
        mock_get_client.return_value = mock_dynamodb
        
        # Act
        result = get_violations_by_user('user-123', limit=100)
        
        # Assert
        assert len(result) == 1
        assert result[0]['violation_id'] == 'VIOLATION-1'
        mock_table.query.assert_called_once()
        call_args = mock_table.query.call_args[1]
        assert call_args['IndexName'] == 'GSI2'


class TestTenantIsolationIntegration:
    """Test suite for tenant isolation decorator integration."""
    
    @patch('security_monitoring.violation_detector.detect_cross_tenant_access')
    def test_tenant_isolation_blocks_cross_tenant_access(self, mock_detect):
        """Test that decorator blocks cross-tenant access attempts."""
        # Arrange
        mock_detect.return_value = {
            'violation_id': 'VIOLATION-123',
            'violation_type': 'CROSS_TENANT_ACCESS'
        }
        
        @with_tenant_isolation
        def test_handler(event, context):
            return {'statusCode': 200}
        
        event = {
            'requestContext': {
                'authorizer': {
                    'tenantId': 'tenant-A',
                    'userId': 'user-123'
                }
            },
            'pathParameters': {
                'tenantId': 'tenant-B'  # Different tenant!
            },
            'httpMethod': 'GET',
            'path': '/api/projects'
        }
        context = Mock()
        
        # Act & Assert
        with pytest.raises(TenantIsolationError) as exc_info:
            test_handler(event, context)
        
        assert 'Cross-tenant access attempt detected and blocked' in str(exc_info.value)
        assert exc_info.value.details['violation_id'] == 'VIOLATION-123'
        mock_detect.assert_called_once()
    
    def test_tenant_isolation_allows_same_tenant_access(self):
        """Test that decorator allows access within same tenant."""
        # Arrange
        @with_tenant_isolation
        def test_handler(event, context):
            return {'statusCode': 200, 'tenant_id': event['tenant_id']}
        
        event = {
            'requestContext': {
                'authorizer': {
                    'tenantId': 'tenant-A',
                    'userId': 'user-123'
                }
            },
            'pathParameters': {
                'tenantId': 'tenant-A'  # Same tenant
            },
            'httpMethod': 'GET',
            'path': '/api/projects'
        }
        context = Mock()
        
        # Act
        result = test_handler(event, context)
        
        # Assert
        assert result['statusCode'] == 200
        assert result['tenant_id'] == 'tenant-A'
    
    def test_tenant_isolation_allows_no_tenant_in_request(self):
        """Test that decorator allows requests without tenant parameter."""
        # Arrange
        @with_tenant_isolation
        def test_handler(event, context):
            return {'statusCode': 200, 'tenant_id': event['tenant_id']}
        
        event = {
            'requestContext': {
                'authorizer': {
                    'tenantId': 'tenant-A',
                    'userId': 'user-123'
                }
            },
            'pathParameters': {},
            'httpMethod': 'GET',
            'path': '/api/dashboard'
        }
        context = Mock()
        
        # Act
        result = test_handler(event, context)
        
        # Assert
        assert result['statusCode'] == 200
        assert result['tenant_id'] == 'tenant-A'
    
    def test_tenant_isolation_raises_error_on_missing_context(self):
        """Test that decorator raises error when tenant context is missing."""
        # Arrange
        @with_tenant_isolation
        def test_handler(event, context):
            return {'statusCode': 200}
        
        event = {
            'requestContext': {
                'authorizer': {}  # No tenantId
            },
            'httpMethod': 'GET',
            'path': '/api/projects'
        }
        context = Mock()
        
        # Act & Assert
        with pytest.raises(TenantIsolationError) as exc_info:
            test_handler(event, context)
        
        assert 'Missing tenant context' in str(exc_info.value)


class TestViolationLogging:
    """Test suite for violation logging."""
    
    @patch('security_monitoring.violation_detector.logger')
    def test_log_violation_attempt(self, mock_logger):
        """Test that violations are logged with proper structure."""
        # Arrange
        violation_type = 'CROSS_TENANT_ACCESS'
        user_id = 'user-123'
        tenant_id = 'tenant-A'
        details = {
            'requested_tenant': 'tenant-B',
            'endpoint': 'GET /api/projects'
        }
        
        # Act
        log_violation_attempt(violation_type, user_id, tenant_id, details)
        
        # Assert
        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args
        assert 'Security violation' in call_args[0][0]
        assert call_args[1]['extra']['violation_type'] == violation_type
        assert call_args[1]['extra']['user_id'] == user_id
        assert call_args[1]['extra']['tenant_id'] == tenant_id
        assert 'timestamp' in call_args[1]['extra']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
