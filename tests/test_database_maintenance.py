"""
Tests for database maintenance Lambda function.

Validates Requirements 18.7, 23.1
"""

import pytest
import json
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime
import sys

# Mock psycopg2 before importing handler
sys.modules['psycopg2'] = MagicMock()
sys.modules['psycopg2.extras'] = MagicMock()
sys.modules['psycopg2.extensions'] = MagicMock()

# Create mock psycopg2 module with necessary attributes
psycopg2_mock = sys.modules['psycopg2']
psycopg2_mock.Error = Exception
psycopg2_mock.OperationalError = Exception
psycopg2_mock.extensions.ISOLATION_LEVEL_AUTOCOMMIT = 0


# Mock the database_maintenance handler module
@pytest.fixture
def mock_secrets_manager():
    """Mock AWS Secrets Manager."""
    with patch('database_maintenance.handler.secrets_manager') as mock:
        mock.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'host': 'test-db.amazonaws.com',
                'port': 5432,
                'username': 'postgres',
                'password': 'test-password'
            })
        }
        yield mock


@pytest.fixture
def mock_cloudwatch():
    """Mock AWS CloudWatch."""
    with patch('database_maintenance.handler.cloudwatch') as mock:
        yield mock


@pytest.fixture
def mock_db_connection():
    """Mock database connection."""
    with patch('database_maintenance.handler.psycopg2.connect') as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # Configure cursor context manager
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = None
        
        mock_connect.return_value = mock_conn
        
        yield mock_conn, mock_cursor


