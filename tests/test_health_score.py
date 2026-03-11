"""Tests for health score calculation service."""

import sys
import os
import json
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal
from datetime import datetime

import pytest
from hypothesis import given, strategies as st, assume, settings

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from health_score.score_calculator import (
    calculate_velocity_score,
    calculate_backlog_score,
    calculate_milestone_score,
    calculate_risk_score,
    calculate_health_score,
    get_tenant_weights,
    DEFAULT_WEIGHTS
)
from health_score.score_storage import (
    store_health_score_history,
    get_health_score_history,
    get_latest_health_score
)
from health_score.handler import (
    calculate_health_score_handler,
    get_health_score_handler,
    get_health_score_history_handler
)


# ============================================================================
# Property-Based Tests
# ============================================================================

class TestHealthScoreComposition:
    """
    Property 54: Health Score Composition
    
    **Validates: Requirements 18.1**
    
    For any project, the system SHALL calculate health score as a weighted 
    composite of velocity trend, backlog health, milestone progress, and risk count.
    """
    
    @settings(max_examples=20, deadline=None)
    @given(
        velocity_score=st.floats(min_value=0, max_value=100),
        backlog_score=st.floats(min_value=0, max_value=100),
        milestone_score=st.floats(min_value=0, max_value=100),
        risk_score=st.floats(min_value=0, max_value=100)
    )
    def test_health_score_is_weighted_composite(
        self,
        velocity_score,
        backlog_score,
        milestone_score,
        risk_score
    ):
        """
        Property: Health score MUST be calculated as weighted composite of all components.
        
        For any valid component scores, the health score should equal:
        (velocity × 0.30) + (backlog × 0.25) + (milestones × 0.30) + (risks × 0.15)
        """
        weights = DEFAULT_WEIGHTS
        
        expected_score = (
            velocity_score * weights['velocity'] +
            backlog_score * weights['backlog'] +
            milestone_score * weights['milestones'] +
            risk_score * weights['risks']
        )
        
        # Mock the component calculation functions
        with patch('health_score.score_calculator.calculate_velocity_score', return_value=velocity_score), \
             patch('health_score.score_calculator.calculate_backlog_score', return_value=backlog_score), \
             patch('health_score.score_calculator.calculate_milestone_score', return_value=milestone_score), \
             patch('health_score.score_calculator.calculate_risk_score', return_value=risk_score):
            
            result = calculate_health_score('project-1', 'tenant-1')
            
            # Verify the weighted composite calculation
            assert abs(result['health_score'] - round(expected_score)) <= 1, \
                f"Health score {result['health_score']} should equal weighted composite {round(expected_score)}"
            
            # Verify all components are included
            assert 'velocity' in result['component_scores']
            assert 'backlog' in result['component_scores']
            assert 'milestones' in result['component_scores']
            assert 'risks' in result['component_scores']
    
    @settings(max_examples=20, deadline=None)
    @given(
        velocity_weight=st.floats(min_value=0, max_value=1),
        backlog_weight=st.floats(min_value=0, max_value=1),
        milestone_weight=st.floats(min_value=0, max_value=1),
        risk_weight=st.floats(min_value=0, max_value=1)
    )
    def test_custom_weights_applied_correctly(
        self,
        velocity_weight,
        backlog_weight,
        milestone_weight,
        risk_weight
    ):
        """
        Property: Custom weights MUST be applied when provided.
        
        For any valid custom weights, the calculation should use those weights
        instead of defaults.
        """
        # Normalize weights to sum to 1.0
        total = velocity_weight + backlog_weight + milestone_weight + risk_weight
        assume(total > 0)  # Avoid division by zero
        
        custom_weights = {
            'velocity': velocity_weight / total,
            'backlog': backlog_weight / total,
            'milestones': milestone_weight / total,
            'risks': risk_weight / total
        }
        
        # Mock component scores
        component_scores = {
            'velocity': 80.0,
            'backlog': 70.0,
            'milestones': 75.0,
            'risks': 85.0
        }
        
        with patch('health_score.score_calculator.calculate_velocity_score', return_value=component_scores['velocity']), \
             patch('health_score.score_calculator.calculate_backlog_score', return_value=component_scores['backlog']), \
             patch('health_score.score_calculator.calculate_milestone_score', return_value=component_scores['milestones']), \
             patch('health_score.score_calculator.calculate_risk_score', return_value=component_scores['risks']):
            
            result = calculate_health_score('project-1', 'tenant-1', custom_weights=custom_weights)
            
            # Verify custom weights were used
            assert result['weights'] == custom_weights
            
            # Verify calculation uses custom weights
            expected = (
                component_scores['velocity'] * custom_weights['velocity'] +
                component_scores['backlog'] * custom_weights['backlog'] +
                component_scores['milestones'] * custom_weights['milestones'] +
                component_scores['risks'] * custom_weights['risks']
            )
            
            assert abs(result['health_score'] - round(expected)) <= 1


