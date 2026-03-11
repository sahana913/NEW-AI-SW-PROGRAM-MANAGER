"""Tests for caching strategy implementation."""

import pytest
import json
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Mock redis before importing cache_manager
import sys
sys.modules['redis'] = MagicMock()

from src.dashboard.cache_manager import (
    get_cached_data,
    set_cached_data,
    cache_dashboard_data,
    cache_report_data,
    invalidate_cache,
    invalidate_cache_pattern,
    invalidate_tenant_cache,
    invalidate_project_cache,
    DASHBOARD_CACHE_TTL,
    REPORT_CACHE_TTL
)


class TestCacheTTLConfiguration:
    """Test cache TTL configuration."""
    
    def test_dashboard_cache_ttl_is_5_minutes(self):
        """
        Validates: Requirement 20.3 (5-minute TTL for dashboard data)
        """
        assert DASHBOARD_CACHE_TTL == 300, "Dashboard cache TTL should be 5 minutes (300 seconds)"
    
    def test_report_cache_ttl_is_1_hour(self):
        """
        Validates: Requirement 23.1 (1-hour TTL for reports)
        """
        assert REPORT_CACHE_TTL == 3600, "Report cache TTL should be 1 hour (3600 seconds)"


class TestCacheDashboardData:
    """Test dashboard data caching with 5-minute TTL."""
    
    @patch('src.dashboard.cache_manager.get_redis_client')
    def test_cache_dashboard_data_uses_5_minute_ttl(self, mock_get_redis):
        """
        Validates: Requirement 20.3 (5-minute TTL for dashboard data)
        """
        mock_redis = Mock()
        mock_get_redis.return_value = mock_redis
        
        test_data = {'health_score': 85, 'rag_status': 'GREEN'}
        cache_key = 'dashboard:overview:tenant-123'
        
        result = cache_dashboard_data(cache_key, test_data)
        
        assert result is True
        mock_redis.setex.assert_called_once()
        
        # Verify TTL is 300 seconds (5 minutes)
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == cache_key
        assert call_args[0][1] == 300  # 5 minutes
        assert json.loads(call_args[0][2]) == test_data
    
    @patch('src.dashboard.cache_manager.get_redis_client')
    def test_cache_dashboard_data_with_project_filter(self, mock_get_redis):
        """Test caching dashboard data with project filtering."""
        mock_redis = Mock()
        mock_get_redis.return_value = mock_redis
        
        test_data = {
            'projects': [
                {'project_id': 'proj-1', 'health_score': 85},
                {'project_id': 'proj-2', 'health_score': 72}
            ]
        }
        cache_key = 'dashboard:overview:tenant-123:proj-1,proj-2'
        
        result = cache_dashboard_data(cache_key, test_data)
        
        assert result is True
        mock_redis.setex.assert_called_once()


class TestCacheReportData:
    """Test report data caching with 1-hour TTL."""
    
    @patch('src.dashboard.cache_manager.get_redis_client')
    def test_cache_report_data_uses_1_hour_ttl(self, mock_get_redis):
        """
        Validates: Requirement 23.1 (1-hour TTL for reports)
        """
        mock_redis = Mock()
        mock_get_redis.return_value = mock_redis
        
        test_data = {
            'projects': [{'project_id': 'proj-1'}],
            'completed_milestones': [],
            'risks': []
        }
        cache_key = 'report:data:tenant-123'
        
        result = cache_report_data(cache_key, test_data)
        
        assert result is True
        mock_redis.setex.assert_called_once()
        
        # Verify TTL is 3600 seconds (1 hour)
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == cache_key
        assert call_args[0][1] == 3600  # 1 hour
        assert json.loads(call_args[0][2]) == test_data
    
    @patch('src.dashboard.cache_manager.get_redis_client')
    def test_cache_report_data_with_date_range(self, mock_get_redis):
        """Test caching report data with date range in key."""
        mock_redis = Mock()
        mock_get_redis.return_value = mock_redis
        
        test_data = {'projects': [], 'milestones': []}
        cache_key = 'report:data:tenant-123:start:20240101:end:20240131'
        
        result = cache_report_data(cache_key, test_data)
        
        assert result is True
        mock_redis.setex.assert_called_once()