class TestDatabaseMaintenance:
    """Test database maintenance Lambda function."""

    def test_refresh_materialized_views_success(
        self,
        mock_secrets_manager,
        mock_cloudwatch,
        mock_db_connection
    ):
        """Test successful materialized view refresh."""
        from database_maintenance.handler import lambda_handler
        
        mock_conn, mock_cursor = mock_db_connection
        
        # Arrange
        event = {
            'task': 'refresh_views'
        }
        context = {}
        
        # Act
        response = lambda_handler(event, context)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['task'] == 'refresh_views'
        assert body['success'] is True
        assert 'refresh_views' in body['results']
        
        # Verify materialized views were refreshed
        refresh_results = body['results']['refresh_views']
        assert len(refresh_results['views_refreshed']) == 3
        
        view_names = [v['view'] for v in refresh_results['views_refreshed']]
        assert 'project_metrics_summary' in view_names
        assert 'sprint_velocity_trends' in view_names
        assert 'milestone_status_summary' in view_names
        
        # Verify SQL commands were executed
        expected_calls = [
            call('REFRESH MATERIALIZED VIEW CONCURRENTLY project_metrics_summary'),
            call('REFRESH MATERIALIZED VIEW CONCURRENTLY sprint_velocity_trends'),
            call('REFRESH MATERIALIZED VIEW CONCURRENTLY milestone_status_summary')
        ]
        mock_cursor.execute.assert_has_calls(expected_calls, any_order=False)
        
        # Verify CloudWatch metrics were sent
        assert mock_cloudwatch.put_metric_data.call_count == 3

    def test_refresh_views_within_30_seconds(
        self,
        mock_secrets_manager,
        mock_cloudwatch,
        mock_db_connection
    ):
        """
        Test that materialized view refresh completes within 30 seconds.
        Validates Requirement 18.7.
        """
        from database_maintenance.handler import lambda_handler
        
        mock_conn, mock_cursor = mock_db_connection
        
        # Arrange
        event = {'task': 'refresh_views'}
        context = {}
        
        # Act
        start_time = datetime.utcnow()
        response = lambda_handler(event, context)
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        
        # Verify total duration is under 30 seconds (Requirement 18.7)
        assert body['results']['refresh_views']['duration_seconds'] < 30
        assert duration < 30
        
        # Verify each view refresh is tracked
        for view in body['results']['refresh_views']['views_refreshed']:
            assert view['duration_seconds'] >= 0
            assert view['status'] == 'success'

    def test_vacuum_analyze_success(
        self,
        mock_secrets_manager,
        mock_cloudwatch,
        mock_db_connection
    ):
        """Test successful VACUUM ANALYZE execution."""
        from database_maintenance.handler import lambda_handler
        
        mock_conn, mock_cursor = mock_db_connection
        
        # Arrange
        event = {'task': 'vacuum_analyze'}
        context = {}
        
        # Act
        response = lambda_handler(event, context)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['task'] == 'vacuum_analyze'
        assert body['success'] is True
        
        # Verify tables were analyzed
        vacuum_results = body['results']['vacuum_analyze']
        assert len(vacuum_results['tables_analyzed']) == 8
        
        table_names = [t['table'] for t in vacuum_results['tables_analyzed']]
        expected_tables = [
            'tenants', 'projects', 'sprints', 'backlog_items',
            'milestones', 'resources', 'dependencies', 'health_scores'
        ]
        for table in expected_tables:
            assert table in table_names
        
        # Verify VACUUM ANALYZE was called for each table
        assert mock_cursor.execute.call_count == 8

    def test_check_slow_queries(
        self,
        mock_secrets_manager,
        mock_cloudwatch,
        mock_db_connection
    ):
        """
        Test slow query detection.
        Validates Requirement 23.1 (queries should be < 2 seconds).
        """
        from database_maintenance.handler import lambda_handler
        
        mock_conn, mock_cursor = mock_db_connection
        
        # Arrange - Mock slow queries
        mock_cursor.fetchall.return_value = [
            {
                'query': 'SELECT * FROM projects WHERE tenant_id = $1',
                'calls': 1000,
                'total_exec_time': 2500000,  # 2.5 seconds total
                'mean_exec_time': 2500,  # 2.5 seconds average
                'max_exec_time': 5000  # 5 seconds max
            },
            {
                'query': 'SELECT * FROM sprints WHERE project_id = $1',
                'calls': 500,
                'total_exec_time': 1100000,  # 1.1 seconds total
                'mean_exec_time': 2200,  # 2.2 seconds average
                'max_exec_time': 3000  # 3 seconds max
            }
        ]
        
        event = {'task': 'check_performance'}
        context = {}
        
        # Act
        response = lambda_handler(event, context)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        
        # Verify slow queries were detected
        slow_queries = body['results']['slow_queries']
        assert slow_queries['slow_queries_count'] == 2
        
        # Verify queries exceed 2-second threshold (Requirement 23.1)
        for query in slow_queries['slow_queries']:
            assert query['mean_exec_time_ms'] > 2000
        
        # Verify CloudWatch metrics were sent
        assert mock_cloudwatch.put_metric_data.call_count >= 2

    def test_check_table_sizes(
        self,
        mock_secrets_manager,
        mock_cloudwatch,
        mock_db_connection
    ):
        """Test table size monitoring."""
        from database_maintenance.handler import lambda_handler
        
        mock_conn, mock_cursor = mock_db_connection
        
        # Arrange - Mock table sizes
        mock_cursor.fetchall.side_effect = [
            [],  # No slow queries
            [  # Table sizes
                {
                    'schemaname': 'public',
                    'tablename': 'sprints',
                    'total_bytes': 104857600,  # 100 MB
                    'table_bytes': 83886080,   # 80 MB
                    'index_bytes': 20971520    # 20 MB
                },
                {
                    'schemaname': 'public',
                    'tablename': 'backlog_items',
                    'total_bytes': 52428800,   # 50 MB
                    'table_bytes': 41943040,   # 40 MB
                    'index_bytes': 10485760    # 10 MB
                }
            ]
        ]
        
        event = {'task': 'check_performance'}
        context = {}
        
        # Act
        response = lambda_handler(event, context)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        
        # Verify table sizes were checked
        table_sizes = body['results']['table_sizes']
        assert len(table_sizes['table_sizes']) == 2
        
        # Verify size calculations
        sprints_size = table_sizes['table_sizes'][0]
        assert sprints_size['table'] == 'sprints'
        assert sprints_size['total_mb'] == 100.0
        assert sprints_size['table_mb'] == 80.0
        assert sprints_size['index_mb'] == 20.0

    def test_all_tasks_execution(
        self,
        mock_secrets_manager,
        mock_cloudwatch,
        mock_db_connection
    ):
        """Test execution of all maintenance tasks."""
        from database_maintenance.handler import lambda_handler
        
        mock_conn, mock_cursor = mock_db_connection
        mock_cursor.fetchall.return_value = []  # No slow queries
        
        # Arrange
        event = {'task': 'all'}
        context = {}
        
        # Act
        response = lambda_handler(event, context)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['task'] == 'all'
        assert body['success'] is True
        
        # Verify all tasks were executed
        assert 'refresh_views' in body['results']
        assert 'vacuum_analyze' in body['results']
        assert 'slow_queries' in body['results']
        assert 'table_sizes' in body['results']

    def test_database_connection_failure(
        self,
        mock_secrets_manager,
        mock_cloudwatch
    ):
        """Test handling of database connection failure."""
        from database_maintenance.handler import lambda_handler
        
        # Arrange - Mock connection failure
        with patch('database_maintenance.handler.psycopg2.connect') as mock_connect:
            mock_connect.side_effect = Exception("Connection failed")
            
            event = {'task': 'refresh_views'}
            context = {}
            
            # Act
            response = lambda_handler(event, context)
            
            # Assert
            assert response['statusCode'] == 500
            body = json.loads(response['body'])
            assert 'error' in body
            assert 'Connection failed' in body['error']

    def test_materialized_view_refresh_failure(
        self,
        mock_secrets_manager,
        mock_cloudwatch,
        mock_db_connection
    ):
        """Test handling of materialized view refresh failure."""
        from database_maintenance.handler import lambda_handler
        
        mock_conn, mock_cursor = mock_db_connection
        
        # Arrange - Mock refresh failure
        mock_cursor.execute.side_effect = Exception("Refresh failed")
        
        event = {'task': 'refresh_views'}
        context = {}
        
        # Act
        response = lambda_handler(event, context)
        
        # Assert
        assert response['statusCode'] == 200  # Lambda succeeds even if refresh fails
        body = json.loads(response['body'])
        assert body['success'] is False  # But task is marked as failed
        
        # Verify errors were recorded
        refresh_results = body['results']['refresh_views']
        assert len(refresh_results['errors']) > 0

    def test_cloudwatch_metrics_sent(
        self,
        mock_secrets_manager,
        mock_cloudwatch,
        mock_db_connection
    ):
        """Test that CloudWatch metrics are sent for monitoring."""
        from database_maintenance.handler import lambda_handler
        
        mock_conn, mock_cursor = mock_db_connection
        
        # Arrange
        event = {'task': 'refresh_views'}
        context = {}
        
        # Act
        response = lambda_handler(event, context)
        
        # Assert
        assert response['statusCode'] == 200
        
        # Verify CloudWatch metrics were sent
        assert mock_cloudwatch.put_metric_data.call_count == 3
        
        # Verify metric structure
        for call_args in mock_cloudwatch.put_metric_data.call_args_list:
            kwargs = call_args[1]
            assert kwargs['Namespace'] == 'AI-SW-PM/Database'
            assert 'MetricData' in kwargs
            
            metric_data = kwargs['MetricData'][0]
            assert 'MetricName' in metric_data
            assert 'Value' in metric_data
            assert 'Unit' in metric_data
            assert metric_data['MetricName'] == 'MaterializedViewRefreshDuration'

    def test_tenant_specific_refresh(
        self,
        mock_secrets_manager,
        mock_cloudwatch,
        mock_db_connection
    ):
        """Test tenant-specific materialized view refresh."""
        from database_maintenance.handler import lambda_handler
        
        mock_conn, mock_cursor = mock_db_connection
        
        # Arrange
        event = {
            'task': 'refresh_views',
            'tenant_id': 'tenant-123'
        }
        context = {}
        
        # Act
        response = lambda_handler(event, context)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['success'] is True
        
        # Verify views were refreshed (tenant-specific refresh still refreshes all views)
        refresh_results = body['results']['refresh_views']
        assert len(refresh_results['views_refreshed']) == 3