class TestHealthScoreRange:
    """
    Property 55: Health Score Range
    
    **Validates: Requirements 18.2**
    
    For any calculated health score, the system SHALL normalize it to the range 0-100.
    """
    
    @settings(max_examples=20, deadline=None)
    @given(
        velocity_score=st.floats(min_value=-100, max_value=200),
        backlog_score=st.floats(min_value=-100, max_value=200),
        milestone_score=st.floats(min_value=-100, max_value=200),
        risk_score=st.floats(min_value=-100, max_value=200)
    )
    def test_health_score_always_in_valid_range(
        self,
        velocity_score,
        backlog_score,
        milestone_score,
        risk_score
    ):
        """
        Property: Health score MUST always be in range [0, 100].
        
        Even if component scores are outside normal range, the final health score
        must be normalized to 0-100.
        """
        with patch('health_score.score_calculator.calculate_velocity_score', return_value=velocity_score), \
             patch('health_score.score_calculator.calculate_backlog_score', return_value=backlog_score), \
             patch('health_score.score_calculator.calculate_milestone_score', return_value=milestone_score), \
             patch('health_score.score_calculator.calculate_risk_score', return_value=risk_score):
            
            result = calculate_health_score('project-1', 'tenant-1')
            
            # Verify health score is in valid range
            assert 0 <= result['health_score'] <= 100, \
                f"Health score {result['health_score']} must be in range [0, 100]"
            
            # Verify it's an integer
            assert isinstance(result['health_score'], int), \
                "Health score must be an integer"
    
    @settings(max_examples=20, deadline=None)
    @given(
        component_score=st.floats(min_value=0, max_value=100)
    )
    def test_component_scores_in_valid_range(self, component_score):
        """
        Property: All component scores MUST be in range [0, 100].
        """
        with patch('health_score.score_calculator.calculate_velocity_score', return_value=component_score), \
             patch('health_score.score_calculator.calculate_backlog_score', return_value=component_score), \
             patch('health_score.score_calculator.calculate_milestone_score', return_value=component_score), \
             patch('health_score.score_calculator.calculate_risk_score', return_value=component_score):
            
            result = calculate_health_score('project-1', 'tenant-1')
            
            # Verify all component scores are in valid range
            for component, score in result['component_scores'].items():
                assert 0 <= score <= 100, \
                    f"Component score {component}={score} must be in range [0, 100]"


