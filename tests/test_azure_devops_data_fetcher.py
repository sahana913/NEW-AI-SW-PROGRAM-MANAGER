"""Unit tests for Azure DevOps data fetching Lambda handler."""

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

from azure_devops_integration.data_fetcher import (
    fetch_azure_devops_data,
    AzureDevOpsAPIClient,
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
    with patch('azure_devops_integration.data_fetcher.get_dynamodb') as mock:
        table = MagicMock()
        mock.return_value.Table.return_value = table
        yield table


@pytest.fixture
def mock_secrets_manager():
    """Mock Secrets Manager client."""
    with patch('azure_devops_integration.data_fetcher.get_secrets_manager') as mock:
        client = MagicMock()
        mock.return_value = client
        yield client



@pytest.fixture
def mock_azure_client():
    """Mock Azure DevOps API client."""
    with patch('azure_devops_integration.data_fetcher.AzureDevOpsAPIClient') as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


@pytest.fixture
def valid_fetch_event():
    """Valid event for fetching Azure DevOps data."""
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
        'path': '/integrations/azure-devops/fetch'
    }


@pytest.fixture
def integration_config():
    """Mock integration configuration."""
    return {
        'PK': 'TENANT#tenant-123',
        'SK': 'INTEGRATION#integration-123',
        'integrationId': 'integration-123',
        'tenantId': 'tenant-123',
        'integrationType': 'AZURE_DEVOPS',
        'configuration': {
            'organizationUrl': 'https://dev.azure.com/myorg',
            'projectName': 'MyProject',
            'secretName': 'test-prefix/azure-devops/tenant-123/integration-123'
        },
        'status': 'ACTIVE'
    }


@pytest.fixture
def secret_data():
    """Mock secret data."""
    return {
        'organizationUrl': 'https://dev.azure.com/myorg',
        'projectName': 'MyProject',
        'pat': 'test-pat-token-123'
    }


class TestAzureDevOpsAPIClient:
    """Test suite for AzureDevOpsAPIClient class."""
    
    @patch('azure_devops_integration.data_fetcher.requests.Session')
    def test_init_with_pat(self, mock_session_class):
        """Test client initialization with PAT."""
        # Arrange
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        
        # Act
        client = AzureDevOpsAPIClient(
            'https://dev.azure.com/myorg',
            'test-pat'
        )
        
        # Assert
        assert client.organization_url == 'https://dev.azure.com/myorg'
        assert client.pat == 'test-pat'
        assert mock_session.headers.update.called
    
    @patch('azure_devops_integration.data_fetcher.requests.Session')
    def test_make_request_success(self, mock_session_class):
        """Test successful API request."""
        # Arrange
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'value': []}
        mock_session.request.return_value = mock_response
        
        client = AzureDevOpsAPIClient(
            'https://dev.azure.com/myorg',
            'test-pat'
        )
        
        # Act
        result = client._make_request('GET', 'https://dev.azure.com/myorg/_apis/projects')
        
        # Assert
        assert result == {'value': []}
        mock_session.request.assert_called_once()
    
    @patch('azure_devops_integration.data_fetcher.requests.Session')
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
        mock_response_200.json.return_value = {'value': []}
        
        mock_session.request.side_effect = [mock_response_429, mock_response_200]
        
        client = AzureDevOpsAPIClient(
            'https://dev.azure.com/myorg',
            'test-pat'
        )
        
        # Act
        result = client._make_request('GET', 'https://dev.azure.com/myorg/_apis/projects')
        
        # Assert
        assert result == {'value': []}
        assert mock_session.request.call_count == 2
        mock_sleep.assert_called_once_with(1)  # First retry delay
    
    @patch('azure_devops_integration.data_fetcher.requests.Session')
    @patch('time.sleep')
    def test_make_request_max_retries_exceeded(self, mock_sleep, mock_session_class):
        """Test failure after maximum retries."""
        # Arrange
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_session.request.return_value = mock_response
        
        client = AzureDevOpsAPIClient(
            'https://dev.azure.com/myorg',
            'test-pat'
        )
        
        # Act & Assert
        with pytest.raises(DataError) as exc_info:
            client._make_request('GET', 'https://dev.azure.com/myorg/_apis/projects')
        
        assert 'rate limit exceeded' in str(exc_info.value).lower()
        assert mock_session.request.call_count == 5  # Max retries



