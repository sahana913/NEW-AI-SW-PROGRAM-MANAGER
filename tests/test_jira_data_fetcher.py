"""Unit tests for Jira data fetching Lambda handler."""

import json
import os
import pytest
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime
from botocore.exceptions import ClientError

# Set up environment variables before importing handler
os.environ['INTEGRATIONS_TABLE_NAME'] = 'test-integrations'
os.environ['SECRETS_MANAGER_PREFIX'] = 'test-prefix'
os.environ['USER_POOL_ID'] = 'test-pool-id'

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from jira_integration.data_fetcher import (
    fetch_jira_data,
    JiraAPIClient,
    transform_sprint_data,
    transform_backlog_data,
    transform_milestone_data,
    transform_resource_data,
    transform_dependency_data
)
from shared.errors import ValidationError, DataError


@pytest.fixture
def mock_dynamodb():
    """Mock DynamoDB resource."""
    with patch('jira_integration.data_fetcher.get_dynamodb') as mock:
        table = MagicMock()
        mock.return_value.Table.return_value = table
        yield table


@pytest.fixture
def mock_secrets_manager():
    """Mock Secrets Manager client."""
    with patch('jira_integration.data_fetcher.get_secrets_manager') as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


@pytest.fixture
def mock_jira_client():
    """Mock Jira API client."""
    with patch('jira_integration.data_fetcher.JiraAPIClient') as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


@pytest.fixture
def valid_fetch_event():
    """Valid event for fetching Jira data."""
    return {
        'body': json.dumps({
            'integrationId': 'integration-123'
        }),
        'requestContext': {
            'authorizer': {
                'role': 'ADMIN',
                'userId': 'user-123',
                'tenantId': 'tenant-123'
            }
        },
        'httpMethod': 'POST',
        'path': '/integrations/jira/fetch'
    }


@pytest.fixture
def integration_config():
    """Mock integration configuration."""
    return {
        'PK': 'TENANT#tenant-123',
        'SK': 'INTEGRATION#integration-123',
        'integrationId': 'integration-123',
        'tenantId': 'tenant-123',
        'integrationType': 'JIRA',
        'configuration': {
            'jiraUrl': 'https://example.atlassian.net',
            'authType': 'API_TOKEN',
            'projectKeys': ['PROJ1', 'PROJ2'],
            'syncSchedule': 'cron(0 0 * * ? *)',
            'secretName': 'test-prefix/jira/tenant-123/integration-123'
        },
        'status': 'ACTIVE'
    }


@pytest.fixture
def secret_data():
    """Mock secret data."""
    return {
        'jiraUrl': 'https://example.atlassian.net',
        'authType': 'API_TOKEN',
        'credentials': {
            'email': 'test@example.com',
            'apiToken': 'test-token-123'
        }
    }


class TestJiraAPIClient:
    """Test suite for JiraAPIClient class."""
    
    @patch('jira_integration.data_fetcher.requests.Session')
    def test_init_with_api_token(self, mock_session_class):
        """Test client initialization with API token."""
        # Arrange
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        
        credentials = {
            'email': 'test@example.com',
            'apiToken': 'test-token'
        }
        
        # Act
        client = JiraAPIClient(
            'https://example.atlassian.net',
            'API_TOKEN',
            credentials
        )
        
        # Assert
        assert client.jira_url == 'https://example.atlassian.net'
        assert client.auth_type == 'API_TOKEN'
        assert mock_session.headers.update.called
    
    @patch('jira_integration.data_fetcher.requests.Session')
    def test_make_request_success(self, mock_session_class):
        """Test successful API request."""
        # Arrange
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': 'test'}
        mock_session.request.return_value = mock_response
        
        client = JiraAPIClient(
            'https://example.atlassian.net',
            'API_TOKEN',
            {'apiToken': 'test'}
        )
        
        # Act
        result = client._make_request('GET', '/test')
        
        # Assert
        assert result == {'data': 'test'}
        mock_session.request.assert_called_once()
    
    @patch('jira_integration.data_fetcher.requests.Session')
    @patch('time.sleep')
    def test_make_request_rate_limit_retry(self, mock_sleep, mock_session_class):
        """Test retry logic for rate limiting."""
        # Arrange
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        
        # First call returns 429, second call succeeds
        mock_response_429 = MagicMock()
        mock_response_429.status_code = 429
        
        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {'data': 'test'}
        
        mock_session.request.side_effect = [mock_response_429, mock_response_200]
        
        client = JiraAPIClient(
            'https://example.atlassian.net',
            'API_TOKEN',
            {'apiToken': 'test'}
        )
        
        # Act
        result = client._make_request('GET', '/test')
        
        # Assert
        assert result == {'data': 'test'}
        assert mock_session.request.call_count == 2
        mock_sleep.assert_called_once_with(1)  # First retry delay
    
    @patch('jira_integration.data_fetcher.requests.Session')
    @patch('time.sleep')
    def test_make_request_max_retries_exceeded(self, mock_sleep, mock_session_class):
        """Test failure after maximum retries."""
        # Arrange
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_session.request.return_value = mock_response
        
        client = JiraAPIClient(
            'https://example.atlassian.net',
            'API_TOKEN',
            {'apiToken': 'test'}
        )
        
        # Act & Assert
        with pytest.raises(DataError) as exc_info:
            client._make_request('GET', '/test')
        
        assert 'rate limit exceeded' in str(exc_info.value).lower()
        assert mock_session.request.call_count == 5  # Max retries


