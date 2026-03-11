"""Tests for risk alert storage and retrieval."""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from decimal import Decimal

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from risk_detection.risk_storage import (
    convert_floats_to_decimals,
    convert_decimals_to_floats,
    store_risk_alert,
    list_risks,
    dismiss_risk,
    publish_risk_event
)


class TestConversionFunctions:
    """Tests for Decimal/float conversion functions."""
    
    def test_convert_floats_to_decimals(self):
        """Test converting floats to Decimals."""
        obj = {
            'value': 123.45,
            'nested': {
                'value': 67.89
            },
            'list': [1.1, 2.2, 3.3]
        }
        
        result = convert_floats_to_decimals(obj)
        
        assert isinstance(result['value'], Decimal)
        assert isinstance(result['nested']['value'], Decimal)
        assert all(isinstance(v, Decimal) for v in result['list'])
    
    def test_convert_decimals_to_floats(self):
        """Test converting Decimals to floats."""
        obj = {
            'value': Decimal('123.45'),
            'nested': {
                'value': Decimal('67.89')
            },
            'list': [Decimal('1.1'), Decimal('2.2'), Decimal('3.3')]
        }
        
        result = convert_decimals_to_floats(obj)
        
        assert isinstance(result['value'], float)
        assert isinstance(result['nested']['value'], float)
        assert all(isinstance(v, float) for v in result['list'])


class TestStoreRiskAlert:
    """Tests for store_risk_alert function."""
    
    @patch('risk_detection.risk_storage.get_dynamodb_resource')
    def test_store_risk_alert_success(self, mock_dynamodb):
        """Test successful risk alert storage."""
        # Mock DynamoDB table
        mock_table = MagicMock()
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_dynamodb.return_value = mock_resource
        
        risk = {
            'tenant_id': 'tenant-123',
            'project_id': 'project-456',
            'type': 'VELOCITY_DECLINE',
            'severity': 'HIGH',
            'title': 'Velocity Decline Detected',
            'description': 'Velocity has declined by 25%',
            'metrics': {
                'current_velocity': 25.0,
                'decline_percentage': 25.0
            },
            'recommendations': ['Review team capacity'],
            'detected_at': '2024-01-15T10:00:00Z'
        }
        
        risk_id = store_risk_alert(risk)
        
        assert risk_id is not None
        assert isinstance(risk_id, str)
        mock_table.put_item.assert_called_once()
    
    @patch('risk_detection.risk_storage.get_dynamodb_resource')
    def test_store_risk_alert_with_milestone(self, mock_dynamodb):
        """Test storing milestone-related risk."""
        mock_table = MagicMock()
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_dynamodb.return_value = mock_resource
        
        risk = {
            'tenant_id': 'tenant-123',
            'project_id': 'project-456',
            'type': 'MILESTONE_SLIPPAGE',
            'severity': 'CRITICAL',
            'title': 'Milestone at Risk',
            'description': 'Milestone is behind schedule',
            'milestone_id': 'milestone-789',
            'milestone_name': 'Phase 1 Complete',
            'metrics': {},
            'recommendations': []
        }
        
        risk_id = store_risk_alert(risk)
        
        assert risk_id is not None
        mock_table.put_item.assert_called_once()