class TestTransformFunctions:
    """Test suite for data transformation functions."""
    
    def test_transform_sprint_data(self):
        """Test sprint data transformation."""
        # Arrange
        iteration = {
            'id': 'iter-123',
            'name': 'Sprint 1',
            'attributes': {
                'startDate': '2024-01-01T00:00:00Z',
                'finishDate': '2024-01-14T00:00:00Z'
            }
        }
        
        work_items = [
            {
                'fields': {
                    'Microsoft.VSTS.Scheduling.StoryPoints': 5,
                    'System.State': 'Done'
                }
            },
            {
                'fields': {
                    'Microsoft.VSTS.Scheduling.Effort': 3,
                    'System.State': 'Completed'
                }
            },
            {
                'fields': {
                    'Microsoft.VSTS.Scheduling.StoryPoints': 2,
                    'System.State': 'Active'
                }
            }
        ]
        
        # Act
        result = transform_sprint_data(iteration, work_items)
        
        # Assert
        assert result['sprintId'] == 'iter-123'
        assert result['sprintName'] == 'Sprint 1'
        assert result['velocity'] == 8  # 5 + 3 completed
        assert result['completedPoints'] == 8
        assert result['plannedPoints'] == 10  # 5 + 3 + 2
        assert result['completionRate'] == 80.0
    
    def test_transform_backlog_data(self):
        """Test backlog data transformation."""
        # Arrange
        work_items = [
            {
                'fields': {
                    'System.WorkItemType': 'Bug',
                    'Microsoft.VSTS.Common.Priority': 1,
                    'System.CreatedDate': '2024-01-01T00:00:00Z'
                }
            },
            {
                'fields': {
                    'System.WorkItemType': 'User Story',
                    'Microsoft.VSTS.Common.Priority': 2,
                    'System.CreatedDate': '2024-01-15T00:00:00Z'
                }
            },
            {
                'fields': {
                    'System.WorkItemType': 'Bug',
                    'Microsoft.VSTS.Common.Priority': 3,
                    'System.CreatedDate': '2024-01-20T00:00:00Z'
                }
            }
        ]
        
        # Act
        result = transform_backlog_data(work_items)
        
        # Assert
        assert result['totalIssues'] == 3
        assert result['issuesByType']['Bug'] == 2
        assert result['issuesByType']['User Story'] == 1
        assert result['issuesByPriority']['Priority 1'] == 1
        assert result['issuesByPriority']['Priority 2'] == 1
        assert result['issuesByPriority']['Priority 3'] == 1
        assert result['averageAge'] >= 0
    
    def test_transform_milestone_data(self):
        """Test milestone data transformation."""
        # Arrange
        iterations = [
            {
                'id': 'iter-1',
                'name': 'Sprint 1',
                'attributes': {
                    'startDate': '2024-01-01T00:00:00Z',
                    'finishDate': '2024-01-14T00:00:00Z'
                }
            },
            {
                'id': 'iter-2',
                'name': 'Sprint 2',
                'attributes': {
                    'startDate': '2024-01-15T00:00:00Z',
                    'finishDate': '2025-12-31T00:00:00Z'
                }
            }
        ]
        
        # Act
        result = transform_milestone_data(iterations)
        
        # Assert
        assert len(result) == 2
        assert result[0]['milestoneId'] == 'iter-1'
        assert result[0]['name'] == 'Sprint 1'
        assert result[1]['milestoneId'] == 'iter-2'
    
    def test_transform_resource_data(self):
        """Test resource data transformation."""
        # Arrange
        work_items = [
            {
                'fields': {
                    'System.AssignedTo': {
                        'uniqueName': 'user1@example.com',
                        'displayName': 'John Doe'
                    },
                    'Microsoft.VSTS.Scheduling.CompletedWork': 2,
                    'Microsoft.VSTS.Scheduling.RemainingWork': 3
                }
            },
            {
                'fields': {
                    'System.AssignedTo': {
                        'uniqueName': 'user1@example.com',
                        'displayName': 'John Doe'
                    },
                    'Microsoft.VSTS.Scheduling.CompletedWork': 5,
                    'Microsoft.VSTS.Scheduling.RemainingWork': 0
                }
            },
            {
                'fields': {
                    'System.AssignedTo': {
                        'uniqueName': 'user2@example.com',
                        'displayName': 'Jane Smith'
                    },
                    'Microsoft.VSTS.Scheduling.CompletedWork': 1,
                    'Microsoft.VSTS.Scheduling.RemainingWork': 2
                }
            }
        ]
        
        # Act
        result = transform_resource_data(work_items)
        
        # Assert
        assert len(result) == 2
        user1 = next(r for r in result if r['userId'] == 'user1@example.com')
        assert user1['userName'] == 'John Doe'
        assert user1['allocatedHours'] == 10.0  # 2+3+5+0
        assert user1['utilizationRate'] == 25.0  # 10/40 * 100
    
    def test_transform_dependency_data(self):
        """Test dependency data transformation."""
        # Arrange
        work_items = [
            {
                'id': 1,
                'relations': [
                    {
                        'rel': 'System.LinkTypes.Dependency-Forward',
                        'url': 'https://dev.azure.com/org/_apis/wit/workItems/2'
                    },
                    {
                        'rel': 'System.LinkTypes.Predecessor',
                        'url': 'https://dev.azure.com/org/_apis/wit/workItems/3'
                    }
                ]
            }
        ]
        
        # Act
        result = transform_dependency_data(work_items)
        
        # Assert
        assert len(result) == 2
        assert result[0]['sourceTaskId'] == '1'
        assert result[0]['targetTaskId'] == '2'
        assert result[1]['sourceTaskId'] == '1'
        assert result[1]['targetTaskId'] == '3'
        assert result[1]['type'] == 'BLOCKS'



