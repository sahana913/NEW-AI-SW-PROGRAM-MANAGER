"""Tests for backlog growth analysis."""

import pytest
import sys
import os
from unittest.mock import Mock, patch
from datetime import datetime, date

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from risk_detection.backlog_analysis import (
    query_backlog_metrics,
    calculate_team_completion_rate,
    calculate_backlog_growth_rate,
    detect_backlog_growth_risk,
    analyze_backlog_risk
)


class TestQueryBacklogMetrics:
    """Tests for query_backlog_metrics function."""
    
    @patch('risk_detection.backlog_analysis.execute_query')
    def test_query_backlog_metrics_success(self, mock_execute):
        """Test successful backlog metrics query."""
        mock_execute.return_value = [{
            'total_items': 150,
            'open_items': 100,
            'bug_count': 30,
            'feature_count': 60,
            'tech_debt_count': 10,
            'average_age': 15.5
        }]
        
        result = query_backlog_metrics('project-123')
        
        assert result['total_items'] == 150
        assert result['open_items'] == 100
        assert result['items_by_type']['bug'] == 30
        assert result['items_by_type']['feature'] == 60
        assert result['items_by_type']['technical_debt'] == 10
        assert result['average_age'] == 15.5
    
    @patch('risk_detection.backlog_analysis.execute_query')
    def test_query_backlog_metrics_empty(self, mock_execute):
        """Test backlog metrics with no items."""
        mock_execute.return_value = []
        
        result = query_backlog_metrics('project-123')
        
        assert result['total_items'] == 0
        assert result['open_items'] == 0


class TestCalculateTeamCompletionRate:
    """Tests for calculate_team_completion_rate function."""
    
    @patch('risk_detection.backlog_analysis.execute_query')
    def test_calculate_completion_rate_success(self, mock_execute):
        """Test successful completion rate calculation."""
        mock_execute.return_value = [{
            'avg_completed_points': 30.0,
            'avg_sprint_weeks': 2.0
        }]
        
        result = calculate_team_completion_rate('project-123')
        
        assert result == 15.0  # 30 points / 2 weeks
    
    @patch('risk_detection.backlog_analysis.execute_query')
    def test_calculate_completion_rate_no_data(self, mock_execute):
        """Test completion rate with no sprint data."""
        mock_execute.return_value = []
        
        result = calculate_team_completion_rate('project-123')
        
        assert result == 0


class TestCalculateBacklogGrowthRate:
    """Tests for calculate_backlog_growth_rate function."""
    
    def test_calculate_growth_rate_positive(self):
        """Test positive growth rate calculation."""
        historical_data = [
            {'week_start': date(2024, 1, 1), 'open_items': 100},
            {'week_start': date(2024, 1, 8), 'open_items': 130}
        ]
        
        result = calculate_backlog_growth_rate(historical_data)
        
        assert result == 30.0  # 30% growth
    
    def test_calculate_growth_rate_negative(self):
        """Test negative growth rate (backlog shrinking)."""
        historical_data = [
            {'week_start': date(2024, 1, 1), 'open_items': 100},
            {'week_start': date(2024, 1, 8), 'open_items': 80}
        ]
        
        result = calculate_backlog_growth_rate(historical_data)
        
        assert result == -20.0  # 20% decrease
    
    def test_calculate_growth_rate_insufficient_data(self):
        """Test growth rate with insufficient data."""
        historical_data = [
            {'week_start': date(2024, 1, 1), 'open_items': 100}
        ]
        
        result = calculate_backlog_growth_rate(historical_data)
        
        assert result == 0