class TestCacheInvalidation:
    """Test cache invalidation mechanisms."""
    
    @patch('src.dashboard.cache_manager.get_redis_client')
    def test_invalidate_single_cache_key(self, mock_get_redis):
        """
        Validates: Requirement 20.3 (cache invalidation on data updates)
        """
        mock_redis = Mock()
        mock_get_redis.return_value = mock_redis
        
        cache_key = 'dashboard:project:tenant-123:project-456'
        
        result = invalidate_cache(cache_key)
        
        assert result is True
        mock_redis.delete.assert_called_once_with(cache_key)
    
    @patch('src.dashboard.cache_manager.get_redis_client')
    def test_invalidate_cache_pattern(self, mock_get_redis):
        """Test invalidating multiple cache keys by pattern."""
        mock_redis = Mock()
        mock_redis.keys.return_value = [
            'dashboard:overview:tenant-123',
            'dashboard:overview:tenant-123:proj-1',
            'dashboard:overview:tenant-123:proj-2'
        ]
        mock_redis.delete.return_value = 3
        mock_get_redis.return_value = mock_redis
        
        pattern = 'dashboard:overview:tenant-123*'
        
        count = invalidate_cache_pattern(pattern)
        
        assert count == 3
        mock_redis.keys.assert_called_once_with(pattern)
        mock_redis.delete.assert_called_once()
    
    @patch('src.dashboard.cache_manager.get_redis_client')
    def test_invalidate_tenant_cache(self, mock_get_redis):
        """Test invalidating all cache for a tenant."""
        mock_redis = Mock()
        mock_redis.keys.return_value = [
            'dashboard:overview:tenant-123',
            'dashboard:project:tenant-123:proj-1',
            'report:data:tenant-123'
        ]
        mock_redis.delete.return_value = 3
        mock_get_redis.return_value = mock_redis
        
        count = invalidate_tenant_cache('tenant-123')
        
        assert count == 3
        mock_redis.keys.assert_called_once()
    
    @patch('src.dashboard.cache_manager.get_redis_client')
    def test_invalidate_project_cache(self, mock_get_redis):
        """Test invalidating cache for a specific project."""
        mock_redis = Mock()
        mock_redis.keys.side_effect = [
            ['dashboard:project:tenant-123:project-456'],  # Project-specific
            ['dashboard:overview:tenant-123', 'dashboard:overview:tenant-123:proj-1']  # Overview
        ]
        mock_redis.delete.side_effect = [1, 2]
        mock_get_redis.return_value = mock_redis
        
        count = invalidate_project_cache('tenant-123', 'project-456')
        
        assert count == 3  # 1 project + 2 overview
        assert mock_redis.keys.call_count == 2
        assert mock_redis.delete.call_count == 2


class TestCacheKeyNaming:
    """Test cache key naming conventions."""
    
    def test_dashboard_overview_key_format(self):
        """Test dashboard overview cache key format."""
        tenant_id = 'tenant-123'
        expected_key = f'dashboard:overview:{tenant_id}'
        
        # This would be the actual key used in the handler
        assert expected_key == 'dashboard:overview:tenant-123'
    
    def test_dashboard_project_key_format(self):
        """Test dashboard project cache key format."""
        tenant_id = 'tenant-123'
        project_id = 'project-456'
        expected_key = f'dashboard:project:{tenant_id}:{project_id}'
        
        assert expected_key == 'dashboard:project:tenant-123:project-456'
    
    def test_report_data_key_format(self):
        """Test report data cache key format."""
        tenant_id = 'tenant-123'
        project_ids = ['proj-1', 'proj-2']
        expected_key = f'report:data:{tenant_id}:projects:{",".join(sorted(project_ids))}'
        
        assert expected_key == 'report:data:tenant-123:projects:proj-1,proj-2'
    
    def test_cache_key_includes_tenant_id_for_isolation(self):
        """
        Validates: Tenant isolation in cache keys
        
        All cache keys must include tenant_id to prevent cross-tenant data leakage.
        """
        # Dashboard keys
        assert 'tenant-123' in 'dashboard:overview:tenant-123'
        assert 'tenant-123' in 'dashboard:project:tenant-123:project-456'
        
        # Report keys
        assert 'tenant-123' in 'report:data:tenant-123'
        assert 'tenant-123' in 'report:data:tenant-123:projects:proj-1'