class TestHealthScoreUpdateTriggering:
    """
    Property 56: Health Score Update Triggering
    
    **Validates: Requirements 18.3**
    
    For any project data refresh, the system SHALL recalculate the health score.
    """
    
    @settings(max_examples=20, deadline=None)
    @given(
        project_id=st.uuids().map(str),
        tenant_id=st.uuids().map(str)
    )
    def test_data_refresh_triggers_recalculation(self, project_id, tenant_id):
        """
        Property: Data refresh events MUST trigger health score recalculation.
        
        For any valid project and tenant, when a data refresh event occurs,
        the health score should be recalculated.
        """
        from health_score.event_trigger import data_refresh_trigger_handler
        
        event = {
            'detail-type': 'DataIngestionCompleted',
            'source': 'ai-sw-pm.data-ingestion',
            'detail': {
                'project_id': project_id,
                'tenant_id': tenant_id,
                'ingestion_type': 'JIRA',
                'completed_at': datetime.utcnow().isoformat()
            }
        }
        
        with patch('health_score.event_trigger.calculate_health_score') as mock_calc, \
             patch('health_score.event_trigger.store_health_score_history') as mock_store, \
             patch('health_score.event_trigger.publish_health_score_event') as mock_publish:
            
            mock_calc.return_value = {
                'health_score': 75,
                'component_scores': {'velocity': 80, 'backlog': 70, 'milestones': 75, 'risks': 85},
                'weights': DEFAULT_WEIGHTS,
                'calculated_at': datetime.utcnow().isoformat()
            }
            mock_store.return_value = 'history-id-123'
            
            result = data_refresh_trigger_handler(event, None)
            
            # Verify calculation was triggered
            mock_calc.assert_called_once_with(
                project_id=project_id,
                tenant_id=tenant_id
            )
            
            # Verify result was stored
            mock_store.assert_called_once()
            
            # Verify event was published
            mock_publish.assert_called_once()
            
            # Verify success response
            assert result['statusCode'] == 200


class TestHealthScoreHistoryPersistence:
    """
    Property 57: Health Score History Persistence
    
    **Validates: Requirements 18.4**
    
    For any calculated health score, the system SHALL store it with timestamp 
    for trend analysis.
    """
    
    @settings(max_examples=20, deadline=None)
    @given(
        project_id=st.uuids().map(str),
        tenant_id=st.uuids().map(str),
        health_score=st.integers(min_value=0, max_value=100)
    )
    def test_health_score_stored_with_timestamp(self, project_id, tenant_id, health_score):
        """
        Property: Every health score calculation MUST be stored with timestamp.
        
        For any health score calculation, the result must be persisted with
        a timestamp for historical trend analysis.
        """
        health_score_data = {
            'health_score': health_score,
            'component_scores': {
                'velocity': 80.0,
                'backlog': 70.0,
                'milestones': 75.0,
                'risks': 85.0
            },
            'weights': DEFAULT_WEIGHTS,
            'calculated_at': datetime.utcnow().isoformat()
        }
        
        with patch('health_score.score_storage.execute_query') as mock_query:
            mock_query.return_value = [{'id': 'history-id-123'}]
            
            history_id = store_health_score_history(
                project_id=project_id,
                tenant_id=tenant_id,
                health_score_data=health_score_data
            )
            
            # Verify storage was called
            assert mock_query.call_count >= 1
            
            # Verify the INSERT query includes timestamp
            insert_call = None
            for call in mock_query.call_args_list:
                query = call[0][0] if call[0] else ""
                if 'INSERT INTO health_score_history' in query:
                    insert_call = call
                    break
            
            assert insert_call is not None, "INSERT query should be executed"
            
            # Verify calculated_at is included in parameters
            params = insert_call[0][1] if len(insert_call[0]) > 1 else ()
            assert health_score_data['calculated_at'] in params, \
                "Timestamp must be included in stored data"
            
            # Verify history_id is returned
            assert history_id == 'history-id-123'
    
    @settings(max_examples=20, deadline=None)
    @given(
        project_id=st.uuids().map(str),
        tenant_id=st.uuids().map(str),
        history_count=st.integers(min_value=1, max_value=100)
    )
    def test_health_score_history_retrievable(self, project_id, tenant_id, history_count):
        """
        Property: Stored health score history MUST be retrievable for trend analysis.
        
        For any project with health score history, the system must be able to
        retrieve that history ordered by timestamp.
        """
        # Mock history data
        mock_history = [
            {
                'id': f'history-{i}',
                'health_score': 70 + i,
                'velocity_score': Decimal('80.0'),
                'backlog_score': Decimal('70.0'),
                'milestone_score': Decimal('75.0'),
                'risk_score': Decimal('85.0'),
                'weights': json.dumps(DEFAULT_WEIGHTS),
                'calculated_at': datetime.utcnow().isoformat(),
                'created_at': datetime.utcnow().isoformat()
            }
            for i in range(min(history_count, 30))  # Limit to 30 as per default
        ]
        
        with patch('health_score.score_storage.execute_query') as mock_query:
            mock_query.return_value = mock_history
            
            history = get_health_score_history(
                project_id=project_id,
                tenant_id=tenant_id,
                limit=30
            )
            
            # Verify query was executed
            mock_query.assert_called_once()
            
            # Verify history is returned
            assert len(history) == len(mock_history)
            
            # Verify each entry has required fields
            for entry in history:
                assert 'id' in entry
                assert 'health_score' in entry
                assert 'calculated_at' in entry
                assert 'velocity_score' in entry
                assert 'backlog_score' in entry
                assert 'milestone_score' in entry
                assert 'risk_score' in entry