class TestPerformanceRequirements:
    """Test performance requirements validation."""

    def test_requirement_18_7_health_score_recalculation(
        self,
        mock_secrets_manager,
        mock_cloudwatch,
        mock_db_connection
    ):
        """
        Validate Requirement 18.7:
        Health score recalculation within 30 seconds of data updates.
        """
        from database_maintenance.handler import lambda_handler
        
        mock_conn, mock_cursor = mock_db_connection
        
        # Arrange
        event = {'task': 'refresh_views'}
        context = {}
        
        # Act
        response = lambda_handler(event, context)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        
        # Requirement 18.7: Recalculation within 30 seconds
        duration = body['results']['refresh_views']['duration_seconds']
        assert duration < 30, f"Refresh took {duration}s, expected < 30s"
        
        # Verify all views refreshed successfully
        assert len(body['results']['refresh_views']['views_refreshed']) == 3
        assert len(body['results']['refresh_views']['errors']) == 0

    def test_requirement_23_1_api_response_time(
        self,
        mock_secrets_manager,
        mock_cloudwatch,
        mock_db_connection
    ):
        """
        Validate Requirement 23.1:
        API responds within 2 seconds for 95% of requests.
        
        This test verifies that slow queries (> 2 seconds) are detected.
        """
        from database_maintenance.handler import lambda_handler
        
        mock_conn, mock_cursor = mock_db_connection
        
        # Arrange - Mock slow queries that violate Requirement 23.1
        mock_cursor.fetchall.return_value = [
            {
                'query': 'SELECT * FROM projects',
                'calls': 100,
                'total_exec_time': 250000,
                'mean_exec_time': 2500,  # 2.5 seconds - VIOLATES REQUIREMENT
                'max_exec_time': 4000
            }
        ]
        
        event = {'task': 'check_performance'}
        context = {}
        
        # Act
        response = lambda_handler(event, context)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        
        # Verify slow queries were detected
        slow_queries = body['results']['slow_queries']
        assert slow_queries['slow_queries_count'] > 0
        
        # Requirement 23.1: Queries should be < 2000ms
        for query in slow_queries['slow_queries']:
            # These queries violate the requirement and should be flagged
            assert query['mean_exec_time_ms'] > 2000


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