class TestDetectBacklogGrowthRisk:
    """Tests for detect_backlog_growth_risk function."""
    
    def test_detect_rapid_growth_risk(self):
        """Test detection of rapid backlog growth."""
        backlog_metrics = {
            'open_items': 130,
            'total_items': 150,
            'items_by_type': {'bug': 40, 'feature': 80, 'technical_debt': 10},
            'average_age': 20.0
        }
        
        result = detect_backlog_growth_risk(
            backlog_metrics,
            growth_rate=35.0,  # 35% growth
            completion_rate=15.0
        )
        
        assert result is not None
        assert result['type'] == 'BACKLOG_GROWTH'
        assert result['severity'] in ['MEDIUM', 'HIGH', 'CRITICAL']
        assert 'title' in result
        assert 'metrics' in result
    
    def test_detect_excessive_backlog_risk(self):
        """Test detection of excessive backlog size."""
        backlog_metrics = {
            'open_items': 100,
            'total_items': 120,
            'items_by_type': {'bug': 30, 'feature': 60, 'technical_debt': 10},
            'average_age': 25.0
        }
        
        result = detect_backlog_growth_risk(
            backlog_metrics,
            growth_rate=10.0,  # Low growth
            completion_rate=20.0  # But backlog is 5x completion rate
        )
        
        assert result is not None
        assert result['type'] == 'BACKLOG_GROWTH'
    
    def test_detect_no_risk(self):
        """Test no risk detected with healthy backlog."""
        backlog_metrics = {
            'open_items': 30,
            'total_items': 50,
            'items_by_type': {'bug': 10, 'feature': 15, 'technical_debt': 5},
            'average_age': 10.0
        }
        
        result = detect_backlog_growth_risk(
            backlog_metrics,
            growth_rate=10.0,
            completion_rate=20.0
        )
        
        assert result is None
    
    def test_detect_critical_severity(self):
        """Test critical severity assignment."""
        backlog_metrics = {
            'open_items': 200,
            'total_items': 250,
            'items_by_type': {'bug': 80, 'feature': 100, 'technical_debt': 20},
            'average_age': 30.0
        }
        
        result = detect_backlog_growth_risk(
            backlog_metrics,
            growth_rate=55.0,  # Very high growth
            completion_rate=15.0
        )
        
        assert result is not None
        assert result['severity'] == 'CRITICAL'


class TestAnalyzeBacklogRisk:
    """Tests for analyze_backlog_risk function."""
    
    @patch('risk_detection.backlog_analysis.calculate_team_completion_rate')
    @patch('risk_detection.backlog_analysis.query_historical_backlog')
    @patch('risk_detection.backlog_analysis.query_backlog_metrics')
    def test_analyze_backlog_risk_detected(self, mock_metrics, mock_historical, mock_completion):
        """Test backlog risk analysis with risk detected."""
        mock_metrics.return_value = {
            'open_items': 130,
            'total_items': 150,
            'items_by_type': {'bug': 40, 'feature': 80, 'technical_debt': 10},
            'average_age': 20.0
        }
        
        mock_historical.return_value = [
            {'week_start': date(2024, 1, 1), 'open_items': 100},
            {'week_start': date(2024, 1, 8), 'open_items': 130}
        ]
        
        mock_completion.return_value = 15.0
        
        result = analyze_backlog_risk('project-123', 'tenant-456')
        
        assert result is not None
        assert result['type'] == 'BACKLOG_GROWTH'
        assert result['project_id'] == 'project-123'
        assert result['tenant_id'] == 'tenant-456'
    
    @patch('risk_detection.backlog_analysis.calculate_team_completion_rate')
    @patch('risk_detection.backlog_analysis.query_historical_backlog')
    @patch('risk_detection.backlog_analysis.query_backlog_metrics')
    def test_analyze_backlog_risk_no_risk(self, mock_metrics, mock_historical, mock_completion):
        """Test backlog risk analysis with no risk."""
        mock_metrics.return_value = {
            'open_items': 30,
            'total_items': 50,
            'items_by_type': {'bug': 10, 'feature': 15, 'technical_debt': 5},
            'average_age': 10.0
        }
        
        mock_historical.return_value = [
            {'week_start': date(2024, 1, 1), 'open_items': 28},
            {'week_start': date(2024, 1, 8), 'open_items': 30}
        ]
        
        mock_completion.return_value = 20.0
        
        result = analyze_backlog_risk('project-123', 'tenant-456')
        
        assert result is None
    
    @patch('risk_detection.backlog_analysis.query_backlog_metrics')
    def test_analyze_backlog_risk_no_items(self, mock_metrics):
        """Test backlog risk analysis with no backlog items."""
        mock_metrics.return_value = {
            'open_items': 0,
            'total_items': 0,
            'items_by_type': {'bug': 0, 'feature': 0, 'technical_debt': 0},
            'average_age': 0
        }
        
        result = analyze_backlog_risk('project-123', 'tenant-456')
        
        assert result is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