class TestFetchAzureDevOpsData:
    """Test suite for fetch_azure_devops_data function."""
    
    @patch('azure_devops_integration.data_fetcher.store_multiple_projects')
    def test_fetch_success(
        self,
        mock_store,
        valid_fetch_event,
        mock_dynamodb,
        mock_secrets_manager,
        mock_azure_client,
        integration_config,
        secret_data
    ):
        """Test successful data fetch."""
        # Arrange
        mock_dynamodb.get_item.return_value = {'Item': integration_config}
        mock_secrets_manager.get_secret_value.return_value = {
            'SecretString': json.dumps(secret_data)
        }
        
        # Mock Azure DevOps API responses
        mock_azure_client.fetch_work_items.return_value = [
            {
                'fields': {
                    'System.WorkItemType': 'Bug',
                    'Microsoft.VSTS.Common.Priority': 1,
                    'System.CreatedDate': '2024-01-01T00:00:00Z'
                }
            }
        ]
        mock_azure_client.fetch_iterations.return_value = []
        mock_azure_client.fetch_builds.return_value = []
        mock_azure_client.fetch_releases.return_value = []
        
        # Mock storage
        mock_store.return_value = {
            'total': 1,
            'successful': 1,
            'failed': 0,
            'projects': [],
            'errors': []
        }
        
        # Act
        response = fetch_azure_devops_data(valid_fetch_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['tenantId'] == 'tenant-123'
        assert body['integrationId'] == 'integration-123'
        assert 'projects' in body
        assert len(body['projects']) == 1
        
        # Verify DynamoDB was queried
        mock_dynamodb.get_item.assert_called_once()
        
        # Verify Secrets Manager was queried
        mock_secrets_manager.get_secret_value.assert_called_once()
        
        # Verify integration sync time was updated
        mock_dynamodb.update_item.assert_called_once()
        
        # Verify storage was called
        mock_store.assert_called_once()
    
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
        response = fetch_azure_devops_data(event, None)
        
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
        response = fetch_azure_devops_data(valid_fetch_event, None)
        
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
        response = fetch_azure_devops_data(valid_fetch_event, None)
        
        # Assert
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert 'Secrets Manager' in body['error']['message']
    
    @patch('azure_devops_integration.data_fetcher.store_multiple_projects')
    def test_step_functions_event(
        self,
        mock_store,
        mock_dynamodb,
        mock_secrets_manager,
        mock_azure_client,
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
        mock_azure_client.fetch_work_items.return_value = []
        mock_azure_client.fetch_iterations.return_value = []
        mock_azure_client.fetch_builds.return_value = []
        mock_azure_client.fetch_releases.return_value = []
        
        mock_store.return_value = {
            'total': 1,
            'successful': 1,
            'failed': 0,
            'projects': [],
            'errors': []
        }
        
        # Act
        result = fetch_azure_devops_data(event, None)
        
        # Assert
        assert 'tenantId' in result
        assert 'integrationId' in result
        assert 'projects' in result
        assert 'statusCode' not in result  # Step Functions format
    
    @patch('azure_devops_integration.data_fetcher.store_multiple_projects')
    @patch('azure_devops_integration.data_fetcher.send_admin_alert')
    def test_storage_failure_sends_alert(
        self,
        mock_alert,
        mock_store,
        valid_fetch_event,
        mock_dynamodb,
        mock_secrets_manager,
        mock_azure_client,
        integration_config,
        secret_data
    ):
        """Test that storage failures trigger admin alerts."""
        # Arrange
        mock_dynamodb.get_item.return_value = {'Item': integration_config}
        mock_secrets_manager.get_secret_value.return_value = {
            'SecretString': json.dumps(secret_data)
        }
        
        mock_azure_client.fetch_work_items.return_value = []
        mock_azure_client.fetch_iterations.return_value = []
        mock_azure_client.fetch_builds.return_value = []
        mock_azure_client.fetch_releases.return_value = []
        
        # Mock storage with failures
        mock_store.return_value = {
            'total': 1,
            'successful': 0,
            'failed': 1,
            'projects': [],
            'errors': [{'project_name': 'MyProject', 'error': 'Validation failed'}]
        }
        
        # Act
        response = fetch_azure_devops_data(valid_fetch_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        mock_alert.assert_called_once()
        alert_call = mock_alert.call_args
        assert 'Azure DevOps Data Ingestion Failures' in alert_call[1]['subject']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
