"""Unit tests for User Management Lambda functions."""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from botocore.exceptions import ClientError

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from user_management.handler import create_user, list_users, update_user_role, generate_temporary_password
from shared.errors import ValidationError, AuthorizationError, DataError


@pytest.fixture
def mock_env(monkeypatch):
    """Set up environment variables for tests."""
    monkeypatch.setenv('USERS_TABLE_NAME', 'Users')
    monkeypatch.setenv('USER_POOL_ID', 'us-east-1_TEST123')
    monkeypatch.setenv('AWS_REGION', 'us-east-1')


@pytest.fixture
def mock_context():
    """Mock Lambda context."""
    context = Mock()
    context.request_id = 'test-request-id'
    context.function_name = 'test-function'
    return context


@pytest.fixture
def admin_event():
    """Create a mock event with admin authorization."""
    return {
        'httpMethod': 'POST',
        'path': '/users',
        'requestContext': {
            'authorizer': {
                'userId': 'admin-user-id',
                'tenantId': 'tenant-123',
                'role': 'ADMIN',
                'email': 'admin@example.com'
            }
        },
        'body': json.dumps({
            'email': 'newuser@example.com',
            'firstName': 'John',
            'lastName': 'Doe',
            'role': 'PROGRAM_MANAGER'
        })
    }


@pytest.fixture
def non_admin_event():
    """Create a mock event with non-admin authorization."""
    return {
        'httpMethod': 'POST',
        'path': '/users',
        'requestContext': {
            'authorizer': {
                'userId': 'user-id',
                'tenantId': 'tenant-123',
                'role': 'PROGRAM_MANAGER',
                'email': 'user@example.com'
            }
        },
        'body': json.dumps({
            'email': 'newuser@example.com',
            'firstName': 'John',
            'lastName': 'Doe',
            'role': 'TEAM_MEMBER'
        })
    }


