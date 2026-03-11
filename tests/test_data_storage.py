"""Tests for data validation and storage functionality.

Tests for Tasks 5.3 and 5.4:
- Data validation against expected schema
- Storage in RDS PostgreSQL
- Ingestion metadata with timestamp and source
- Error handling and administrator alerting
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Mock psycopg2 before importing modules that use it
import sys
sys.modules['psycopg2'] = MagicMock()
sys.modules['psycopg2.pool'] = MagicMock()
sys.modules['psycopg2.sql'] = MagicMock()
sys.modules['psycopg2.extras'] = MagicMock()

from src.shared.schema_validator import (
    validate_sprint_schema,
    validate_backlog_schema,
    validate_milestone_schema,
    validate_resource_schema,
    validate_dependency_schema,
    validate_project_data
)
from src.shared.errors import ValidationError


class TestSchemaValidation:
    """Test schema validation for external API data."""
    
    def test_valid_sprint_schema(self):
        """Test validation of valid sprint data."""
        sprint = {
            'sprintName': 'Sprint 1',
            'startDate': '2024-01-01T00:00:00Z',
            'endDate': '2024-01-14T00:00:00Z',
            'velocity': 25.5,
            'completedPoints': 25.5,
            'plannedPoints': 30.0,
            'completionRate': 85.0
        }
        
        result = validate_sprint_schema(sprint)
        assert result == sprint
    
    def test_sprint_missing_required_field(self):
        """Test validation fails when required field is missing."""
        sprint = {
            'startDate': '2024-01-01T00:00:00Z',
            'endDate': '2024-01-14T00:00:00Z'
            # Missing sprintName
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_sprint_schema(sprint)
        
        assert 'sprintName' in str(exc_info.value)
    
    def test_sprint_invalid_date_format(self):
        """Test validation fails with invalid date format."""
        sprint = {
            'sprintName': 'Sprint 1',
            'startDate': 'invalid-date',
            'endDate': '2024-01-14T00:00:00Z'
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_sprint_schema(sprint)
        
        assert 'date' in str(exc_info.value).lower()
    
    def test_sprint_invalid_numeric_value(self):
        """Test validation fails with invalid numeric value."""
        sprint = {
            'sprintName': 'Sprint 1',
            'startDate': '2024-01-01T00:00:00Z',
            'endDate': '2024-01-14T00:00:00Z',
            'velocity': 'not-a-number'
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_sprint_schema(sprint)
        
        assert 'velocity' in str(exc_info.value)
    
    def test_valid_backlog_schema(self):
        """Test validation of valid backlog data."""
        backlog = {
            'totalIssues': 50,
            'issuesByType': {'bug': 10, 'feature': 30, 'technical_debt': 10},
            'issuesByPriority': {'high': 15, 'medium': 25, 'low': 10},
            'averageAge': 12.5,
            'growthRate': 0.15
        }
        
        result = validate_backlog_schema(backlog)
        assert result == backlog
    
    def test_backlog_missing_required_field(self):
        """Test validation fails when required field is missing."""
        backlog = {
            'totalIssues': 50,
            'issuesByType': {}
            # Missing issuesByPriority
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_backlog_schema(backlog)
        
        assert 'issuesByPriority' in str(exc_info.value)
    
    def test_valid_milestone_schema(self):
        """Test validation of valid milestone data."""
        milestone = {
            'name': 'Release 1.0',
            'dueDate': '2024-06-30',
            'completionPercentage': 75.0,
            'status': 'ON_TRACK',
            'dependencies': []
        }
        
        result = validate_milestone_schema(milestone)
        assert result == milestone
    
    def test_milestone_invalid_completion_percentage(self):
        """Test validation fails with invalid completion percentage."""
        milestone = {
            'name': 'Release 1.0',
            'dueDate': '2024-06-30',
            'completionPercentage': 150.0  # Invalid: > 100
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_milestone_schema(milestone)
        
        assert 'completionPercentage' in str(exc_info.value)
    
    def test_milestone_invalid_status(self):
        """Test validation fails with invalid status."""
        milestone = {
            'name': 'Release 1.0',
            'status': 'INVALID_STATUS'
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_milestone_schema(milestone)
        
        assert 'status' in str(exc_info.value)
    
    def test_valid_resource_schema(self):
        """Test validation of valid resource data."""
        resource = {
            'userId': 'user-123',
            'userName': 'John Doe',
            'allocatedHours': 35.0,
            'capacity': 40.0,
            'utilizationRate': 87.5
        }
        
        result = validate_resource_schema(resource)
        assert result == resource
    
    def test_resource_negative_hours(self):
        """Test validation fails with negative hours."""
        resource = {
            'userName': 'John Doe',
            'allocatedHours': -10.0  # Invalid: negative
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_resource_schema(resource)
        
        assert 'allocatedHours' in str(exc_info.value)
    
    def test_valid_dependency_schema(self):
        """Test validation of valid dependency data."""
        dependency = {
            'dependencyId': 'dep-123',
            'sourceTaskId': 'TASK-1',
            'targetTaskId': 'TASK-2',
            'type': 'BLOCKS',
            'status': 'ACTIVE'
        }
        
        result = validate_dependency_schema(dependency)
        assert result == dependency
    
    def test_dependency_invalid_type(self):
        """Test validation fails with invalid dependency type."""
        dependency = {
            'sourceTaskId': 'TASK-1',
            'targetTaskId': 'TASK-2',
            'type': 'INVALID_TYPE'
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_dependency_schema(dependency)
        
        assert 'type' in str(exc_info.value)
    
    def test_valid_project_data(self):
        """Test validation of complete project data."""
        project_data = {
            'projectId': 'proj-123',
            'projectName': 'Test Project',
            'source': 'JIRA',
            'lastSyncAt': '2024-01-15T10:00:00Z',
            'metrics': {
                'sprints': [
                    {
                        'sprintName': 'Sprint 1',
                        'startDate': '2024-01-01T00:00:00Z',
                        'endDate': '2024-01-14T00:00:00Z',
                        'velocity': 25.0
                    }
                ],
                'backlog': {
                    'totalIssues': 50,
                    'issuesByType': {'bug': 10},
                    'issuesByPriority': {'high': 15}
                },
                'milestones': [
                    {
                        'name': 'Release 1.0',
                        'dueDate': '2024-06-30'
                    }
                ],
                'resources': [
                    {
                        'userName': 'John Doe',
                        'allocatedHours': 35.0
                    }
                ],
                'dependencies': [
                    {
                        'sourceTaskId': 'TASK-1',
                        'targetTaskId': 'TASK-2'
                    }
                ]
            }
        }
        
        result = validate_project_data(project_data)
        assert result['projectName'] == 'Test Project'
        assert result['source'] == 'JIRA'
    
    def test_project_data_missing_required_field(self):
        """Test validation fails when project missing required field."""
        project_data = {
            'projectName': 'Test Project',
            # Missing source and metrics
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_project_data(project_data)
        
        assert 'required field' in str(exc_info.value).lower()
    
    def test_project_data_invalid_source(self):
        """Test validation fails with invalid data source."""
        project_data = {
            'projectName': 'Test Project',
            'source': 'INVALID_SOURCE',
            'metrics': {}
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_project_data(project_data)
        
        assert 'source' in str(exc_info.value).lower()
    
    def test_project_data_invalid_sprint_in_list(self):
        """Test validation fails when sprint in list is invalid."""
        project_data = {
            'projectName': 'Test Project',
            'source': 'JIRA',
            'metrics': {
                'sprints': [
                    {
                        'sprintName': 'Sprint 1',
                        'startDate': '2024-01-01T00:00:00Z',
                        'endDate': '2024-01-14T00:00:00Z'
                    },
                    {
                        # Missing required fields
                        'velocity': 25.0
                    }
                ],
                'backlog': {
                    'totalIssues': 0,
                    'issuesByType': {},
                    'issuesByPriority': {}
                },
                'milestones': [],
                'resources': [],
                'dependencies': []
            }
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_project_data(project_data)
        
        assert 'sprint' in str(exc_info.value).lower()


class TestDataStorage:
    """Test data storage functionality."""
    
    @patch('src.jira_integration.data_storage.insert_project')
    @patch('src.jira_integration.data_storage.insert_sprints')
    @patch('src.jira_integration.data_storage.insert_milestones')
    @patch('src.jira_integration.data_storage.insert_resources')
    @patch('src.jira_integration.data_storage.insert_dependencies')
    def test_store_project_data_success(
        self,
        mock_insert_deps,
        mock_insert_resources,
        mock_insert_milestones,
        mock_insert_sprints,
        mock_insert_project
    ):
        """Test successful project data storage."""
        from src.jira_integration.data_storage import store_project_data
        
        # Setup mocks
        mock_insert_project.return_value = 'proj-uuid-123'
        mock_insert_sprints.return_value = 2
        mock_insert_milestones.return_value = 3
        mock_insert_resources.return_value = 5
        mock_insert_deps.return_value = 4
        
        project_data = {
            'projectId': 'ext-proj-123',
            'projectName': 'Test Project',
            'source': 'JIRA',
            'metrics': {
                'sprints': [{'sprintName': 'S1', 'startDate': '2024-01-01', 'endDate': '2024-01-14'}] * 2,
                'backlog': {'totalIssues': 10, 'issuesByType': {}, 'issuesByPriority': {}},
                'milestones': [{'name': 'M1'}] * 3,
                'resources': [{'userName': 'User1'}] * 5,
                'dependencies': [{'sourceTaskId': 'T1', 'targetTaskId': 'T2'}] * 4
            }
        }
        
        result = store_project_data('tenant-123', project_data, 'JIRA')
        
        # Verify result
        assert result['success'] is True
        assert result['project_id'] == 'proj-uuid-123'
        assert result['project_name'] == 'Test Project'
        assert result['storage_counts']['sprints'] == 2
        assert result['storage_counts']['milestones'] == 3
        assert result['storage_counts']['resources'] == 5
        assert result['storage_counts']['dependencies'] == 4
        
        # Verify mocks were called
        mock_insert_project.assert_called_once()
        mock_insert_sprints.assert_called_once()
        mock_insert_milestones.assert_called_once()
        mock_insert_resources.assert_called_once()
        mock_insert_deps.assert_called_once()
    
    @patch('src.jira_integration.data_storage.insert_project')
    def test_store_project_data_validation_failure(self, mock_insert_project):
        """Test storage fails with validation error."""
        from src.jira_integration.data_storage import store_project_data
        from src.shared.errors import ValidationError
        
        # Invalid project data (missing required fields)
        project_data = {
            'projectName': 'Test Project'
            # Missing source and metrics
        }
        
        # Should raise ValidationError
        error_raised = False
        try:
            store_project_data('tenant-123', project_data, 'JIRA')
        except ValidationError as e:
            error_raised = True
            assert 'source' in str(e).lower() or 'required' in str(e).lower()
        
        assert error_raised, "ValidationError should have been raised"
        
        # Verify insert was not called
        mock_insert_project.assert_not_called()
    
    @patch('src.jira_integration.data_storage.insert_project')
    def test_store_multiple_projects_partial_failure(self, mock_insert_project):
        """Test storing multiple projects with some failures."""
        from src.jira_integration.data_storage import store_multiple_projects
        
        mock_insert_project.return_value = 'proj-uuid-123'
        
        projects = [
            {
                'projectName': 'Valid Project',
                'source': 'JIRA',
                'metrics': {
                    'sprints': [],
                    'backlog': {'totalIssues': 0, 'issuesByType': {}, 'issuesByPriority': {}},
                    'milestones': [],
                    'resources': [],
                    'dependencies': []
                }
            },
            {
                'projectName': 'Invalid Project'
                # Missing required fields
            }
        ]
        
        result = store_multiple_projects('tenant-123', projects, 'JIRA')
        
        assert result['total'] == 2
        assert result['successful'] == 1
        assert result['failed'] == 1
        assert len(result['errors']) == 1
        assert 'Invalid Project' in result['errors'][0]['project_name']


class TestErrorHandling:
    """Test error handling and administrator alerting."""
    
    @patch('src.jira_integration.data_fetcher.get_sns')
    @patch('src.jira_integration.data_fetcher.SNS_ADMIN_ALERT_TOPIC', 'arn:aws:sns:us-east-1:123456789012:admin-alerts')
    def test_send_admin_alert_success(self, mock_get_sns):
        """Test sending administrator alert via SNS."""
        from src.jira_integration.data_fetcher import send_admin_alert
        
        mock_sns = Mock()
        mock_get_sns.return_value = mock_sns
        
        send_admin_alert(
            subject='Test Alert',
            message='Test message',
            error_details={'error': 'test error'}
        )
        
        mock_sns.publish.assert_called_once()
        call_args = mock_sns.publish.call_args
        assert call_args[1]['Subject'] == 'Test Alert'
        assert 'Test message' in call_args[1]['Message']
        assert 'test error' in call_args[1]['Message']
    
    @patch('src.jira_integration.data_fetcher.get_sns')
    @patch('src.jira_integration.data_fetcher.SNS_ADMIN_ALERT_TOPIC', None)
    def test_send_admin_alert_no_topic_configured(self, mock_get_sns):
        """Test alert skipped when SNS topic not configured."""
        from src.jira_integration.data_fetcher import send_admin_alert
        
        # Should not raise error, just log warning
        send_admin_alert(
            subject='Test Alert',
            message='Test message'
        )
        
        # SNS should not be called
        mock_get_sns.assert_not_called()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
