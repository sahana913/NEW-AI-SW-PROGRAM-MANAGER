"""Unit tests for Jira integration Lambda handler."""

import json
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from botocore.exceptions import ClientError

# Set up environment variables before importing handler
os.environ['INTEGRATIONS_TABLE_NAME'] = 'test-integrations'
os.environ['SECRETS_MANAGER_PREFIX'] = 'test-prefix'
os.environ['USER_POOL_ID'] = 'test-pool-id'

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from jira_integration.handler import configure_jira_integration
from shared.errors import ValidationError, AuthorizationError, DataError


@pytest.fixture
def mock_dynamodb():
    """Mock DynamoDB resource."""
    with patch('jira_integration.handler.get_dynamodb') as mock:
        table = MagicMock()
        mock.return_value.Table.return_value = table
        yield table


@pytest.fixture
def mock_secrets_manager():
    """Mock Secrets Manager client."""
    with patch('jira_integration.handler.get_secrets_manager') as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


@pytest.fixture
def valid_api_token_event():
    """Valid API Gateway event with API token authentication."""
    return {
        'body': json.dumps({
            'jiraUrl': 'https://example.atlassian.net',
            'authType': 'API_TOKEN',
            'credentials': {
                'apiToken': 'test-api-token-12345'
            },
            'projectKeys': ['PROJ1', 'PROJ2'],
            'syncSchedule': 'cron(0 0 * * ? *)'
        }),
        'requestContext': {
            'authorizer': {
                'role': 'ADMIN',
                'userId': 'user-123',
                'tenantId': 'tenant-123'
            }
        },
        'httpMethod': 'POST',
        'path': '/integrations/jira/configure'
    }


@pytest.fixture
def valid_oauth_event():
    """Valid API Gateway event with OAuth authentication."""
    return {
        'body': json.dumps({
            'jiraUrl': 'https://example.atlassian.net',
            'authType': 'OAUTH',
            'credentials': {
                'oauthClientId': 'client-id-123',
                'oauthClientSecret': 'client-secret-456'
            },
            'projectKeys': ['PROJ1'],
            'syncSchedule': 'cron(0 */6 * * ? *)'
        }),
        'requestContext': {
            'authorizer': {
                'role': 'PROGRAM_MANAGER',
                'userId': 'user-456',
                'tenantId': 'tenant-456'
            }
        },
        'httpMethod': 'POST',
        'path': '/integrations/jira/configure'
    }