class TestCreateUser:
    """Tests for create_user function."""
    
    @patch('user_management.handler.get_dynamodb')
    @patch('user_management.handler.get_cognito_client')
    def test_create_user_success(self, mock_get_cognito, mock_get_dynamodb, admin_event, mock_context, mock_env):
        """Test successful user creation."""
        # Mock Cognito client
        mock_cognito = Mock()
        mock_get_cognito.return_value = mock_cognito
        mock_cognito.admin_create_user.return_value = {
            'User': {
                'Username': 'newuser@example.com',
                'Attributes': []
            }
        }
        
        # Mock DynamoDB resource
        mock_dynamodb = Mock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.put_item.return_value = {}
        
        # Call function
        response = create_user(admin_event, mock_context)
        
        # Assertions
        assert response['statusCode'] == 201
        body = json.loads(response['body'])
        assert 'userId' in body
        assert body['email'] == 'newuser@example.com'
        assert 'temporaryPassword' in body
        
        # Verify Cognito was called correctly
        mock_cognito.admin_create_user.assert_called_once()
        call_args = mock_cognito.admin_create_user.call_args
        assert call_args[1]['Username'] == 'newuser@example.com'
        
        # Verify custom attributes include tenant_id and role
        user_attrs = call_args[1]['UserAttributes']
        tenant_attr = next(attr for attr in user_attrs if attr['Name'] == 'custom:tenant_id')
        assert tenant_attr['Value'] == 'tenant-123'
        
        role_attr = next(attr for attr in user_attrs if attr['Name'] == 'custom:role')
        assert role_attr['Value'] == 'PROGRAM_MANAGER'
        
        # Verify DynamoDB was called
        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args[1]['Item']
        assert item['PK'] == 'TENANT#tenant-123'
        assert item['SK'].startswith('USER#')
        assert item['email'] == 'newuser@example.com'
        assert item['role'] == 'PROGRAM_MANAGER'
        assert item['tenantId'] == 'tenant-123'
    
    def test_create_user_non_admin_fails(self, non_admin_event, mock_context, mock_env):
        """Test that non-admin users cannot create users."""
        response = create_user(non_admin_event, mock_context)
        
        assert response['statusCode'] == 403
        body = json.loads(response['body'])
        assert body['error']['code'] == 'AUTHORIZATION_FAILED'
    
    @patch('user_management.handler.get_cognito_client')
    def test_create_user_missing_required_fields(self, mock_get_cognito, admin_event, mock_context, mock_env):
        """Test validation of required fields."""
        # Remove required field
        body = json.loads(admin_event['body'])
        del body['email']
        admin_event['body'] = json.dumps(body)
        
        response = create_user(admin_event, mock_context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == 'VALIDATION_ERROR'
    
    @patch('user_management.handler.get_cognito_client')
    def test_create_user_invalid_email(self, mock_get_cognito, admin_event, mock_context, mock_env):
        """Test validation of email format."""
        body = json.loads(admin_event['body'])
        body['email'] = 'invalid-email'
        admin_event['body'] = json.dumps(body)
        
        response = create_user(admin_event, mock_context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == 'VALIDATION_ERROR'
        assert 'email' in body['error']['details'].get('field', '')
    
    @patch('user_management.handler.get_cognito_client')
    def test_create_user_invalid_role(self, mock_get_cognito, admin_event, mock_context, mock_env):
        """Test validation of role."""
        body = json.loads(admin_event['body'])
        body['role'] = 'INVALID_ROLE'
        admin_event['body'] = json.dumps(body)
        
        response = create_user(admin_event, mock_context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == 'VALIDATION_ERROR'
    
    @patch('user_management.handler.get_dynamodb')
    @patch('user_management.handler.get_cognito_client')
    def test_create_user_duplicate_email(self, mock_get_cognito, mock_get_dynamodb, admin_event, mock_context, mock_env):
        """Test handling of duplicate email."""
        # Mock Cognito to raise UsernameExistsException
        mock_cognito = Mock()
        mock_get_cognito.return_value = mock_cognito
        mock_cognito.admin_create_user.side_effect = ClientError(
            {'Error': {'Code': 'UsernameExistsException', 'Message': 'User already exists'}},
            'AdminCreateUser'
        )
        
        response = create_user(admin_event, mock_context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == 'VALIDATION_ERROR'
        assert 'already exists' in body['error']['message']
    
    @patch('user_management.handler.get_dynamodb')
    @patch('user_management.handler.get_cognito_client')
    def test_create_user_dynamodb_failure_rollback(self, mock_get_cognito, mock_get_dynamodb, admin_event, mock_context, mock_env):
        """Test rollback when DynamoDB fails."""
        # Mock Cognito success
        mock_cognito = Mock()
        mock_get_cognito.return_value = mock_cognito
        mock_cognito.admin_create_user.return_value = {
            'User': {'Username': 'newuser@example.com'}
        }
        
        # Mock DynamoDB failure
        mock_dynamodb = Mock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.put_item.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'DynamoDB error'}},
            'PutItem'
        )
        
        response = create_user(admin_event, mock_context)
        
        assert response['statusCode'] == 500
        
        # Verify rollback: Cognito user should be deleted
        mock_cognito.admin_delete_user.assert_called_once()


class TestListUsers:
    """Tests for list_users function."""
    
    @patch('user_management.handler.get_dynamodb')
    def test_list_users_success(self, mock_get_dynamodb, mock_context, mock_env):
        """Test successful user listing."""
        event = {
            'httpMethod': 'GET',
            'path': '/users',
            'requestContext': {
                'authorizer': {
                    'userId': 'admin-user-id',
                    'tenantId': 'tenant-123',
                    'role': 'ADMIN',
                    'email': 'admin@example.com'
                }
            },
            'queryStringParameters': None
        }
        
        # Mock DynamoDB response
        mock_dynamodb = Mock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.query.return_value = {
            'Items': [
                {
                    'userId': 'user-1',
                    'email': 'user1@example.com',
                    'firstName': 'User',
                    'lastName': 'One',
                    'role': 'PROGRAM_MANAGER',
                    'tenantId': 'tenant-123',
                    'createdAt': '2024-01-01T00:00:00Z'
                },
                {
                    'userId': 'user-2',
                    'email': 'user2@example.com',
                    'firstName': 'User',
                    'lastName': 'Two',
                    'role': 'EXECUTIVE',
                    'tenantId': 'tenant-123',
                    'createdAt': '2024-01-02T00:00:00Z',
                    'lastLogin': '2024-01-15T10:30:00Z'
                }
            ]
        }
        
        response = list_users(event, mock_context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'users' in body
        assert len(body['users']) == 2
        assert body['users'][0]['email'] == 'user1@example.com'
        assert body['users'][1]['email'] == 'user2@example.com'
        
        # Verify query was called with correct tenant filter
        call_args = mock_table.query.call_args[1]
        assert ':pk' in call_args['ExpressionAttributeValues']
        assert call_args['ExpressionAttributeValues'][':pk'] == 'TENANT#tenant-123'
    
    @patch('user_management.handler.get_dynamodb')
    def test_list_users_with_pagination(self, mock_get_dynamodb, mock_context, mock_env):
        """Test user listing with pagination."""
        event = {
            'httpMethod': 'GET',
            'path': '/users',
            'requestContext': {
                'authorizer': {
                    'userId': 'admin-user-id',
                    'tenantId': 'tenant-123',
                    'role': 'ADMIN',
                    'email': 'admin@example.com'
                }
            },
            'queryStringParameters': {
                'limit': '10'
            }
        }
        
        # Mock DynamoDB response with pagination
        mock_dynamodb = Mock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.query.return_value = {
            'Items': [
                {
                    'userId': 'user-1',
                    'email': 'user1@example.com',
                    'firstName': 'User',
                    'lastName': 'One',
                    'role': 'PROGRAM_MANAGER',
                    'tenantId': 'tenant-123',
                    'createdAt': '2024-01-01T00:00:00Z'
                }
            ],
            'LastEvaluatedKey': {'PK': 'TENANT#tenant-123', 'SK': 'USER#user-1'}
        }
        
        response = list_users(event, mock_context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'nextToken' in body
        assert len(body['users']) == 1
    
    @patch('user_management.handler.get_dynamodb')
    def test_list_users_tenant_isolation(self, mock_get_dynamodb, mock_context, mock_env):
        """Test that users can only see users from their tenant."""
        event = {
            'httpMethod': 'GET',
            'path': '/users',
            'requestContext': {
                'authorizer': {
                    'userId': 'user-id',
                    'tenantId': 'tenant-123',
                    'role': 'PROGRAM_MANAGER',
                    'email': 'user@example.com'
                }
            },
            'queryStringParameters': None
        }
        
        # Mock DynamoDB response
        mock_dynamodb = Mock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.query.return_value = {'Items': []}
        
        response = list_users(event, mock_context)
        
        # Verify query filters by tenant
        call_args = mock_table.query.call_args[1]
        assert call_args['ExpressionAttributeValues'][':pk'] == 'TENANT#tenant-123'


class TestUpdateUserRole:
    """Tests for update_user_role function."""
    
    @patch('user_management.handler.get_dynamodb')
    @patch('user_management.handler.get_cognito_client')
    def test_update_user_role_success(self, mock_get_cognito, mock_get_dynamodb, mock_context, mock_env):
        """Test successful role update."""
        user_id = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
        event = {
            'httpMethod': 'PUT',
            'path': f'/users/{user_id}/role',
            'pathParameters': {
                'userId': user_id
            },
            'requestContext': {
                'authorizer': {
                    'userId': 'admin-user-id',
                    'tenantId': 'tenant-123',
                    'role': 'ADMIN',
                    'email': 'admin@example.com'
                }
            },
            'body': json.dumps({
                'role': 'EXECUTIVE'
            })
        }
        
        # Mock DynamoDB get_item
        mock_dynamodb = Mock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.return_value = {
            'Item': {
                'userId': user_id,
                'email': 'user@example.com',
                'cognitoUserId': 'cognito-user-123',
                'role': 'PROGRAM_MANAGER',
                'tenantId': 'tenant-123'
            }
        }
        mock_table.update_item.return_value = {}
        
        # Mock Cognito
        mock_cognito = Mock()
        mock_get_cognito.return_value = mock_cognito
        mock_cognito.admin_update_user_attributes.return_value = {}
        
        response = update_user_role(event, mock_context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['userId'] == user_id
        assert body['role'] == 'EXECUTIVE'
        
        # Verify Cognito was updated
        mock_cognito.admin_update_user_attributes.assert_called_once()
        call_args = mock_cognito.admin_update_user_attributes.call_args[1]
        role_attr = call_args['UserAttributes'][0]
        assert role_attr['Name'] == 'custom:role'
        assert role_attr['Value'] == 'EXECUTIVE'
        
        # Verify DynamoDB was updated
        mock_table.update_item.assert_called_once()
    
    def test_update_user_role_non_admin_fails(self, mock_context, mock_env):
        """Test that non-admin users cannot update roles."""
        user_id = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
        event = {
            'httpMethod': 'PUT',
            'path': f'/users/{user_id}/role',
            'pathParameters': {
                'userId': user_id
            },
            'requestContext': {
                'authorizer': {
                    'userId': 'user-id',
                    'tenantId': 'tenant-123',
                    'role': 'PROGRAM_MANAGER',
                    'email': 'user@example.com'
                }
            },
            'body': json.dumps({
                'role': 'EXECUTIVE'
            })
        }
        
        response = update_user_role(event, mock_context)
        
        assert response['statusCode'] == 403
        body = json.loads(response['body'])
        assert body['error']['code'] == 'AUTHORIZATION_FAILED'
    
    @patch('user_management.handler.get_dynamodb')
    def test_update_user_role_invalid_role(self, mock_get_dynamodb, mock_context, mock_env):
        """Test validation of role."""
        user_id = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
        event = {
            'httpMethod': 'PUT',
            'path': f'/users/{user_id}/role',
            'pathParameters': {
                'userId': user_id
            },
            'requestContext': {
                'authorizer': {
                    'userId': 'admin-user-id',
                    'tenantId': 'tenant-123',
                    'role': 'ADMIN',
                    'email': 'admin@example.com'
                }
            },
            'body': json.dumps({
                'role': 'INVALID_ROLE'
            })
        }
        
        response = update_user_role(event, mock_context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == 'VALIDATION_ERROR'
    
    @patch('user_management.handler.get_dynamodb')
    def test_update_user_role_user_not_found(self, mock_get_dynamodb, mock_context, mock_env):
        """Test handling of non-existent user."""
        user_id = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
        event = {
            'httpMethod': 'PUT',
            'path': f'/users/{user_id}/role',
            'pathParameters': {
                'userId': user_id
            },
            'requestContext': {
                'authorizer': {
                    'userId': 'admin-user-id',
                    'tenantId': 'tenant-123',
                    'role': 'ADMIN',
                    'email': 'admin@example.com'
                }
            },
            'body': json.dumps({
                'role': 'EXECUTIVE'
            })
        }
        
        # Mock DynamoDB to return no item
        mock_dynamodb = Mock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.return_value = {}
        
        response = update_user_role(event, mock_context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'not found' in body['error']['message']
    
    @patch('user_management.handler.get_dynamodb')
    def test_update_user_role_tenant_isolation(self, mock_get_dynamodb, mock_context, mock_env):
        """Test that users can only update roles within their tenant."""
        user_id = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
        event = {
            'httpMethod': 'PUT',
            'path': f'/users/{user_id}/role',
            'pathParameters': {
                'userId': user_id
            },
            'requestContext': {
                'authorizer': {
                    'userId': 'admin-user-id',
                    'tenantId': 'tenant-123',
                    'role': 'ADMIN',
                    'email': 'admin@example.com'
                }
            },
            'body': json.dumps({
                'role': 'EXECUTIVE'
            })
        }
        
        # Mock DynamoDB to return no item (user in different tenant)
        mock_dynamodb = Mock()
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.return_value = {}
        
        response = update_user_role(event, mock_context)
        
        # Should fail because user not found in this tenant
        assert response['statusCode'] == 400
        
        # Verify get_item was called with correct tenant filter
        call_args = mock_table.get_item.call_args[1]
        assert call_args['Key']['PK'] == 'TENANT#tenant-123'


class TestGenerateTemporaryPassword:
    """Tests for generate_temporary_password function."""
    
    def test_password_length(self):
        """Test that password has correct length."""
        password = generate_temporary_password()
        assert len(password) == 12
    
    def test_password_complexity(self):
        """Test that password meets complexity requirements."""
        password = generate_temporary_password()
        
        # Check for uppercase
        assert any(c.isupper() for c in password)
        
        # Check for lowercase
        assert any(c.islower() for c in password)
        
        # Check for digit
        assert any(c.isdigit() for c in password)
        
        # Check for special character
        assert any(c in "!@#$%^&*" for c in password)
    
    def test_password_uniqueness(self):
        """Test that generated passwords are unique."""
        passwords = [generate_temporary_password() for _ in range(10)]
        assert len(set(passwords)) == 10  # All should be unique