# ============================================================================
# Unit Tests
# ============================================================================

class TestVelocityScoreCalculation:
    """Unit tests for velocity score calculation."""
    
    def test_velocity_score_with_insufficient_data(self):
        """Test velocity score returns neutral (100) with insufficient data."""
        with patch('health_score.score_calculator.execute_query') as mock_query:
            mock_query.return_value = []
            
            score = calculate_velocity_score('project-1')
            
            assert score == 100.0
    
    def test_velocity_score_with_good_velocity(self):
        """Test velocity score with current velocity >= average."""
        with patch('health_score.score_calculator.execute_query') as mock_query:
            mock_query.return_value = [
                {'velocity': Decimal('40')},
                {'velocity': Decimal('38')},
                {'velocity': Decimal('42')},
                {'velocity': Decimal('40')}
            ]
            
            score = calculate_velocity_score('project-1')
            
            # Current (40) >= average (40), should return 100
            assert score == 100.0
    
    def test_velocity_score_with_declining_velocity(self):
        """Test velocity score with declining velocity."""
        with patch('health_score.score_calculator.execute_query') as mock_query:
            mock_query.return_value = [
                {'velocity': Decimal('25')},  # Current (most recent in DESC order)
                {'velocity': Decimal('30')},
                {'velocity': Decimal('35')},
                {'velocity': Decimal('40')}
            ]
            
            score = calculate_velocity_score('project-1')
            
            # Current (25) vs average (32.5) = 77% ratio, should return 70
            assert score == 70.0


class TestBacklogScoreCalculation:
    """Unit tests for backlog score calculation."""
    
    def test_backlog_score_with_no_items(self):
        """Test backlog score returns neutral (100) with no items."""
        with patch('health_score.score_calculator.execute_query') as mock_query:
            mock_query.return_value = [{'total_items': 0, 'open_items': 0}]
            
            score = calculate_backlog_score('project-1')
            
            assert score == 100.0
    
    def test_backlog_score_with_low_open_ratio(self):
        """Test backlog score with low open ratio."""
        with patch('health_score.score_calculator.execute_query') as mock_query:
            mock_query.return_value = [{'total_items': 100, 'open_items': 20}]
            
            score = calculate_backlog_score('project-1')
            
            # 20% open, should return 100
            assert score == 100.0
    
    def test_backlog_score_with_high_open_ratio(self):
        """Test backlog score with high open ratio."""
        with patch('health_score.score_calculator.execute_query') as mock_query:
            mock_query.return_value = [{'total_items': 100, 'open_items': 90}]
            
            score = calculate_backlog_score('project-1')
            
            # 90% open, should return 30
            assert score == 30.0


class TestMilestoneScoreCalculation:
    """Unit tests for milestone score calculation."""
    
    def test_milestone_score_with_no_milestones(self):
        """Test milestone score returns neutral (100) with no milestones."""
        with patch('health_score.score_calculator.execute_query') as mock_query:
            mock_query.return_value = []
            
            score = calculate_milestone_score('project-1')
            
            assert score == 100.0
    
    def test_milestone_score_all_on_track(self):
        """Test milestone score with all milestones on track."""
        with patch('health_score.score_calculator.execute_query') as mock_query:
            mock_query.return_value = [
                {'status': 'ON_TRACK', 'count': 5},
                {'status': 'COMPLETED', 'count': 3}
            ]
            
            score = calculate_milestone_score('project-1')
            
            # All on track or completed, should return 100
            assert score == 100.0
    
    def test_milestone_score_mixed_status(self):
        """Test milestone score with mixed milestone status."""
        with patch('health_score.score_calculator.execute_query') as mock_query:
            mock_query.return_value = [
                {'status': 'ON_TRACK', 'count': 4},
                {'status': 'AT_RISK', 'count': 2},
                {'status': 'DELAYED', 'count': 2}
            ]
            
            score = calculate_milestone_score('project-1')
            
            # (4*100 + 2*50 + 2*0) / 8 = 62.5
            assert score == 62.5