class TestConfigureJiraIntegration:
    """Test suite for configure_jira_integration function."""
    
    def test_configure_with_api_token_success(
        self,
        valid_api_token_event,
        mock_dynamodb,
        mock_secrets_manager
    ):
        """Test successful configuration with API token."""
        # Arrange
        mock_secrets_manager.create_secret.return_value = {
            'ARN': 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test',
            'Name': 'test-secret'
        }
        mock_dynamodb.put_item.return_value = {}
        
        # Act
        response = configure_jira_integration(valid_api_token_event, None)
        
        # Assert
        assert response['statusCode'] == 201
        body = json.loads(response['body'])
        assert 'integrationId' in body
        assert body['status'] == 'ACTIVE'
        
        # Verify Secrets Manager was called
        mock_secrets_manager.create_secret.assert_called_once()
        call_args = mock_secrets_manager.create_secret.call_args
        assert 'test-prefix/jira/tenant-123' in call_args[1]['Name']
        
        secret_value = json.loads(call_args[1]['SecretString'])
        assert secret_value['jiraUrl'] == 'https://example.atlassian.net'
        assert secret_value['authType'] == 'API_TOKEN'
        assert secret_value['credentials']['apiToken'] == 'test-api-token-12345'
        
        # Verify DynamoDB was called
        mock_dynamodb.put_item.assert_called_once()
        item = mock_dynamodb.put_item.call_args[1]['Item']
        assert item['PK'] == 'TENANT#tenant-123'
        assert item['SK'].startswith('INTEGRATION#')
        assert item['integrationType'] == 'JIRA'
        assert item['status'] == 'ACTIVE'
        assert item['configuration']['projectKeys'] == ['PROJ1', 'PROJ2']
    
    def test_configure_with_oauth_success(
        self,
        valid_oauth_event,
        mock_dynamodb,
        mock_secrets_manager
    ):
        """Test successful configuration with OAuth."""
        # Arrange
        mock_secrets_manager.create_secret.return_value = {
            'ARN': 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test',
            'Name': 'test-secret'
        }
        mock_dynamodb.put_item.return_value = {}
        
        # Act
        response = configure_jira_integration(valid_oauth_event, None)
        
        # Assert
        assert response['statusCode'] == 201
        body = json.loads(response['body'])
        assert 'integrationId' in body
        assert body['status'] == 'ACTIVE'
        
        # Verify OAuth credentials were stored
        call_args = mock_secrets_manager.create_secret.call_args
        secret_value = json.loads(call_args[1]['SecretString'])
        assert secret_value['authType'] == 'OAUTH'
        assert 'oauthClientId' in secret_value['credentials']
        assert 'oauthClientSecret' in secret_value['credentials']
    
    def test_missing_required_fields(self, mock_dynamodb, mock_secrets_manager):
        """Test validation error for missing required fields."""
        # Arrange
        event = {
            'body': json.dumps({
                'jiraUrl': 'https://example.atlassian.net'
                # Missing authType, credentials, projectKeys, syncSchedule
            }),
            'requestContext': {
                'authorizer': {
                    'role': 'ADMIN',
                    'userId': 'user-123',
                    'tenantId': 'tenant-123'
                }
            },
            'httpMethod': 'POST',
            'path': '/integrations/jira/configure'
        }
        
        # Act
        response = configure_jira_integration(event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'error' in body
        assert 'Missing required fields' in body['error']['message']
    
    def test_invalid_auth_type(self, mock_dynamodb, mock_secrets_manager):
        """Test validation error for invalid auth type."""
        # Arrange
        event = {
            'body': json.dumps({
                'jiraUrl': 'https://example.atlassian.net',
                'authType': 'INVALID_TYPE',
                'credentials': {'apiToken': 'test'},
                'projectKeys': ['PROJ1'],
                'syncSchedule': 'cron(0 0 * * ? *)'
            }),
            'requestContext': {
                'authorizer': {
                    'role': 'ADMIN',
                    'userId': 'user-123',
                    'tenantId': 'tenant-123'
                }
            },
            'httpMethod': 'POST',
            'path': '/integrations/jira/configure'
        }
        
        # Act
        response = configure_jira_integration(event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'authType must be either' in body['error']['message']
    
    def test_missing_api_token_credentials(self, mock_dynamodb, mock_secrets_manager):
        """Test validation error for missing API token."""
        # Arrange
        event = {
            'body': json.dumps({
                'jiraUrl': 'https://example.atlassian.net',
                'authType': 'API_TOKEN',
                'credentials': {},  # Missing apiToken
                'projectKeys': ['PROJ1'],
                'syncSchedule': 'cron(0 0 * * ? *)'
            }),
            'requestContext': {
                'authorizer': {
                    'role': 'ADMIN',
                    'userId': 'user-123',
                    'tenantId': 'tenant-123'
                }
            },
            'httpMethod': 'POST',
            'path': '/integrations/jira/configure'
        }
        
        # Act
        response = configure_jira_integration(event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'credentials' in body['error']['message'].lower()
    
    def test_missing_oauth_credentials(self, mock_dynamodb, mock_secrets_manager):
        """Test validation error for missing OAuth credentials."""
        # Arrange
        event = {
            'body': json.dumps({
                'jiraUrl': 'https://example.atlassian.net',
                'authType': 'OAUTH',
                'credentials': {
                    'oauthClientId': 'client-id'
                    # Missing oauthClientSecret
                },
                'projectKeys': ['PROJ1'],
                'syncSchedule': 'cron(0 0 * * ? *)'
            }),
            'requestContext': {
                'authorizer': {
                    'role': 'ADMIN',
                    'userId': 'user-123',
                    'tenantId': 'tenant-123'
                }
            },
            'httpMethod': 'POST',
            'path': '/integrations/jira/configure'
        }
        
        # Act
        response = configure_jira_integration(event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'credentials' in body['error']['message'].lower()
    
    def test_empty_project_keys(self, mock_dynamodb, mock_secrets_manager):
        """Test validation error for empty project keys."""
        # Arrange
        event = {
            'body': json.dumps({
                'jiraUrl': 'https://example.atlassian.net',
                'authType': 'API_TOKEN',
                'credentials': {'apiToken': 'test'},
                'projectKeys': [],  # Empty array
                'syncSchedule': 'cron(0 0 * * ? *)'
            }),
            'requestContext': {
                'authorizer': {
                    'role': 'ADMIN',
                    'userId': 'user-123',
                    'tenantId': 'tenant-123'
                }
            },
            'httpMethod': 'POST',
            'path': '/integrations/jira/configure'
        }
        
        # Act
        response = configure_jira_integration(event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'projectKeys' in body['error']['message']
    
    def test_invalid_url_format(self, mock_dynamodb, mock_secrets_manager):
        """Test validation error for invalid URL format."""
        # Arrange
        event = {
            'body': json.dumps({
                'jiraUrl': 'not-a-valid-url',
                'authType': 'API_TOKEN',
                'credentials': {'apiToken': 'test'},
                'projectKeys': ['PROJ1'],
                'syncSchedule': 'cron(0 0 * * ? *)'
            }),
            'requestContext': {
                'authorizer': {
                    'role': 'ADMIN',
                    'userId': 'user-123',
                    'tenantId': 'tenant-123'
                }
            },
            'httpMethod': 'POST',
            'path': '/integrations/jira/configure'
        }
        
        # Act
        response = configure_jira_integration(event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'jiraUrl' in body['error']['message']
    
    def test_unauthorized_role(self, mock_dynamodb, mock_secrets_manager):
        """Test authorization error for unauthorized role."""
        # Arrange
        event = {
            'body': json.dumps({
                'jiraUrl': 'https://example.atlassian.net',
                'authType': 'API_TOKEN',
                'credentials': {'apiToken': 'test'},
                'projectKeys': ['PROJ1'],
                'syncSchedule': 'cron(0 0 * * ? *)'
            }),
            'requestContext': {
                'authorizer': {
                    'role': 'TEAM_MEMBER',  # Not authorized
                    'userId': 'user-123',
                    'tenantId': 'tenant-123'
                }
            },
            'httpMethod': 'POST',
            'path': '/integrations/jira/configure'
        }
        
        # Act
        response = configure_jira_integration(event, None)
        
        # Assert
        assert response['statusCode'] == 403
        body = json.loads(response['body'])
        assert 'administrators and program managers' in body['error']['message']
    
    def test_secrets_manager_failure(
        self,
        valid_api_token_event,
        mock_dynamodb,
        mock_secrets_manager
    ):
        """Test handling of Secrets Manager failure."""
        # Arrange
        mock_secrets_manager.create_secret.side_effect = ClientError(
            {'Error': {'Code': 'InternalServiceError', 'Message': 'Service error'}},
            'CreateSecret'
        )
        
        # Act
        response = configure_jira_integration(valid_api_token_event, None)
        
        # Assert
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert 'Secrets Manager' in body['error']['message']
    
    def test_dynamodb_failure_with_rollback(
        self,
        valid_api_token_event,
        mock_dynamodb,
        mock_secrets_manager
    ):
        """Test handling of DynamoDB failure with Secrets Manager rollback."""
        # Arrange
        mock_secrets_manager.create_secret.return_value = {
            'ARN': 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test',
            'Name': 'test-secret'
        }
        mock_dynamodb.put_item.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'DB error'}},
            'PutItem'
        )
        
        # Act
        response = configure_jira_integration(valid_api_token_event, None)
        
        # Assert
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert 'DynamoDB' in body['error']['message']
        
        # Verify rollback was attempted
        mock_secrets_manager.delete_secret.assert_called_once()
        call_args = mock_secrets_manager.delete_secret.call_args
        assert call_args[1]['ForceDeleteWithoutRecovery'] is True
    
    def test_duplicate_secret(
        self,
        valid_api_token_event,
        mock_dynamodb,
        mock_secrets_manager
    ):
        """Test handling of duplicate secret."""
        # Arrange
        mock_secrets_manager.create_secret.side_effect = ClientError(
            {'Error': {'Code': 'ResourceExistsException', 'Message': 'Secret exists'}},
            'CreateSecret'
        )
        
        # Act
        response = configure_jira_integration(valid_api_token_event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'already exists' in body['error']['message']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