class TestTransformFunctions:
    """Test suite for data transformation functions."""
    
    def test_transform_sprint_data(self):
        """Test sprint data transformation."""
        # Arrange
        sprint_data = {
            'id': 123,
            'name': 'Sprint 1',
            'startDate': '2024-01-01T00:00:00.000Z',
            'endDate': '2024-01-14T00:00:00.000Z'
        }
        
        sprint_report = {
            'contents': {
                'completedIssues': [
                    {
                        'estimateStatistic': {
                            'statFieldValue': {'value': 5}
                        }
                    },
                    {
                        'estimateStatistic': {
                            'statFieldValue': {'value': 3}
                        }
                    }
                ],
                'incompletedIssues': [
                    {
                        'estimateStatistic': {
                            'statFieldValue': {'value': 2}
                        }
                    }
                ]
            }
        }
        
        # Act
        result = transform_sprint_data(sprint_data, sprint_report)
        
        # Assert
        assert result['sprintId'] == '123'
        assert result['sprintName'] == 'Sprint 1'
        assert result['velocity'] == 8
        assert result['completedPoints'] == 8
        assert result['plannedPoints'] == 10
        assert result['completionRate'] == 80.0
    
    def test_transform_backlog_data(self):
        """Test backlog data transformation."""
        # Arrange
        backlog_issues = [
            {
                'fields': {
                    'issuetype': {'name': 'Bug'},
                    'priority': {'name': 'High'},
                    'created': '2024-01-01T00:00:00.000Z'
                }
            },
            {
                'fields': {
                    'issuetype': {'name': 'Feature'},
                    'priority': {'name': 'Medium'},
                    'created': '2024-01-15T00:00:00.000Z'
                }
            },
            {
                'fields': {
                    'issuetype': {'name': 'Bug'},
                    'priority': {'name': 'Low'},
                    'created': '2024-01-20T00:00:00.000Z'
                }
            }
        ]
        
        # Act
        result = transform_backlog_data(backlog_issues)
        
        # Assert
        assert result['totalIssues'] == 3
        assert result['issuesByType']['Bug'] == 2
        assert result['issuesByType']['Feature'] == 1
        assert result['issuesByPriority']['High'] == 1
        assert result['issuesByPriority']['Medium'] == 1
        assert result['issuesByPriority']['Low'] == 1
        assert result['averageAge'] >= 0
    
    def test_transform_milestone_data(self):
        """Test milestone data transformation."""
        # Arrange
        versions = [
            {
                'id': 'v1',
                'name': 'Version 1.0',
                'releaseDate': '2024-06-01',
                'released': False,
                'overdue': False
            },
            {
                'id': 'v2',
                'name': 'Version 2.0',
                'releaseDate': '2024-12-01',
                'released': False,
                'overdue': True
            }
        ]
        
        # Act
        result = transform_milestone_data(versions)
        
        # Assert
        assert len(result) == 2
        assert result[0]['milestoneId'] == 'v1'
        assert result[0]['name'] == 'Version 1.0'
        assert result[0]['status'] == 'ON_TRACK'
        assert result[1]['status'] == 'DELAYED'
    
    def test_transform_resource_data(self):
        """Test resource data transformation."""
        # Arrange
        issues = [
            {
                'fields': {
                    'assignee': {
                        'accountId': 'user1',
                        'displayName': 'John Doe'
                    },
                    'timetracking': {
                        'timeSpentSeconds': 7200  # 2 hours
                    }
                }
            },
            {
                'fields': {
                    'assignee': {
                        'accountId': 'user1',
                        'displayName': 'John Doe'
                    },
                    'timetracking': {
                        'timeSpentSeconds': 10800  # 3 hours
                    }
                }
            },
            {
                'fields': {
                    'assignee': {
                        'accountId': 'user2',
                        'displayName': 'Jane Smith'
                    },
                    'timetracking': {
                        'timeSpentSeconds': 3600  # 1 hour
                    }
                }
            }
        ]
        
        # Act
        result = transform_resource_data(issues)
        
        # Assert
        assert len(result) == 2
        user1 = next(r for r in result if r['userId'] == 'user1')
        assert user1['userName'] == 'John Doe'
        assert user1['allocatedHours'] == 5.0
        assert user1['utilizationRate'] == 12.5  # 5/40 * 100
    
    def test_transform_dependency_data(self):
        """Test dependency data transformation."""
        # Arrange
        issue_links = [
            {
                'type': {'name': 'Blocks'},
                'outwardIssue': {'key': 'PROJ-2'}
            },
            {
                'type': {'name': 'Relates'},
                'inwardIssue': {'key': 'PROJ-3'}
            }
        ]
        
        # Act
        result = transform_dependency_data(issue_links, 'PROJ-1')
        
        # Assert
        assert len(result) == 2
        assert result[0]['sourceTaskId'] == 'PROJ-1'
        assert result[0]['targetTaskId'] == 'PROJ-2'
        assert result[0]['type'] == 'BLOCKS'
        assert result[1]['targetTaskId'] == 'PROJ-1'
        assert result[1]['sourceTaskId'] == 'PROJ-3'