class TestListRisks:
    """Tests for list_risks function."""
    
    @patch('risk_detection.risk_storage.get_dynamodb_resource')
    def test_list_risks_by_tenant(self, mock_dynamodb):
        """Test listing risks by tenant."""
        mock_table = MagicMock()
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_dynamodb.return_value = mock_resource
        
        mock_table.query.return_value = {
            'Items': [
                {
                    'risk_id': 'risk-1',
                    'type': 'VELOCITY_DECLINE',
                    'severity': 'HIGH',
                    'status': 'ACTIVE'
                },
                {
                    'risk_id': 'risk-2',
                    'type': 'BACKLOG_GROWTH',
                    'severity': 'MEDIUM',
                    'status': 'ACTIVE'
                }
            ]
        }
        
        result = list_risks('tenant-123')
        
        assert len(result) == 2
        assert result[0]['risk_id'] == 'risk-1'
        mock_table.query.assert_called_once()
    
    @patch('risk_detection.risk_storage.get_dynamodb_resource')
    def test_list_risks_by_project(self, mock_dynamodb):
        """Test listing risks by project."""
        mock_table = MagicMock()
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_dynamodb.return_value = mock_resource
        
        mock_table.query.return_value = {
            'Items': [
                {
                    'risk_id': 'risk-1',
                    'project_id': 'project-456',
                    'type': 'VELOCITY_DECLINE'
                }
            ]
        }
        
        result = list_risks('tenant-123', project_id='project-456')
        
        assert len(result) == 1
        assert result[0]['project_id'] == 'project-456'
    
    @patch('risk_detection.risk_storage.get_dynamodb_resource')
    def test_list_risks_by_severity(self, mock_dynamodb):
        """Test listing risks by severity."""
        mock_table = MagicMock()
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_dynamodb.return_value = mock_resource
        
        mock_table.query.return_value = {
            'Items': [
                {
                    'risk_id': 'risk-1',
                    'severity': 'CRITICAL'
                }
            ]
        }
        
        result = list_risks('tenant-123', severity='CRITICAL')
        
        assert len(result) == 1
        assert result[0]['severity'] == 'CRITICAL'
    
    @patch('risk_detection.risk_storage.get_dynamodb_resource')
    def test_list_risks_with_status_filter(self, mock_dynamodb):
        """Test listing risks with status filter."""
        mock_table = MagicMock()
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_dynamodb.return_value = mock_resource
        
        mock_table.query.return_value = {
            'Items': [
                {'risk_id': 'risk-1', 'status': 'ACTIVE'},
                {'risk_id': 'risk-2', 'status': 'DISMISSED'},
                {'risk_id': 'risk-3', 'status': 'ACTIVE'}
            ]
        }
        
        result = list_risks('tenant-123', status='ACTIVE')
        
        assert len(result) == 2
        assert all(r['status'] == 'ACTIVE' for r in result)


class TestDismissRisk:
    """Tests for dismiss_risk function."""
    
    @patch('risk_detection.risk_storage.get_dynamodb_resource')
    def test_dismiss_risk_success(self, mock_dynamodb):
        """Test successful risk dismissal."""
        mock_table = MagicMock()
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_dynamodb.return_value = mock_resource
        
        mock_table.update_item.return_value = {
            'Attributes': {
                'risk_id': 'risk-1',
                'status': 'DISMISSED',
                'dismissed_by': 'user-123',
                'dismissal_reason': 'False positive'
            }
        }
        
        result = dismiss_risk(
            risk_id='risk-1',
            tenant_id='tenant-123',
            dismissed_by='user-123',
            reason='False positive'
        )
        
        assert result['status'] == 'DISMISSED'
        assert result['dismissed_by'] == 'user-123'
        mock_table.update_item.assert_called_once()


class TestPublishRiskEvent:
    """Tests for publish_risk_event function."""
    
    @patch('risk_detection.risk_storage.get_eventbridge_client')
    def test_publish_risk_event_success(self, mock_eventbridge):
        """Test successful event publishing."""
        mock_client = MagicMock()
        mock_eventbridge.return_value = mock_client
        
        mock_client.put_events.return_value = {
            'FailedEntryCount': 0,
            'Entries': [{'EventId': 'event-123'}]
        }
        
        risk = {
            'risk_id': 'risk-1',
            'project_id': 'project-456',
            'type': 'VELOCITY_DECLINE'
        }
        
        # Should not raise exception
        publish_risk_event(risk, 'RiskDetected')
        
        mock_client.put_events.assert_called_once()
    
    @patch('risk_detection.risk_storage.get_eventbridge_client')
    def test_publish_risk_event_failure_logged(self, mock_eventbridge):
        """Test event publishing failure raises DataError."""
        mock_client = MagicMock()
        mock_eventbridge.return_value = mock_client
        
        mock_client.put_events.return_value = {
            'FailedEntryCount': 1,
            'Entries': [{'ErrorCode': 'InternalError'}]
        }
        
        risk = {
            'risk_id': 'risk-1',
            'project_id': 'project-456'
        }
        
        # Event publishing failures raise DataError
        from shared.errors import DataError
        with pytest.raises(DataError):
            publish_risk_event(risk, 'RiskDetected')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
