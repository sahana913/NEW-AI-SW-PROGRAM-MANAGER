"""
Tests for audit logging service.

Validates Requirements 27.1, 27.2, 28.1, 28.2, 28.3
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Import the handler
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from audit_logging.handler import (
    handler,
    process_authentication_event,
    process_data_modification_event,
    process_admin_action_event
)
from audit_logging.audit_publisher import (
    publish_authentication_event,
    publish_data_modification_event,
    publish_admin_action_event
)


class TestAuditLoggingHandler:
    """Test suite for audit logging Lambda handler."""
    
    def test_authentication_event_success(self):
        """Test logging successful authentication attempt."""
        event = {
            "source": "aws.cognito",
            "detail": {
                "userId": "user-123",
                "email": "test@example.com",
                "success": True
            }
        }
        
        context = Mock()
        context.request_id = "req-123"
        
        with patch('audit_logging.handler.log_authentication_attempt') as mock_log:
            response = handler(event, context)
            
            assert response["statusCode"] == 200
            body = json.loads(response["body"])
            assert body["message"] == "Authentication event logged"
            assert body["user_id"] == "user-123"
            
            # Verify logging was called
            mock_log.assert_called_once()
            call_args = mock_log.call_args
            assert call_args[1]["user_id"] == "user-123"
            assert call_args[1]["email"] == "test@example.com"
            assert call_args[1]["success"] is True
    
    def test_authentication_event_failure(self):
        """Test logging failed authentication attempt with reason."""
        event = {
            "source": "aws.cognito",
            "detail": {
                "userId": "user-456",
                "email": "test@example.com",
                "success": False,
                "reason": "Invalid password"
            }
        }
        
        context = Mock()
        
        with patch('audit_logging.handler.log_authentication_attempt') as mock_log:
            response = handler(event, context)
            
            assert response["statusCode"] == 200
            
            # Verify failure reason was logged
            call_args = mock_log.call_args
            assert call_args[1]["success"] is False
            assert call_args[1]["reason"] == "Invalid password"
    
    def test_data_modification_event_create(self):
        """Test logging data creation operation."""
        event = {
            "source": "custom.datamodification",
            "detail": {
                "userId": "user-123",
                "tenantId": "tenant-456",
                "operationType": "CREATE",
                "entityType": "project",
                "entityId": "project-789",
                "changes": {
                    "name": "New Project",
                    "status": "active"
                }
            }
        }
        
        context = Mock()
        
        with patch('audit_logging.handler.log_data_modification') as mock_log:
            response = handler(event, context)
            
            assert response["statusCode"] == 200
            body = json.loads(response["body"])
            assert body["message"] == "Data modification event logged"
            assert body["entity_id"] == "project-789"
            
            # Verify all required fields were logged
            call_args = mock_log.call_args
            assert call_args[1]["user_id"] == "user-123"
            assert call_args[1]["tenant_id"] == "tenant-456"
            assert call_args[1]["operation_type"] == "CREATE"
            assert call_args[1]["entity_type"] == "project"
            assert call_args[1]["entity_id"] == "project-789"
            assert call_args[1]["changes"]["name"] == "New Project"
    
    def test_data_modification_event_update(self):
        """Test logging data update operation."""
        event = {
            "source": "custom.datamodification",
            "detail": {
                "userId": "user-123",
                "tenantId": "tenant-456",
                "operationType": "UPDATE",
                "entityType": "milestone",
                "entityId": "milestone-111",
                "changes": {
                    "status": "completed",
                    "completion_percentage": 100
                }
            }
        }
        
        context = Mock()
        
        with patch('audit_logging.handler.log_data_modification') as mock_log:
            response = handler(event, context)
            
            assert response["statusCode"] == 200
            
            call_args = mock_log.call_args
            assert call_args[1]["operation_type"] == "UPDATE"
            assert call_args[1]["changes"]["status"] == "completed"
    
    def test_data_modification_event_delete(self):
        """Test logging data deletion operation."""
        event = {
            "source": "custom.datamodification",
            "detail": {
                "userId": "user-123",
                "tenantId": "tenant-456",
                "operationType": "DELETE",
                "entityType": "risk",
                "entityId": "risk-222"
            }
        }
        
        context = Mock()
        
        with patch('audit_logging.handler.log_data_modification') as mock_log:
            response = handler(event, context)
            
            assert response["statusCode"] == 200
            
            call_args = mock_log.call_args
            assert call_args[1]["operation_type"] == "DELETE"
    
    def test_data_modification_missing_fields(self):
        """Test handling of incomplete data modification event."""
        event = {
            "source": "custom.datamodification",
            "detail": {
                "userId": "user-123",
                # Missing required fields
            }
        }
        
        context = Mock()
        
        response = handler(event, context)
        
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "Missing required fields" in body["error"]
    
    def test_admin_action_user_creation(self):
        """Test logging user creation administrative action."""
        event = {
            "source": "custom.adminaction",
            "detail": {
                "adminUserId": "admin-123",
                "actionType": "USER_CREATED",
                "affectedEntities": {
                    "user_id": "user-789",
                    "email": "newuser@example.com"
                },
                "details": {
                    "role": "PROGRAM_MANAGER",
                    "tenant_id": "tenant-456"
                }
            }
        }
        
        context = Mock()
        
        with patch('audit_logging.handler.log_administrative_action') as mock_log:
            response = handler(event, context)
            
            assert response["statusCode"] == 200
            body = json.loads(response["body"])
            assert body["message"] == "Administrative action logged"
            assert body["action_type"] == "USER_CREATED"
            
            # Verify all fields were logged
            call_args = mock_log.call_args
            assert call_args[1]["admin_user_id"] == "admin-123"
            assert call_args[1]["action_type"] == "USER_CREATED"
            assert call_args[1]["affected_entities"]["user_id"] == "user-789"
            assert call_args[1]["details"]["role"] == "PROGRAM_MANAGER"
    
    def test_admin_action_role_assignment(self):
        """Test logging role assignment administrative action."""
        event = {
            "source": "custom.adminaction",
            "detail": {
                "adminUserId": "admin-123",
                "actionType": "ROLE_ASSIGNED",
                "affectedEntities": {
                    "user_id": "user-456"
                },
                "details": {
                    "old_role": "TEAM_MEMBER",
                    "new_role": "PROGRAM_MANAGER"
                }
            }
        }
        
        context = Mock()
        
        with patch('audit_logging.handler.log_administrative_action') as mock_log:
            response = handler(event, context)
            
            assert response["statusCode"] == 200
            
            call_args = mock_log.call_args
            assert call_args[1]["action_type"] == "ROLE_ASSIGNED"
            assert call_args[1]["details"]["new_role"] == "PROGRAM_MANAGER"
    
    def test_admin_action_config_change(self):
        """Test logging configuration change administrative action."""
        event = {
            "source": "custom.adminaction",
            "detail": {
                "adminUserId": "admin-123",
                "actionType": "CONFIG_CHANGED",
                "affectedEntities": {
                    "config_key": "health_score_weights"
                },
                "details": {
                    "old_value": {"velocity": 0.30, "backlog": 0.25},
                    "new_value": {"velocity": 0.35, "backlog": 0.20}
                }
            }
        }
        
        context = Mock()
        
        with patch('audit_logging.handler.log_administrative_action') as mock_log:
            response = handler(event, context)
            
            assert response["statusCode"] == 200
            
            call_args = mock_log.call_args
            assert call_args[1]["action_type"] == "CONFIG_CHANGED"
    
    def test_admin_action_missing_fields(self):
        """Test handling of incomplete administrative action event."""
        event = {
            "source": "custom.adminaction",
            "detail": {
                "adminUserId": "admin-123"
                # Missing required fields
            }
        }
        
        context = Mock()
        
        response = handler(event, context)
        
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "Missing required fields" in body["error"]
    
    def test_eventbridge_event_routing(self):
        """Test routing of EventBridge events to correct handlers."""
        event = {
            "detail-type": "Authentication Attempt",
            "detail": {
                "userId": "user-123",
                "email": "test@example.com",
                "success": True
            }
        }
        
        context = Mock()
        
        with patch('audit_logging.handler.process_authentication_event') as mock_process:
            mock_process.return_value = {"statusCode": 200, "body": "{}"}
            handler(event, context)
            mock_process.assert_called_once()
    
    def test_direct_invocation_authentication(self):
        """Test direct invocation for authentication audit."""
        event = {
            "auditType": "authentication",
            "userId": "user-123",
            "email": "test@example.com",
            "success": True
        }
        
        context = Mock()
        
        with patch('audit_logging.handler.log_authentication_attempt') as mock_log:
            response = handler(event, context)
            assert response["statusCode"] == 200
            mock_log.assert_called_once()
    
    def test_direct_invocation_data_modification(self):
        """Test direct invocation for data modification audit."""
        event = {
            "auditType": "data_modification",
            "userId": "user-123",
            "tenantId": "tenant-456",
            "operationType": "UPDATE",
            "entityType": "project",
            "entityId": "project-789"
        }
        
        context = Mock()
        
        with patch('audit_logging.handler.log_data_modification') as mock_log:
            response = handler(event, context)
            assert response["statusCode"] == 200
            mock_log.assert_called_once()


class TestAuditPublisher:
    """Test suite for audit event publisher."""
    
    @patch('audit_logging.audit_publisher.get_eventbridge_client')
    def test_publish_authentication_event_success(self, mock_get_client):
        """Test publishing authentication event to EventBridge."""
        mock_eventbridge = Mock()
        mock_get_client.return_value = mock_eventbridge
        mock_eventbridge.put_events.return_value = {
            'FailedEntryCount': 0,
            'Entries': [{'EventId': 'event-123'}]
        }
        
        result = publish_authentication_event(
            user_id="user-123",
            email="test@example.com",
            success=True
        )
        
        assert result is True
        mock_eventbridge.put_events.assert_called_once()
        
        # Verify event structure
        call_args = mock_eventbridge.put_events.call_args
        entries = call_args[1]['Entries']
        assert len(entries) == 1
        assert entries[0]['Source'] == 'aws.cognito'
        assert entries[0]['DetailType'] == 'Authentication Attempt'
        
        detail = json.loads(entries[0]['Detail'])
        assert detail['userId'] == 'user-123'
        assert detail['email'] == 'test@example.com'
        assert detail['success'] is True
    
    @patch('audit_logging.audit_publisher.get_eventbridge_client')
    def test_publish_authentication_event_failure(self, mock_get_client):
        """Test handling of EventBridge publish failure."""
        mock_eventbridge = Mock()
        mock_get_client.return_value = mock_eventbridge
        mock_eventbridge.put_events.return_value = {
            'FailedEntryCount': 1,
            'Entries': [{'ErrorCode': 'InternalError'}]
        }
        
        result = publish_authentication_event(
            user_id="user-123",
            email="test@example.com",
            success=True
        )
        
        assert result is False
    
    @patch('audit_logging.audit_publisher.get_eventbridge_client')
    def test_publish_data_modification_event(self, mock_get_client):
        """Test publishing data modification event."""
        mock_eventbridge = Mock()
        mock_get_client.return_value = mock_eventbridge
        mock_eventbridge.put_events.return_value = {
            'FailedEntryCount': 0,
            'Entries': [{'EventId': 'event-456'}]
        }
        
        result = publish_data_modification_event(
            user_id="user-123",
            tenant_id="tenant-456",
            operation_type="CREATE",
            entity_type="project",
            entity_id="project-789",
            changes={"name": "New Project"}
        )
        
        assert result is True
        
        # Verify event structure
        call_args = mock_eventbridge.put_events.call_args
        entries = call_args[1]['Entries']
        assert entries[0]['Source'] == 'custom.datamodification'
        
        detail = json.loads(entries[0]['Detail'])
        assert detail['userId'] == 'user-123'
        assert detail['tenantId'] == 'tenant-456'
        assert detail['operationType'] == 'CREATE'
        assert detail['entityType'] == 'project'
        assert detail['entityId'] == 'project-789'
        assert detail['changes']['name'] == 'New Project'
    
    @patch('audit_logging.audit_publisher.get_eventbridge_client')
    def test_publish_admin_action_event(self, mock_get_client):
        """Test publishing administrative action event."""
        mock_eventbridge = Mock()
        mock_get_client.return_value = mock_eventbridge
        mock_eventbridge.put_events.return_value = {
            'FailedEntryCount': 0,
            'Entries': [{'EventId': 'event-789'}]
        }
        
        result = publish_admin_action_event(
            admin_user_id="admin-123",
            action_type="USER_CREATED",
            affected_entities={"user_id": "user-456"},
            details={"role": "PROGRAM_MANAGER"}
        )
        
        assert result is True
        
        # Verify event structure
        call_args = mock_eventbridge.put_events.call_args
        entries = call_args[1]['Entries']
        assert entries[0]['Source'] == 'custom.adminaction'
        
        detail = json.loads(entries[0]['Detail'])
        assert detail['adminUserId'] == 'admin-123'
        assert detail['actionType'] == 'USER_CREATED'
        assert detail['affectedEntities']['user_id'] == 'user-456'
        assert detail['details']['role'] == 'PROGRAM_MANAGER'


class TestLoggingRequirements:
    """Test suite for specific logging requirements."""
    
    def test_error_logging_completeness(self):
        """
        Test that error logging includes all required fields.
        Validates: Requirement 27.1
        """
        from shared.logger import log_error, get_logger
        
        logger = get_logger()
        error = ValueError("Test error")
        context = {"function": "test_function", "request_id": "req-123"}
        
        with patch.object(logger, 'error') as mock_error:
            log_error(logger, error, context=context, severity="ERROR")
            
            # Verify error log includes all required fields
            call_args = mock_error.call_args
            extra = call_args[1]['extra']
            
            assert 'severity' in extra
            assert 'timestamp' in extra
            assert 'error_type' in extra
            assert 'error_message' in extra
            assert 'stack_trace' in extra
            assert 'context' in extra
            
            assert extra['severity'] == 'ERROR'
            assert extra['error_type'] == 'ValueError'
            assert extra['error_message'] == 'Test error'
            assert extra['context'] == context
    
    def test_api_request_logging_completeness(self):
        """
        Test that API request logging includes all required fields.
        Validates: Requirement 27.2
        """
        from shared.logger import log_api_request, get_logger
        
        logger = get_logger()
        
        with patch.object(logger, 'info') as mock_info:
            log_api_request(
                logger,
                request_id="req-123",
                user_id="user-456",
                tenant_id="tenant-789",
                endpoint="/api/projects",
                method="GET",
                response_time_ms=150.5,
                status_code=200
            )
            
            # Verify API request log includes all required fields
            call_args = mock_info.call_args
            extra = call_args[1]['extra']
            
            assert 'request_id' in extra
            assert 'user_id' in extra
            assert 'tenant_id' in extra
            assert 'endpoint' in extra
            assert 'method' in extra
            assert 'response_time_ms' in extra
            assert 'status_code' in extra
            assert 'timestamp' in extra
            
            assert extra['request_id'] == 'req-123'
            assert extra['user_id'] == 'user-456'
            assert extra['tenant_id'] == 'tenant-789'
            assert extra['response_time_ms'] == 150.5


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
