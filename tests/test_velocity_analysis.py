"""Tests for velocity trend analysis."""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, date, timedelta

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from risk_detection.velocity_analysis import (
    query_last_sprints,
    calculate_velocity_trend,
    detect_velocity_decline,
    analyze_velocity_risk
)


class TestQueryLastSprints:
    """Tests for query_last_sprints function."""
    
    @patch('risk_detection.velocity_analysis.execute_query')
    def test_query_last_sprints_success(self, mock_execute):
        """Test successful sprint query."""
        # Mock data
        mock_sprints = [
            {
                'sprint_id': 'sprint-4',
                'sprint_name': 'Sprint 4',
                'start_date': date(2024, 1, 22),
                'end_date': date(2024, 2, 5),
                'velocity': 30.0,
                'completed_points': 30.0,
                'planned_points': 35.0,
                'completion_rate': 85.7
            },
            {
                'sprint_id': 'sprint-3',
                'sprint_name': 'Sprint 3',
                'start_date': date(2024, 1, 8),
                'end_date': date(2024, 1, 22),
                'velocity': 35.0,
                'completed_points': 35.0,
                'planned_points': 40.0,
                'completion_rate': 87.5
            }
        ]
        
        mock_execute.return_value = mock_sprints
        
        # Execute
        result = query_last_sprints('project-123', limit=4)
        
        # Verify
        assert len(result) == 2
        assert result[0]['sprint_id'] == 'sprint-3'  # Reversed to chronological
        assert result[1]['sprint_id'] == 'sprint-4'
        mock_execute.assert_called_once()
    
    @patch('risk_detection.velocity_analysis.execute_query')
    def test_query_last_sprints_empty(self, mock_execute):
        """Test query with no sprints."""
        mock_execute.return_value = []
        
        result = query_last_sprints('project-123')
        
        assert result == []


class TestCalculateVelocityTrend:
    """Tests for calculate_velocity_trend function."""
    
    def test_calculate_velocity_trend_declining(self):
        """Test velocity trend calculation with declining velocity."""
        sprints = [
            {'velocity': 40.0},
            {'velocity': 38.0},
            {'velocity': 32.0},
            {'velocity': 25.0}
        ]
        
        result = calculate_velocity_trend(sprints)
        
        assert result['moving_average'] == 33.75
        assert result['current_velocity'] == 25.0
        assert result['previous_velocity'] == 32.0
        assert result['trend'] == 'DECLINING'
        assert result['decline_percentage'] > 0
    
    def test_calculate_velocity_trend_improving(self):
        """Test velocity trend calculation with improving velocity."""
        sprints = [
            {'velocity': 25.0},
            {'velocity': 30.0},
            {'velocity': 35.0},
            {'velocity': 40.0}
        ]
        
        result = calculate_velocity_trend(sprints)
        
        assert result['moving_average'] == 32.5
        assert result['current_velocity'] == 40.0
        assert result['trend'] == 'IMPROVING'
    
    def test_calculate_velocity_trend_stable(self):
        """Test velocity trend calculation with stable velocity."""
        sprints = [
            {'velocity': 30.0},
            {'velocity': 31.0},
            {'velocity': 29.0},
            {'velocity': 30.0}
        ]
        
        result = calculate_velocity_trend(sprints)
        
        assert result['trend'] == 'STABLE'
    
    def test_calculate_velocity_trend_empty(self):
        """Test velocity trend with no sprints."""
        result = calculate_velocity_trend([])
        
        assert result['moving_average'] == 0
        assert result['current_velocity'] == 0
        assert result['trend'] == 'STABLE'


class TestDetectVelocityDecline:
    """Tests for detect_velocity_decline function."""
    
    def test_detect_velocity_decline_high_severity(self):
        """Test detection of high severity velocity decline."""
        sprints = [
            {'velocity': 40.0},
            {'velocity': 38.0},
            {'velocity': 35.0},
            {'velocity': 25.0}  # 28.6% decline from previous
        ]
        
        velocity_metrics = calculate_velocity_trend(sprints)
        result = detect_velocity_decline(sprints, velocity_metrics)
        
        assert result is not None
        assert result['type'] == 'VELOCITY_DECLINE'
        assert result['severity'] in ['MEDIUM', 'HIGH']
        assert 'title' in result
        assert 'metrics' in result
    
    def test_detect_velocity_decline_critical_severity(self):
        """Test detection of critical severity velocity decline."""
        sprints = [
            {'velocity': 40.0},
            {'velocity': 38.0},
            {'velocity': 35.0},
            {'velocity': 20.0}  # 42.9% decline from previous
        ]
        
        velocity_metrics = calculate_velocity_trend(sprints)
        result = detect_velocity_decline(sprints, velocity_metrics)
        
        assert result is not None
        assert result['severity'] == 'CRITICAL'
    
    def test_detect_velocity_decline_no_risk(self):
        """Test no risk detected when velocity is stable."""
        sprints = [
            {'velocity': 30.0},
            {'velocity': 31.0},
            {'velocity': 29.0},
            {'velocity': 30.0}
        ]
        
        velocity_metrics = calculate_velocity_trend(sprints)
        result = detect_velocity_decline(sprints, velocity_metrics)
        
        assert result is None
    
    def test_detect_velocity_decline_insufficient_data(self):
        """Test no risk with insufficient sprint data."""
        sprints = [{'velocity': 30.0}]
        
        velocity_metrics = calculate_velocity_trend(sprints)
        result = detect_velocity_decline(sprints, velocity_metrics)
        
        assert result is None


class TestAnalyzeVelocityRisk:
    """Tests for analyze_velocity_risk function."""
    
    @patch('risk_detection.velocity_analysis.query_last_sprints')
    def test_analyze_velocity_risk_detected(self, mock_query):
        """Test velocity risk analysis with risk detected."""
        mock_query.return_value = [
            {'velocity': 40.0},
            {'velocity': 38.0},
            {'velocity': 32.0},
            {'velocity': 25.0}
        ]
        
        result = analyze_velocity_risk('project-123', 'tenant-456')
        
        assert result is not None
        assert result['type'] == 'VELOCITY_DECLINE'
        assert result['project_id'] == 'project-123'
        assert result['tenant_id'] == 'tenant-456'
    
    @patch('risk_detection.velocity_analysis.query_last_sprints')
    def test_analyze_velocity_risk_no_risk(self, mock_query):
        """Test velocity risk analysis with no risk."""
        mock_query.return_value = [
            {'velocity': 30.0},
            {'velocity': 31.0},
            {'velocity': 29.0},
            {'velocity': 30.0}
        ]
        
        result = analyze_velocity_risk('project-123', 'tenant-456')
        
        assert result is None
    
    @patch('risk_detection.velocity_analysis.query_last_sprints')
    def test_analyze_velocity_risk_insufficient_data(self, mock_query):
        """Test velocity risk analysis with insufficient data."""
        mock_query.return_value = [{'velocity': 30.0}]
        
        result = analyze_velocity_risk('project-123', 'tenant-456')
        
        assert result is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