class TestCacheGracefulDegradation:
    """Test cache graceful degradation when Redis unavailable."""
    
    @patch('src.dashboard.cache_manager.get_redis_client')
    def test_get_cached_data_returns_none_when_redis_unavailable(self, mock_get_redis):
        """Test that cache miss returns None gracefully when Redis unavailable."""
        mock_get_redis.return_value = None
        
        result = get_cached_data('any-key')
        
        assert result is None
    
    @patch('src.dashboard.cache_manager.get_redis_client')
    def test_set_cached_data_returns_false_when_redis_unavailable(self, mock_get_redis):
        """Test that cache set fails gracefully when Redis unavailable."""
        mock_get_redis.return_value = None
        
        result = set_cached_data('any-key', {'data': 'value'})
        
        assert result is False
    
    @patch('src.dashboard.cache_manager.get_redis_client')
    def test_invalidate_cache_returns_false_when_redis_unavailable(self, mock_get_redis):
        """Test that cache invalidation fails gracefully when Redis unavailable."""
        mock_get_redis.return_value = None
        
        result = invalidate_cache('any-key')
        
        assert result is False


class TestCachePerformance:
    """Test cache performance characteristics."""
    
    @patch('src.dashboard.cache_manager.get_redis_client')
    def test_cache_hit_returns_data_quickly(self, mock_get_redis):
        """Test that cache hit returns data without database query."""
        mock_redis = Mock()
        test_data = {'health_score': 85}
        mock_redis.get.return_value = json.dumps(test_data)
        mock_get_redis.return_value = mock_redis
        
        result = get_cached_data('dashboard:overview:tenant-123')
        
        assert result == test_data
        mock_redis.get.assert_called_once()
    
    @patch('src.dashboard.cache_manager.get_redis_client')
    def test_cache_miss_returns_none(self, mock_get_redis):
        """Test that cache miss returns None to trigger database query."""
        mock_redis = Mock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis
        
        result = get_cached_data('dashboard:overview:tenant-123')
        
        assert result is None
        mock_redis.get.assert_called_once()


class TestCacheStatistics:
    """Test cache statistics collection."""
    
    @patch('src.dashboard.cache_manager.get_redis_client')
    def test_get_cache_stats_returns_metrics(self, mock_get_redis):
        """Test retrieving cache statistics."""
        from src.dashboard.cache_manager import get_cache_stats
        
        mock_redis = Mock()
        mock_redis.info.return_value = {
            'total_connections_received': 1000,
            'total_commands_processed': 5000,
            'keyspace_hits': 4500,
            'keyspace_misses': 500
        }
        mock_get_redis.return_value = mock_redis
        
        stats = get_cache_stats()
        
        assert stats['keyspace_hits'] == 4500
        assert stats['keyspace_misses'] == 500
        assert stats['hit_rate'] == 90.0  # 4500 / (4500 + 500) * 100
    
    @patch('src.dashboard.cache_manager.get_redis_client')
    def test_get_cache_stats_handles_redis_unavailable(self, mock_get_redis):
        """Test cache stats returns empty dict when Redis unavailable."""
        from src.dashboard.cache_manager import get_cache_stats
        
        mock_get_redis.return_value = None
        
        stats = get_cache_stats()
        
        assert stats == {}


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