class TestFetchJiraData:
    """Test suite for fetch_jira_data function."""
    
    def test_fetch_success(
        self,
        valid_fetch_event,
        mock_dynamodb,
        mock_secrets_manager,
        mock_jira_client,
        integration_config,
        secret_data
    ):
        """Test successful data fetch."""
        # Arrange
        mock_dynamodb.get_item.return_value = {'Item': integration_config}
        mock_secrets_manager.get_secret_value.return_value = {
            'SecretString': json.dumps(secret_data)
        }
        
        # Mock Jira API responses
        mock_jira_client.fetch_issues_by_jql.return_value = [
            {
                'fields': {
                    'issuetype': {'name': 'Bug'},
                    'priority': {'name': 'High'},
                    'created': '2024-01-01T00:00:00.000Z'
                }
            }
        ]
        mock_jira_client.fetch_project_versions.return_value = []
        
        # Act
        response = fetch_jira_data(valid_fetch_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['tenantId'] == 'tenant-123'
        assert body['integrationId'] == 'integration-123'
        assert 'projects' in body
        assert len(body['projects']) == 2  # PROJ1 and PROJ2
        
        # Verify DynamoDB was queried
        mock_dynamodb.get_item.assert_called_once()
        
        # Verify Secrets Manager was queried
        mock_secrets_manager.get_secret_value.assert_called_once()
        
        # Verify integration sync time was updated
        mock_dynamodb.update_item.assert_called_once()
    
    def test_missing_integration_id(self, mock_dynamodb, mock_secrets_manager):
        """Test error when integration ID is missing."""
        # Arrange
        event = {
            'body': json.dumps({}),
            'requestContext': {
                'authorizer': {
                    'tenantId': 'tenant-123'
                }
            }
        }
        
        # Act
        response = fetch_jira_data(event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'integrationId' in body['error']['message']
    
    def test_integration_not_found(
        self,
        valid_fetch_event,
        mock_dynamodb,
        mock_secrets_manager
    ):
        """Test error when integration is not found."""
        # Arrange
        mock_dynamodb.get_item.return_value = {}  # No Item
        
        # Act
        response = fetch_jira_data(valid_fetch_event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'not found' in body['error']['message']
    
    def test_secrets_manager_failure(
        self,
        valid_fetch_event,
        mock_dynamodb,
        mock_secrets_manager,
        integration_config
    ):
        """Test handling of Secrets Manager failure."""
        # Arrange
        mock_dynamodb.get_item.return_value = {'Item': integration_config}
        mock_secrets_manager.get_secret_value.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Secret not found'}},
            'GetSecretValue'
        )
        
        # Act
        response = fetch_jira_data(valid_fetch_event, None)
        
        # Assert
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert 'Secrets Manager' in body['error']['message']
    
    def test_step_functions_event(
        self,
        mock_dynamodb,
        mock_secrets_manager,
        mock_jira_client,
        integration_config,
        secret_data
    ):
        """Test handling of Step Functions event format."""
        # Arrange
        event = {
            'integrationId': 'integration-123',
            'tenantId': 'tenant-123',
            'requestContext': {
                'authorizer': {
                    'tenantId': 'tenant-123'
                }
            }
        }
        
        mock_dynamodb.get_item.return_value = {'Item': integration_config}
        mock_secrets_manager.get_secret_value.return_value = {
            'SecretString': json.dumps(secret_data)
        }
        mock_jira_client.fetch_issues_by_jql.return_value = []
        mock_jira_client.fetch_project_versions.return_value = []
        
        # Act
        result = fetch_jira_data(event, None)
        
        # Assert
        assert 'tenantId' in result
        assert 'integrationId' in result
        assert 'projects' in result
        assert 'statusCode' not in result  # Step Functions format


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
