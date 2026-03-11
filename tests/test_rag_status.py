"""Tests for RAG status determination service."""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import json

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from rag_status.rag_calculator import (
    get_tenant_thresholds,
    determine_rag_status,
    calculate_rag_status,
    DEFAULT_THRESHOLDS
)
from rag_status.rag_storage import (
    store_rag_status,
    get_rag_status_history,
    get_latest_rag_status,
    get_previous_rag_status,
    detect_status_degradation,
    publish_rag_status_event,
    publish_degradation_notification
)
from rag_status.handler import (
    calculate_rag_status_handler,
    get_rag_status_handler,
    get_rag_status_history_handler
)


# ============================================================================
# RAG Calculator Tests
# ============================================================================

class TestRagCalculator:
    """Tests for RAG status calculation logic."""
    
    def test_get_tenant_thresholds_returns_defaults(self):
        """Test that default thresholds are returned when no custom config exists."""
        thresholds = get_tenant_thresholds('tenant-123')
        
        assert thresholds == DEFAULT_THRESHOLDS
        assert thresholds['green'] == 80
        assert thresholds['amber'] == 60
    
    def test_determine_rag_status_green(self):
        """
        Test RAG status determination for Green status.
        
        **Validates: Property 60 - RAG Status Determination**
        """
        # Test at green threshold
        assert determine_rag_status(80) == 'GREEN'
        
        # Test above green threshold
        assert determine_rag_status(90) == 'GREEN'
        assert determine_rag_status(100) == 'GREEN'
    
    def test_determine_rag_status_amber(self):
        """
        Test RAG status determination for Amber status.
        
        **Validates: Property 60 - RAG Status Determination**
        """
        # Test at amber threshold
        assert determine_rag_status(60) == 'AMBER'
        
        # Test in amber range
        assert determine_rag_status(70) == 'AMBER'
        assert determine_rag_status(79) == 'AMBER'
    
    def test_determine_rag_status_red(self):
        """
        Test RAG status determination for Red status.
        
        **Validates: Property 60 - RAG Status Determination**
        """
        # Test below amber threshold
        assert determine_rag_status(59) == 'RED'
        assert determine_rag_status(30) == 'RED'
        assert determine_rag_status(0) == 'RED'
    
    def test_determine_rag_status_with_custom_thresholds(self):
        """
        Test RAG status determination with custom thresholds.
        
        **Validates: Property 61 - Custom Threshold Application**
        """
        custom_thresholds = {'green': 85, 'amber': 65}
        
        # Test green with custom thresholds
        assert determine_rag_status(85, custom_thresholds) == 'GREEN'
        assert determine_rag_status(90, custom_thresholds) == 'GREEN'
        
        # Test amber with custom thresholds
        assert determine_rag_status(65, custom_thresholds) == 'AMBER'
        assert determine_rag_status(75, custom_thresholds) == 'AMBER'
        
        # Test red with custom thresholds
        assert determine_rag_status(64, custom_thresholds) == 'RED'
        assert determine_rag_status(50, custom_thresholds) == 'RED'
    
    def test_calculate_rag_status_returns_complete_data(self):
        """
        Test that calculate_rag_status returns all required fields.
        
        **Validates: Property 60 - RAG Status Determination**
        """
        result = calculate_rag_status(
            project_id='proj-123',
            tenant_id='tenant-123',
            health_score=75
        )
        
        assert 'rag_status' in result
        assert 'health_score' in result
        assert 'thresholds' in result
        assert 'calculated_at' in result
        
        assert result['rag_status'] == 'AMBER'
        assert result['health_score'] == 75
        assert result['thresholds'] == DEFAULT_THRESHOLDS
    
    def test_calculate_rag_status_with_custom_thresholds(self):
        """
        Test calculate_rag_status with custom thresholds.
        
        **Validates: Property 61 - Custom Threshold Application**
        """
        custom_thresholds = {'green': 90, 'amber': 70}
        
        result = calculate_rag_status(
            project_id='proj-123',
            tenant_id='tenant-123',
            health_score=75,
            custom_thresholds=custom_thresholds
        )
        
        assert result['rag_status'] == 'AMBER'
        assert result['thresholds'] == custom_thresholds


# ============================================================================
# RAG Storage Tests
# ============================================================================

