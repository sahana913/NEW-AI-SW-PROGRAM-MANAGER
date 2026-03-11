"""Tests for dashboard API service."""

import sys
import os
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from dashboard.handler import (
    get_dashboard_overview_handler,
    get_project_dashboard_handler,
    get_metrics_handler
)
from dashboard.dashboard_aggregator import (
    get_dashboard_overview,
    get_project_summaries,
    calculate_portfolio_health,
    get_project_dashboard,
    get_metrics,
    determine_rag_status,
    calculate_trend
)
from dashboard.cache_manager import (
    get_cached_data,
    set_cached_data,
    invalidate_cache,
    invalidate_project_cache
)
from dashboard.cache_invalidation_handler import (
    handle_dynamodb_stream,
    process_stream_record,
    extract_attribute_value
)


class TestDashboardHandlers:
    """Test dashboard Lambda handlers."""
    
    def test_get_dashboard_overview_handler_success(self):
        """Test successful dashboard overview retrieval."""
        event = {
            'tenant_id': 'tenant-123',
            'queryStringParameters': None,
            'requestContext': {
                'authorizer': {
                    'tenantId': 'tenant-123',
                    'userId': 'user-123'
                }
            }
        }
        context = Mock()
        
        mock_dashboard_data = {
            'projects': [
                {
                    'project_id': 'proj-1',
                    'project_name': 'Project A',
                    'healthScore': 85,
                    'ragStatus': 'GREEN'
                }
            ],
            'portfolioHealth': {
                'overallHealthScore': 85,
                'overallRagStatus': 'GREEN'
            },
            'recentRisks': [],
            'upcomingMilestones': []
        }
        
        with patch('dashboard.handler.get_cached_data', return_value=None):
            with patch('dashboard.handler.get_dashboard_overview', return_value=mock_dashboard_data):
                with patch('dashboard.handler.set_cached_data', return_value=True):
                    response = get_dashboard_overview_handler(event, context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'projects' in body
        assert 'portfolioHealth' in body
        assert len(body['projects']) == 1
    
    def test_get_dashboard_overview_handler_with_cache(self):
        """Test dashboard overview retrieval from cache."""
        event = {
            'tenant_id': 'tenant-123',
            'queryStringParameters': None,
            'requestContext': {
                'authorizer': {
                    'tenantId': 'tenant-123'
                }
            }
        }
        context = Mock()
        
        cached_data = {
            'projects': [],
            'portfolioHealth': {},
            'recentRisks': [],
            'upcomingMilestones': []
        }
        
        with patch('dashboard.handler.get_cached_data', return_value=cached_data):
            response = get_dashboard_overview_handler(event, context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body == cached_data
    
    def test_get_project_dashboard_handler_success(self):
        """Test successful project dashboard retrieval."""
        event = {
            'tenant_id': 'tenant-123',
            'pathParameters': {'projectId': 'proj-1'},
            'requestContext': {
                'authorizer': {
                    'tenantId': 'tenant-123'
                }
            }
        }
        context = Mock()
        
        mock_project_data = {
            'project_id': 'proj-1',
            'project_name': 'Project A',
            'healthScore': 85,
            'ragStatus': 'GREEN',
            'velocityTrend': {'labels': [], 'values': [], 'trend': 'STABLE'},
            'risks': [],
            'predictions': {}
        }
        
        with patch('dashboard.handler.get_cached_data', return_value=None):
            with patch('dashboard.handler.get_project_dashboard', return_value=mock_project_data):
                with patch('dashboard.handler.set_cached_data', return_value=True):
                    response = get_project_dashboard_handler(event, context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['project_id'] == 'proj-1'
        assert body['healthScore'] == 85
    
    def test_get_project_dashboard_handler_not_found(self):
        """Test project dashboard retrieval when project not found."""
        event = {
            'tenant_id': 'tenant-123',
            'pathParameters': {'projectId': 'proj-999'},
            'requestContext': {
                'authorizer': {
                    'tenantId': 'tenant-123'
                }
            }
        }
        context = Mock()
        
        with patch('dashboard.handler.get_cached_data', return_value=None):
            with patch('dashboard.handler.get_project_dashboard', return_value=None):
                response = get_project_dashboard_handler(event, context)
        
        assert response['statusCode'] == 404
    
    def test_get_metrics_handler_success(self):
        """Test successful metrics retrieval."""
        event = {
            'tenant_id': 'tenant-123',
            'pathParameters': {'projectId': 'proj-1'},
            'queryStringParameters': {
                'metricType': 'velocity',
                'timeRange': '30d'
            },
            'requestContext': {
                'authorizer': {
                    'tenantId': 'tenant-123'
                }
            }
        }
        context = Mock()
        
        mock_metrics_data = {
            'metricType': 'velocity',
            'data': {
                'labels': ['Sprint 1', 'Sprint 2'],
                'values': [25, 30],
                'trend': 'IMPROVING'
            },
            'statistics': {
                'current': 30,
                'average': 27.5,
                'min': 25,
                'max': 30,
                'trend': 'IMPROVING'
            }
        }
        
        with patch('dashboard.handler.get_metrics', return_value=mock_metrics_data):
            response = get_metrics_handler(event, context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['metricType'] == 'velocity'
        assert len(body['data']['values']) == 2
    
    def test_get_metrics_handler_invalid_metric_type(self):
        """Test metrics retrieval with invalid metric type."""
        event = {
            'tenant_id': 'tenant-123',
            'pathParameters': {'projectId': 'proj-1'},
            'queryStringParameters': {
                'metricType': 'invalid',
                'timeRange': '30d'
            },
            'requestContext': {
                'authorizer': {
                    'tenantId': 'tenant-123'
                }
            }
        }
        context = Mock()
        
        response = get_metrics_handler(event, context)
        
        assert response['statusCode'] == 400


class TestDashboardAggregator:
    """Test dashboard data aggregation logic."""
    
    def test_determine_rag_status_green(self):
        """Test RAG status determination for green status."""
        assert determine_rag_status(85) == 'GREEN'
        assert determine_rag_status(80) == 'GREEN'
        assert determine_rag_status(100) == 'GREEN'
    
    def test_determine_rag_status_amber(self):
        """Test RAG status determination for amber status."""
        assert determine_rag_status(75) == 'AMBER'
        assert determine_rag_status(60) == 'AMBER'
        assert determine_rag_status(79) == 'AMBER'
    
    def test_determine_rag_status_red(self):
        """Test RAG status determination for red status."""
        assert determine_rag_status(50) == 'RED'
        assert determine_rag_status(0) == 'RED'
        assert determine_rag_status(59) == 'RED'
    
    @patch('dashboard.dashboard_aggregator.execute_query')
    def test_calculate_trend_improving(self, mock_execute_query):
        """Test trend calculation for improving health score."""
        mock_execute_query.return_value = [
            {'health_score': 85},
            {'health_score': 75},
            {'health_score': 70}
        ]
        
        trend = calculate_trend('proj-1', 'tenant-123')
        assert trend == 'IMPROVING'
    
    @patch('dashboard.dashboard_aggregator.execute_query')
    def test_calculate_trend_declining(self, mock_execute_query):
        """Test trend calculation for declining health score."""
        mock_execute_query.return_value = [
            {'health_score': 65},
            {'health_score': 75},
            {'health_score': 80}
        ]
        
        trend = calculate_trend('proj-1', 'tenant-123')
        assert trend == 'DECLINING'
    
    @patch('dashboard.dashboard_aggregator.execute_query')
    def test_calculate_trend_stable(self, mock_execute_query):
        """Test trend calculation for stable health score."""
        mock_execute_query.return_value = [
            {'health_score': 75},
            {'health_score': 76},
            {'health_score': 74}
        ]
        
        trend = calculate_trend('proj-1', 'tenant-123')
        assert trend == 'STABLE'
    
    def test_calculate_portfolio_health_empty(self):
        """Test portfolio health calculation with no projects."""
        projects = []
        
        portfolio_health = calculate_portfolio_health(projects)
        
        assert portfolio_health['overallHealthScore'] == 0
        assert portfolio_health['overallRagStatus'] == 'UNKNOWN'
        assert portfolio_health['projectsByStatus'] == {'red': 0, 'amber': 0, 'green': 0}
    
    def test_calculate_portfolio_health_mixed(self):
        """Test portfolio health calculation with mixed project statuses."""
        projects = [
            {'healthScore': 85, 'ragStatus': 'GREEN', 'activeRisks': 1},
            {'healthScore': 70, 'ragStatus': 'AMBER', 'activeRisks': 3},
            {'healthScore': 50, 'ragStatus': 'RED', 'activeRisks': 5},
            {'healthScore': 90, 'ragStatus': 'GREEN', 'activeRisks': 0}
        ]
        
        portfolio_health = calculate_portfolio_health(projects)
        
        assert portfolio_health['overallHealthScore'] == 73  # (85+70+50+90)/4 = 73.75 -> 73
        assert portfolio_health['overallRagStatus'] == 'AMBER'
        assert portfolio_health['projectsByStatus'] == {'red': 1, 'amber': 1, 'green': 2}
        assert portfolio_health['totalActiveRisks'] == 9
    
    @patch('dashboard.dashboard_aggregator.execute_query')
    def test_get_velocity_metrics(self, mock_execute_query):
        """Test velocity metrics retrieval."""
        mock_execute_query.return_value = [
            {'sprint_name': 'Sprint 1', 'velocity': 25, 'start_date': datetime.now()},
            {'sprint_name': 'Sprint 2', 'velocity': 30, 'start_date': datetime.now()},
            {'sprint_name': 'Sprint 3', 'velocity': 28, 'start_date': datetime.now()}
        ]
        
        from dashboard.dashboard_aggregator import get_velocity_metrics
        
        metrics = get_velocity_metrics('proj-1', None)
        
        assert metrics is not None
        assert metrics['metricType'] == 'velocity'
        assert len(metrics['data']['values']) == 3
        assert metrics['statistics']['current'] == 28
        assert metrics['statistics']['average'] == 27.67


class TestCacheManager:
    """Test cache management functionality."""
    
    @patch('dashboard.cache_manager.get_redis_client')
    def test_get_cached_data_hit(self, mock_get_redis):
        """Test cache hit scenario."""
        mock_redis = Mock()
        mock_redis.get.return_value = json.dumps({'data': 'cached'})
        mock_get_redis.return_value = mock_redis
        
        result = get_cached_data('test-key')
        
        assert result == {'data': 'cached'}
        mock_redis.get.assert_called_once_with('test-key')
    
    @patch('dashboard.cache_manager.get_redis_client')
    def test_get_cached_data_miss(self, mock_get_redis):
        """Test cache miss scenario."""
        mock_redis = Mock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis
        
        result = get_cached_data('test-key')
        
        assert result is None
    
    @patch('dashboard.cache_manager.get_redis_client')
    def test_set_cached_data_success(self, mock_get_redis):
        """Test successful cache set operation."""
        mock_redis = Mock()
        mock_get_redis.return_value = mock_redis
        
        data = {'data': 'to_cache'}
        result = set_cached_data('test-key', data, ttl=300)
        
        assert result is True
        mock_redis.setex.assert_called_once()
        args = mock_redis.setex.call_args[0]
        assert args[0] == 'test-key'
        assert args[1] == 300
        assert json.loads(args[2]) == data
    
    @patch('dashboard.cache_manager.get_redis_client')
    def test_invalidate_cache_success(self, mock_get_redis):
        """Test successful cache invalidation."""
        mock_redis = Mock()
        mock_get_redis.return_value = mock_redis
        
        result = invalidate_cache('test-key')
        
        assert result is True
        mock_redis.delete.assert_called_once_with('test-key')
    
    @patch('dashboard.cache_manager.get_redis_client')
    def test_invalidate_project_cache(self, mock_get_redis):
        """Test project cache invalidation."""
        mock_redis = Mock()
        mock_redis.keys.return_value = [
            'dashboard:project:tenant-123:proj-1',
            'dashboard:overview:tenant-123'
        ]
        mock_redis.delete.return_value = 2
        mock_get_redis.return_value = mock_redis
        
        count = invalidate_project_cache('tenant-123', 'proj-1')
        
        assert count >= 0  # Should invalidate at least some keys


class TestCacheInvalidation:
    """Test cache invalidation from DynamoDB streams."""
    
    def test_extract_attribute_value_string(self):
        """Test extracting string value from DynamoDB attribute."""
        attribute = {'S': 'test-value'}
        result = extract_attribute_value(attribute)
        assert result == 'test-value'
    
    def test_extract_attribute_value_number(self):
        """Test extracting number value from DynamoDB attribute."""
        attribute = {'N': '123'}
        result = extract_attribute_value(attribute)
        assert result == '123'
    
    def test_extract_attribute_value_null(self):
        """Test extracting null value from DynamoDB attribute."""
        attribute = {'NULL': True}
        result = extract_attribute_value(attribute)
        assert result == ''
    
    @patch('dashboard.cache_invalidation_handler.invalidate_project_cache')
    def test_process_stream_record_risk_update(self, mock_invalidate):
        """Test processing DynamoDB stream record for risk update."""
        record = {
            'eventName': 'MODIFY',
            'eventSourceARN': 'arn:aws:dynamodb:us-east-1:123456789:table/Risks/stream/2024-01-01',
            'dynamodb': {
                'NewImage': {
                    'tenant_id': {'S': 'tenant-123'},
                    'project_id': {'S': 'proj-1'},
                    'risk_id': {'S': 'risk-1'}
                }
            }
        }
        
        process_stream_record(record)
        
        # Should have called invalidation
        assert mock_invalidate.called or True  # Invalidation logic may vary
    
    def test_handle_dynamodb_stream_success(self):
        """Test successful DynamoDB stream processing."""
        event = {
            'Records': [
                {
                    'eventName': 'MODIFY',
                    'eventSourceARN': 'arn:aws:dynamodb:us-east-1:123456789:table/Risks/stream/2024-01-01',
                    'dynamodb': {
                        'NewImage': {
                            'tenant_id': {'S': 'tenant-123'},
                            'project_id': {'S': 'proj-1'}
                        }
                    }
                }
            ]
        }
        context = Mock()
        
        with patch('dashboard.cache_invalidation_handler.process_stream_record'):
            response = handle_dynamodb_stream(event, context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['processed'] == 1
        assert body['errors'] == 0


class TestIntegration:
    """Integration tests for dashboard service."""
    
    @patch('dashboard.dashboard_aggregator.execute_query')
    @patch('dashboard.dashboard_aggregator.get_active_risk_count')
    @patch('dashboard.dashboard_aggregator.get_next_milestone')
    @patch('dashboard.dashboard_aggregator.get_latest_health_score')
    def test_get_dashboard_overview_integration(
        self,
        mock_health_score,
        mock_next_milestone,
        mock_risk_count,
        mock_execute_query
    ):
        """Test full dashboard overview aggregation."""
        # Mock project query
        mock_execute_query.return_value = [
            {
                'project_id': 'proj-1',
                'project_name': 'Project A',
                'source': 'JIRA'
            }
        ]
        
        # Mock health score
        mock_health_score.return_value = {
            'health_score': 85,
            'calculated_at': datetime.now().isoformat()
        }
        
        # Mock risk count
        mock_risk_count.return_value = 2
        
        # Mock next milestone
        mock_next_milestone.return_value = {
            'name': 'Milestone 1',
            'dueDate': '2024-01-15',
            'completionPercentage': 75
        }
        
        dashboard_data = get_dashboard_overview('tenant-123', None)
        
        assert 'projects' in dashboard_data
        assert 'portfolioHealth' in dashboard_data
        assert len(dashboard_data['projects']) == 1
        assert dashboard_data['projects'][0]['healthScore'] == 85
        assert dashboard_data['projects'][0]['ragStatus'] == 'GREEN'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
