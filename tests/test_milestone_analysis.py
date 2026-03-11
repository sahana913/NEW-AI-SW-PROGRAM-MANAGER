"""Tests for milestone slippage analysis."""

import pytest
import sys
import os
from unittest.mock import Mock, patch
from datetime import datetime, date, timedelta

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from risk_detection.milestone_analysis import (
    query_active_milestones,
    calculate_milestone_metrics,
    estimate_delay_days,
    detect_milestone_slippage_risk,
    analyze_milestone_risks
)


class TestQueryActiveMilestones:
    """Tests for query_active_milestones function."""
    
    @patch('risk_detection.milestone_analysis.execute_query')
    def test_query_active_milestones_success(self, mock_execute):
        """Test successful milestone query."""
        mock_execute.return_value = [
            {
                'milestone_id': 'milestone-1',
                'milestone_name': 'Phase 1 Complete',
                'due_date': date.today() + timedelta(days=30),
                'completion_percentage': 45.0,
                'status': 'AT_RISK',
                'source': 'JIRA'
            },
            {
                'milestone_id': 'milestone-2',
                'milestone_name': 'Phase 2 Complete',
                'due_date': date.today() + timedelta(days=60),
                'completion_percentage': 20.0,
                'status': 'ON_TRACK',
                'source': 'JIRA'
            }
        ]
        
        result = query_active_milestones('project-123')
        
        assert len(result) == 2
        assert result[0]['milestone_id'] == 'milestone-1'
    
    @patch('risk_detection.milestone_analysis.execute_query')
    def test_query_active_milestones_empty(self, mock_execute):
        """Test query with no active milestones."""
        mock_execute.return_value = []
        
        result = query_active_milestones('project-123')
        
        assert result == []


class TestCalculateMilestoneMetrics:
    """Tests for calculate_milestone_metrics function."""
    
    def test_calculate_metrics_at_risk(self):
        """Test metrics calculation for at-risk milestone."""
        milestone = {
            'milestone_id': 'milestone-1',
            'milestone_name': 'Phase 1',
            'due_date': date.today() + timedelta(days=10),
            'completion_percentage': 50.0
        }
        
        result = calculate_milestone_metrics(milestone)
        
        assert result['completion_percentage'] == 50.0
        assert result['time_remaining_days'] == 10
        assert result['time_remaining_percentage'] < 20
        assert result['is_at_risk'] == True
    
    def test_calculate_metrics_on_track(self):
        """Test metrics calculation for on-track milestone."""
        milestone = {
            'milestone_id': 'milestone-1',
            'milestone_name': 'Phase 1',
            'due_date': date.today() + timedelta(days=60),
            'completion_percentage': 75.0
        }
        
        result = calculate_milestone_metrics(milestone)
        
        assert result['completion_percentage'] == 75.0
        assert result['time_remaining_days'] == 60
        assert result['is_at_risk'] == False
    
    def test_calculate_metrics_no_due_date(self):
        """Test metrics calculation with no due date."""
        milestone = {
            'milestone_id': 'milestone-1',
            'milestone_name': 'Phase 1',
            'due_date': None,
            'completion_percentage': 50.0
        }
        
        result = calculate_milestone_metrics(milestone)
        
        assert result['time_remaining_days'] == 0
        assert result['is_at_risk'] == False


class TestEstimateDelayDays:
    """Tests for estimate_delay_days function."""
    
    def test_estimate_delay_on_track(self):
        """Test delay estimation for on-track milestone."""
        result = estimate_delay_days(
            completion_pct=75.0,
            time_remaining_days=30,
            project_id='project-123'
        )
        
        assert result == 0  # On track
    
    def test_estimate_delay_behind_schedule(self):
        """Test delay estimation for behind-schedule milestone."""
        result = estimate_delay_days(
            completion_pct=30.0,
            time_remaining_days=10,
            project_id='project-123'
        )
        
        assert result > 0  # Delayed
    
    def test_estimate_delay_past_due(self):
        """Test delay estimation for past-due milestone."""
        result = estimate_delay_days(
            completion_pct=50.0,
            time_remaining_days=-5,
            project_id='project-123'
        )
        
        assert result >= 5  # At least 5 days delayed