class TestRagStorage:
    """Tests for RAG status storage and history management."""
    
    @patch('rag_status.rag_storage.execute_query')
    def test_store_rag_status(self, mock_execute):
        """
        Test storing RAG status in database.
        
        **Validates: Property 62 - RAG Status Update Triggering**
        """
        # Mock database response
        mock_execute.return_value = [{'id': 'status-123'}]
        
        rag_status_data = {
            'rag_status': 'AMBER',
            'health_score': 75,
            'thresholds': {'green': 80, 'amber': 60},
            'calculated_at': '2024-01-01T00:00:00Z'
        }
        
        status_id = store_rag_status(
            project_id='proj-123',
            tenant_id='tenant-123',
            rag_status_data=rag_status_data
        )
        
        assert status_id == 'status-123'
        assert mock_execute.call_count >= 1
    
    @patch('rag_status.rag_storage.execute_query')
    def test_get_rag_status_history(self, mock_execute):
        """Test retrieving RAG status history."""
        # Mock database response
        mock_execute.return_value = [
            {
                'id': 'status-1',
                'rag_status': 'GREEN',
                'health_score': 85,
                'thresholds': json.dumps({'green': 80, 'amber': 60}),
                'calculated_at': '2024-01-02T00:00:00Z',
                'created_at': '2024-01-02T00:00:00Z'
            },
            {
                'id': 'status-2',
                'rag_status': 'AMBER',
                'health_score': 75,
                'thresholds': json.dumps({'green': 80, 'amber': 60}),
                'calculated_at': '2024-01-01T00:00:00Z',
                'created_at': '2024-01-01T00:00:00Z'
            }
        ]
        
        history = get_rag_status_history(
            project_id='proj-123',
            tenant_id='tenant-123',
            limit=10
        )
        
        assert len(history) == 2
        assert history[0]['rag_status'] == 'GREEN'
        assert history[1]['rag_status'] == 'AMBER'
        assert isinstance(history[0]['thresholds'], dict)
    
    @patch('rag_status.rag_storage.get_rag_status_history')
    def test_get_latest_rag_status(self, mock_get_history):
        """Test retrieving latest RAG status."""
        mock_get_history.return_value = [
            {
                'id': 'status-1',
                'rag_status': 'GREEN',
                'health_score': 85
            }
        ]
        
        latest = get_latest_rag_status('proj-123', 'tenant-123')
        
        assert latest is not None
        assert latest['rag_status'] == 'GREEN'
        mock_get_history.assert_called_once_with('proj-123', 'tenant-123', limit=1)
    
    @patch('rag_status.rag_storage.get_rag_status_history')
    def test_get_previous_rag_status(self, mock_get_history):
        """Test retrieving previous RAG status."""
        mock_get_history.return_value = [
            {'rag_status': 'AMBER'},
            {'rag_status': 'GREEN'}
        ]
        
        previous = get_previous_rag_status('proj-123', 'tenant-123')
        
        assert previous == 'GREEN'
        mock_get_history.assert_called_once_with('proj-123', 'tenant-123', limit=2)
    
    def test_detect_status_degradation_green_to_amber(self):
        """
        Test detection of Green to Amber degradation.
        
        **Validates: Property 63 - RAG Degradation Notification**
        """
        assert detect_status_degradation('AMBER', 'GREEN') is True
    
    def test_detect_status_degradation_green_to_red(self):
        """
        Test detection of Green to Red degradation.
        
        **Validates: Property 63 - RAG Degradation Notification**
        """
        assert detect_status_degradation('RED', 'GREEN') is True
    
    def test_detect_status_degradation_no_degradation(self):
        """Test that non-degradation transitions are not detected."""
        # Amber to Red is not considered degradation (already not green)
        assert detect_status_degradation('RED', 'AMBER') is False
        
        # Improvements are not degradation
        assert detect_status_degradation('GREEN', 'AMBER') is False
        assert detect_status_degradation('AMBER', 'RED') is False
        
        # Same status is not degradation
        assert detect_status_degradation('GREEN', 'GREEN') is False
        assert detect_status_degradation('AMBER', 'AMBER') is False
    
    def test_detect_status_degradation_no_previous(self):
        """Test degradation detection with no previous status."""
        assert detect_status_degradation('RED', None) is False
        assert detect_status_degradation('AMBER', None) is False
    
    @patch('rag_status.rag_storage.boto3.client')
    def test_publish_rag_status_event(self, mock_boto_client):
        """Test publishing RAG status event to EventBridge."""
        mock_eventbridge = Mock()
        mock_eventbridge.put_events.return_value = {'FailedEntryCount': 0}
        mock_boto_client.return_value = mock_eventbridge
        
        rag_status_data = {
            'rag_status': 'AMBER',
            'health_score': 75,
            'calculated_at': '2024-01-01T00:00:00Z'
        }
        
        publish_rag_status_event(
            project_id='proj-123',
            tenant_id='tenant-123',
            rag_status_data=rag_status_data
        )
        
        mock_eventbridge.put_events.assert_called_once()
        call_args = mock_eventbridge.put_events.call_args[1]
        entries = call_args['Entries']
        
        assert len(entries) == 1
        assert entries[0]['Source'] == 'ai-sw-pm.rag-status'
        assert entries[0]['DetailType'] == 'RagStatusCalculated'
    
    @patch('rag_status.rag_storage.boto3.client')
    def test_publish_degradation_notification(self, mock_boto_client):
        """
        Test publishing degradation notification.
        
        **Validates: Property 63 - RAG Degradation Notification**
        """
        mock_eventbridge = Mock()
        mock_eventbridge.put_events.return_value = {'FailedEntryCount': 0}
        mock_boto_client.return_value = mock_eventbridge
        
        publish_degradation_notification(
            project_id='proj-123',
            tenant_id='tenant-123',
            current_status='AMBER',
            previous_status='GREEN',
            health_score=75
        )
        
        mock_eventbridge.put_events.assert_called_once()
        call_args = mock_eventbridge.put_events.call_args[1]
        entries = call_args['Entries']
        
        assert len(entries) == 1
        assert entries[0]['Source'] == 'ai-sw-pm.rag-status'
        assert entries[0]['DetailType'] == 'RagStatusDegradation'
        
        detail = json.loads(entries[0]['Detail'])
        assert detail['current_status'] == 'AMBER'
        assert detail['previous_status'] == 'GREEN'
        assert detail['notification_type'] == 'RAG_DEGRADATION'


