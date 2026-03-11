"""Unit tests for Azure DevOps integration Lambda handler."""

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

from azure_devops_integration.handler import configure_azure_devops_integration
from shared.errors import ValidationError, AuthorizationError, DataError


@pytest.fixture
def mock_dynamodb():
    """Mock DynamoDB resource."""
    with patch('azure_devops_integration.handler.get_dynamodb') as mock:
        table = MagicMock()
        mock.return_value.Table.return_value = table
        yield table


@pytest.fixture
def mock_secrets_manager():
    """Mock Secrets Manager client."""
    with patch('azure_devops_integration.handler.get_secrets_manager') as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


@pytest.fixture
def valid_event():
    """Valid API Gateway event for Azure DevOps configuration."""
    return {
        'body': json.dumps({
            'organizationUrl': 'https://dev.azure.com/myorg',
            'projectName': 'MyProject',
            'pat': 'test-personal-access-token-12345'
        }),
        'requestContext': {
            'authorizer': {
                'role': 'ADMIN',
                'userId': 'user-123',
                'tenantId': 'tenant-123'
            }
        },
        'httpMethod': 'POST',
        'path': '/integrations/azure-devops/configure'
    }


@pytest.fixture
def program_manager_event():
    """Valid event with PROGRAM_MANAGER role."""
    return {
        'body': json.dumps({
            'organizationUrl': 'https://dev.azure.com/testorg',
            'projectName': 'TestProject',
            'pat': 'test-pat-token-67890'
        }),
        'requestContext': {
            'authorizer': {
                'role': 'PROGRAM_MANAGER',
                'userId': 'user-456',
                'tenantId': 'tenant-456'
            }
        },
        'httpMethod': 'POST',
        'path': '/integrations/azure-devops/configure'
    }