class TestDetectMilestoneSlippageRisk:
    """Tests for detect_milestone_slippage_risk function."""
    
    def test_detect_slippage_high_severity(self):
        """Test detection of high severity milestone slippage."""
        milestone = {
            'milestone_id': 'milestone-1',
            'milestone_name': 'Phase 1 Complete',
            'due_date': date.today() + timedelta(days=10)
        }
        
        metrics = {
            'completion_percentage': 50.0,
            'time_remaining_days': 10,
            'time_remaining_percentage': 11.0,
            'is_at_risk': True
        }
        
        result = detect_milestone_slippage_risk(milestone, metrics, 'project-123')
        
        assert result is not None
        assert result['type'] == 'MILESTONE_SLIPPAGE'
        assert result['severity'] in ['MEDIUM', 'HIGH', 'CRITICAL']
        assert result['milestone_name'] == 'Phase 1 Complete'
    
    def test_detect_slippage_critical_severity(self):
        """Test detection of critical severity milestone slippage."""
        milestone = {
            'milestone_id': 'milestone-1',
            'milestone_name': 'Phase 1 Complete',
            'due_date': date.today() + timedelta(days=5)
        }
        
        metrics = {
            'completion_percentage': 40.0,
            'time_remaining_days': 5,
            'time_remaining_percentage': 5.0,
            'is_at_risk': True
        }
        
        result = detect_milestone_slippage_risk(milestone, metrics, 'project-123')
        
        assert result is not None
        assert result['severity'] == 'CRITICAL'
    
    def test_detect_no_risk(self):
        """Test no risk detected for on-track milestone."""
        milestone = {
            'milestone_id': 'milestone-1',
            'milestone_name': 'Phase 1 Complete',
            'due_date': date.today() + timedelta(days=60)
        }
        
        metrics = {
            'completion_percentage': 75.0,
            'time_remaining_days': 60,
            'time_remaining_percentage': 66.0,
            'is_at_risk': False
        }
        
        result = detect_milestone_slippage_risk(milestone, metrics, 'project-123')
        
        assert result is None


class TestAnalyzeMilestoneRisks:
    """Tests for analyze_milestone_risks function."""
    
    @patch('risk_detection.milestone_analysis.query_active_milestones')
    def test_analyze_milestone_risks_detected(self, mock_query):
        """Test milestone risk analysis with risks detected."""
        mock_query.return_value = [
            {
                'milestone_id': 'milestone-1',
                'milestone_name': 'Phase 1 Complete',
                'due_date': date.today() + timedelta(days=10),
                'completion_percentage': 50.0,
                'status': 'AT_RISK',
                'source': 'JIRA'
            },
            {
                'milestone_id': 'milestone-2',
                'milestone_name': 'Phase 2 Complete',
                'due_date': date.today() + timedelta(days=5),
                'completion_percentage': 30.0,
                'status': 'AT_RISK',
                'source': 'JIRA'
            }
        ]
        
        result = analyze_milestone_risks('project-123', 'tenant-456')
        
        assert len(result) >= 1  # At least one risk detected
        assert all(r['type'] == 'MILESTONE_SLIPPAGE' for r in result)
        assert all(r['project_id'] == 'project-123' for r in result)
        assert all(r['tenant_id'] == 'tenant-456' for r in result)
    
    @patch('risk_detection.milestone_analysis.query_active_milestones')
    def test_analyze_milestone_risks_no_risk(self, mock_query):
        """Test milestone risk analysis with no risks."""
        mock_query.return_value = [
            {
                'milestone_id': 'milestone-1',
                'milestone_name': 'Phase 1 Complete',
                'due_date': date.today() + timedelta(days=60),
                'completion_percentage': 75.0,
                'status': 'ON_TRACK',
                'source': 'JIRA'
            }
        ]
        
        result = analyze_milestone_risks('project-123', 'tenant-456')
        
        assert result == []
    
    @patch('risk_detection.milestone_analysis.query_active_milestones')
    def test_analyze_milestone_risks_no_milestones(self, mock_query):
        """Test milestone risk analysis with no milestones."""
        mock_query.return_value = []
        
        result = analyze_milestone_risks('project-123', 'tenant-456')
        
        assert result == []


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