# ============================================================================
# Handler Tests
# ============================================================================

class TestHandlers:
    """Tests for Lambda handlers."""
    
    @patch('rag_status.handler.publish_degradation_notification')
    @patch('rag_status.handler.publish_rag_status_event')
    @patch('rag_status.handler.store_rag_status')
    @patch('rag_status.handler.get_previous_rag_status')
    @patch('rag_status.handler.calculate_rag_status')
    def test_calculate_rag_status_handler_eventbridge_format(
        self,
        mock_calculate,
        mock_get_previous,
        mock_store,
        mock_publish_event,
        mock_publish_notification
    ):
        """
        Test handler with EventBridge event format.
        
        **Validates: Property 62 - RAG Status Update Triggering**
        """
        mock_calculate.return_value = {
            'rag_status': 'AMBER',
            'health_score': 75,
            'thresholds': {'green': 80, 'amber': 60},
            'calculated_at': '2024-01-01T00:00:00Z'
        }
        mock_get_previous.return_value = 'GREEN'
        mock_store.return_value = 'status-123'
        
        event = {
            'detail': {
                'project_id': 'proj-123',
                'tenant_id': 'tenant-123',
                'health_score': 75
            }
        }
        
        response = calculate_rag_status_handler(event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['rag_status'] == 'AMBER'
        assert body['status_id'] == 'status-123'
        
        mock_calculate.assert_called_once()
        mock_store.assert_called_once()
        mock_publish_event.assert_called_once()
    
    @patch('rag_status.handler.publish_degradation_notification')
    @patch('rag_status.handler.publish_rag_status_event')
    @patch('rag_status.handler.store_rag_status')
    @patch('rag_status.handler.get_previous_rag_status')
    @patch('rag_status.handler.calculate_rag_status')
    def test_calculate_rag_status_handler_with_degradation(
        self,
        mock_calculate,
        mock_get_previous,
        mock_store,
        mock_publish_event,
        mock_publish_notification
    ):
        """
        Test handler publishes notification on degradation.
        
        **Validates: Property 63 - RAG Degradation Notification**
        """
        mock_calculate.return_value = {
            'rag_status': 'RED',
            'health_score': 50,
            'thresholds': {'green': 80, 'amber': 60},
            'calculated_at': '2024-01-01T00:00:00Z'
        }
        mock_get_previous.return_value = 'GREEN'
        mock_store.return_value = 'status-123'
        
        event = {
            'project_id': 'proj-123',
            'tenant_id': 'tenant-123',
            'health_score': 50
        }
        
        response = calculate_rag_status_handler(event, None)
        
        assert response['statusCode'] == 200
        
        # Verify degradation notification was published
        mock_publish_notifi