class TestConfigureAzureDevOpsIntegration:
    """Test suite for configure_azure_devops_integration function."""
    
    def test_configure_success(
        self,
        valid_event,
        mock_dynamodb,
        mock_secrets_manager
    ):
        """Test successful Azure DevOps configuration."""
        # Arrange
        mock_secrets_manager.create_secret.return_value = {
            'ARN': 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test',
            'Name': 'test-secret'
        }
        mock_dynamodb.put_item.return_value = {}
        
        # Act
        response = configure_azure_devops_integration(valid_event, None)
        
        # Assert
        assert response['statusCode'] == 201
        body = json.loads(response['body'])
        assert 'integrationId' in body
        assert body['status'] == 'ACTIVE'
        
        # Verify Secrets Manager was called
        mock_secrets_manager.create_secret.assert_called_once()
        call_args = mock_secrets_manager.create_secret.call_args
        assert 'test-prefix/azure-devops/tenant-123' in call_args[1]['Name']
        
        secret_value = json.loads(call_args[1]['SecretString'])
        assert secret_value['organizationUrl'] == 'https://dev.azure.com/myorg'
        assert secret_value['projectName'] == 'MyProject'
        assert secret_value['pat'] == 'test-personal-access-token-12345'
        
        # Verify DynamoDB was called
        mock_dynamodb.put_item.assert_called_once()
        item = mock_dynamodb.put_item.call_args[1]['Item']
        assert item['PK'] == 'TENANT#tenant-123'
        assert item['SK'].startswith('INTEGRATION#')
        assert item['integrationType'] == 'AZURE_DEVOPS'
        assert item['status'] == 'ACTIVE'
        assert item['configuration']['organizationUrl'] == 'https://dev.azure.com/myorg'
        assert item['configuration']['projectName'] == 'MyProject'
    
    def test_configure_with_program_manager_role(
        self,
        program_manager_event,
        mock_dynamodb,
        mock_secrets_manager
    ):
        """Test successful configuration with PROGRAM_MANAGER role."""
        # Arrange
        mock_secrets_manager.create_secret.return_value = {
            'ARN': 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test',
            'Name': 'test-secret'
        }
        mock_dynamodb.put_item.return_value = {}
        
        # Act
        response = configure_azure_devops_integration(program_manager_event, None)
        
        # Assert
        assert response['statusCode'] == 201
        body = json.loads(response['body'])
        assert 'integrationId' in body
        assert body['status'] == 'ACTIVE'
    
    def test_missing_required_fields(self, mock_dynamodb, mock_secrets_manager):
        """Test validation error for missing required fields."""
        # Arrange
        event = {
            'body': json.dumps({
                'organizationUrl': 'https://dev.azure.com/myorg'
                # Missing projectName and pat
            }),
            'requestContext': {
                'authorizer': {
                    'role': 'ADMIN',
                    'userId': 'user-123',
                    'tenantId': 'tenant-123'
                }
            },
            'httpMethod': 'POST',
            'path': '/integrations/azure-devops/configure'
        }
        
        # Act
        response = configure_azure_devops_integration(event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'error' in body
        assert 'Missing required fields' in body['error']['message']
    
    def test_invalid_organization_url(self, mock_dynamodb, mock_secrets_manager):
        """Test validation error for invalid organization URL."""
        # Arrange
        event = {
            'body': json.dumps({
                'organizationUrl': 'not-a-valid-url',
                'projectName': 'MyProject',
                'pat': 'test-pat'
            }),
            'requestContext': {
                'authorizer': {
                    'role': 'ADMIN',
                    'userId': 'user-123',
                    'tenantId': 'tenant-123'
                }
            },
            'httpMethod': 'POST',
            'path': '/integrations/azure-devops/configure'
        }
        
        # Act
        response = configure_azure_devops_integration(event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'organizationUrl' in body['error']['message']
    
    def test_empty_project_name(self, mock_dynamodb, mock_secrets_manager):
        """Test validation error for empty project name."""
        # Arrange
        event = {
            'body': json.dumps({
                'organizationUrl': 'https://dev.azure.com/myorg',
                'projectName': '',  # Empty string
                'pat': 'test-pat'
            }),
            'requestContext': {
                'authorizer': {
                    'role': 'ADMIN',
                    'userId': 'user-123',
                    'tenantId': 'tenant-123'
                }
            },
            'httpMethod': 'POST',
            'path': '/integrations/azure-devops/configure'
        }
        
        # Act
        response = configure_azure_devops_integration(event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'projectName' in body['error']['message']
    
    def test_empty_pat(self, mock_dynamodb, mock_secrets_manager):
        """Test validation error for empty PAT."""
        # Arrange
        event = {
            'body': json.dumps({
                'organizationUrl': 'https://dev.azure.com/myorg',
                'projectName': 'MyProject',
                'pat': '   '  # Whitespace only
            }),
            'requestContext': {
                'authorizer': {
                    'role': 'ADMIN',
                    'userId': 'user-123',
                    'tenantId': 'tenant-123'
                }
            },
            'httpMethod': 'POST',
            'path': '/integrations/azure-devops/configure'
        }
        
        # Act
        response = configure_azure_devops_integration(event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'pat' in body['error']['message'].lower()
    
    def test_unauthorized_role(self, mock_dynamodb, mock_secrets_manager):
        """Test authorization error for unauthorized role."""
        # Arrange
        event = {
            'body': json.dumps({
                'organizationUrl': 'https://dev.azure.com/myorg',
                'projectName': 'MyProject',
                'pat': 'test-pat'
            }),
            'requestContext': {
                'authorizer': {
                    'role': 'TEAM_MEMBER',  # Not authorized
                    'userId': 'user-123',
                    'tenantId': 'tenant-123'
                }
            },
            'httpMethod': 'POST',
            'path': '/integrations/azure-devops/configure'
        }
        
        # Act
        response = configure_azure_devops_integration(event, None)
        
        # Assert
        assert response['statusCode'] == 403
        body = json.loads(response['body'])
        assert 'administrators and program managers' in body['error']['message']
    
    def test_executive_role_unauthorized(self, mock_dynamodb, mock_secrets_manager):
        """Test authorization error for EXECUTIVE role."""
        # Arrange
        event = {
            'body': json.dumps({
                'organizationUrl': 'https://dev.azure.com/myorg',
                'projectName': 'MyProject',
                'pat': 'test-pat'
            }),
            'requestContext': {
                'authorizer': {
                    'role': 'EXECUTIVE',  # Not authorized
                    'userId': 'user-123',
                    'tenantId': 'tenant-123'
                }
            },
            'httpMethod': 'POST',
            'path': '/integrations/azure-devops/configure'
        }
        
        # Act
        response = configure_azure_devops_integration(event, None)
        
        # Assert
        assert response['statusCode'] == 403
        body = json.loads(response['body'])
        assert 'administrators and program managers' in body['error']['message']
    
    def test_secrets_manager_failure(
        self,
        valid_event,
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
        response = configure_azure_devops_integration(valid_event, None)
        
        # Assert
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert 'Secrets Manager' in body['error']['message']
    
    def test_dynamodb_failure_with_rollback(
        self,
        valid_event,
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
        response = configure_azure_devops_integration(valid_event, None)
        
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
        valid_event,
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
        response = configure_azure_devops_integration(valid_event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'already exists' in body['error']['message']
    
    def test_secret_name_format(
        self,
        valid_event,
        mock_dynamodb,
        mock_secrets_manager
    ):
        """Test that secret name follows correct format."""
        # Arrange
        mock_secrets_manager.create_secret.return_value = {
            'ARN': 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test',
            'Name': 'test-secret'
        }
        mock_dynamodb.put_item.return_value = {}
        
        # Act
        response = configure_azure_devops_integration(valid_event, None)
        
        # Assert
        call_args = mock_secrets_manager.create_secret.call_args
        secret_name = call_args[1]['Name']
        
        # Verify format: {prefix}/azure-devops/{tenantId}/{integrationId}
        assert secret_name.startswith('test-prefix/azure-devops/tenant-123/')
        assert len(secret_name.split('/')) == 4
    
    def test_secret_tags(
        self,
        valid_event,
        mock_dynamodb,
        mock_secrets_manager
    ):
        """Test that secret is tagged correctly."""
        # Arrange
        mock_secrets_manager.create_secret.return_value = {
            'ARN': 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test',
            'Name': 'test-secret'
        }
        mock_dynamodb.put_item.return_value = {}
        
        # Act
        response = configure_azure_devops_integration(valid_event, None)
        
        # Assert
        call_args = mock_secrets_manager.create_secret.call_args
        tags = call_args[1]['Tags']
        
        tag_dict = {tag['Key']: tag['Value'] for tag in tags}
        assert tag_dict['TenantId'] == 'tenant-123'
        assert tag_dict['IntegrationType'] == 'AZURE_DEVOPS'
        assert 'IntegrationId' in tag_dict
    
    def test_dynamodb_item_structure(
        self,
        valid_event,
        mock_dynamodb,
        mock_secrets_manager
    ):
        """Test that DynamoDB item has correct structure."""
        # Arrange
        mock_secrets_manager.create_secret.return_value = {
            'ARN': 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test',
            'Name': 'test-secret'
        }
        mock_dynamodb.put_item.return_value = {}
        
        # Act
        response = configure_azure_devops_integration(valid_event, None)
        
        # Assert
        item = mock_dynamodb.put_item.call_args[1]['Item']
        
        # Verify required fields
        assert 'PK' in item
        assert 'SK' in item
        assert 'integrationId' in item
        assert 'tenantId' in item
        assert 'integrationType' in item
        assert 'configuration' in item
        assert 'status' in item
        assert 'createdAt' in item
        assert 'lastSyncAt' in item
        assert 'nextSyncAt' in item
        
        # Verify configuration structure
        config = item['configuration']
        assert 'organizationUrl' in config
        assert 'projectName' in config
        assert 'secretName' in config
        
        # Verify PAT is NOT stored in DynamoDB (only in Secrets Manager)
        assert 'pat' not in config


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