class TestRiskScoreCalculation:
    """Unit tests for risk score calculation."""
    
    def test_risk_score_with_no_risks(self):
        """Test risk score returns 100 with no risks."""
        score = calculate_risk_score('project-1', 'tenant-1')
        
        # No risks, should return 100
        assert score == 100.0


class TestHealthScoreHandler:
    """Unit tests for health score Lambda handlers."""
    
    def test_calculate_health_score_handler_success(self):
        """Test successful health score calculation via handler."""
        event = {
            'project_id': 'project-123',
            'tenant_id': 'tenant-456'
        }
        
        mock_health_score_data = {
            'health_score': 75,
            'component_scores': {
                'velocity': 80.0,
                'backlog': 70.0,
                'milestones': 75.0,
                'risks': 85.0
            },
            'weights': DEFAULT_WEIGHTS,
            'calculated_at': datetime.utcnow().isoformat()
        }
        
        with patch('health_score.handler.calculate_health_score') as mock_calc, \
             patch('health_score.handler.store_health_score_history') as mock_store, \
             patch('health_score.handler.publish_health_score_event') as mock_publish:
            
            mock_calc.return_value = mock_health_score_data
            mock_store.return_value = 'history-id-123'
            
            response = calculate_health_score_handler(event, None)
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['health_score'] == 75
            assert body['history_id'] == 'history-id-123'
    
    def test_calculate_health_score_handler_missing_params(self):
        """Test handler with missing required parameters."""
        from shared.errors import ValidationError
        
        event = {
            'project_id': 'project-123'
            # Missing tenant_id
        }
        
        with pytest.raises(ValidationError):
            calculate_health_score_handler(event, None)
    
    def test_get_health_score_handler_success(self):
        """Test retrieving health score via handler."""
        event = {
            'tenant_id': 'tenant-456',
            'pathParameters': {
                'projectId': 'project-123'
            }
        }
        
        mock_health_score = {
            'id': 'history-id-123',
            'health_score': 75,
            'velocity_score': 80.0,
            'backlog_score': 70.0,
            'milestone_score': 75.0,
            'risk_score': 85.0,
            'calculated_at': datetime.utcnow().isoformat()
        }
        
        with patch('health_score.handler.get_latest_health_score') as mock_get:
            mock_get.return_value = mock_health_score
            
            response = get_health_score_handler(event, None)
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['health_score'] == 75
    
    def test_get_health_score_handler_not_found(self):
        """Test handler when health score not found."""
        event = {
            'tenant_id': 'tenant-456',
            'pathParameters': {
                'projectId': 'project-123'
            }
        }
        
        with patch('health_score.handler.get_latest_health_score') as mock_get:
            mock_get.return_value = None
            
            response = get_health_score_handler(event, None)
            
            assert response['statusCode'] == 404
    
    def test_get_health_score_history_handler_success(self):
        """Test retrieving health score history via handler."""
        event = {
            'tenant_id': 'tenant-456',
            'pathParameters': {
                'projectId': 'project-123'
            },
            'queryStringParameters': {
                'limit': '10'
            }
        }
        
        mock_history = [
            {
                'id': f'history-{i}',
                'health_score': 70 + i,
                'calculated_at': datetime.utcnow().isoformat()
            }
            for i in range(10)
        ]
        
        with patch('health_score.handler.get_health_score_history') as mock_get:
            mock_get.return_value = mock_history
            
            response = get_health_score_history_handler(event, None)
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['count'] == 10
            assert len(body['history']) == 10
