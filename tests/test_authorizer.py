"""Unit tests for Lambda Authorizer."""

import pytest
import json
import jwt
import time
from unittest.mock import patch, MagicMock
from src.authorizer.handler import (
    lambda_handler,
    extract_token,
    validate_token,
    generate_policy
)


class TestExtractToken:
    """Tests for token extraction from Authorization header."""
    
    def test_extract_bearer_token(self):
        """Test extracting token with Bearer prefix."""
        event = {
            'authorizationToken': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9'
        }
        token = extract_token(event)
        assert token == 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9'
    
    def test_extract_token_without_bearer(self):
        """Test extracting token without Bearer prefix."""
        event = {
            'authorizationToken': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9'
        }
        token = extract_token(event)
        assert token == 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9'
    
    def test_extract_empty_token(self):
        """Test extracting empty token."""
        event = {
            'authorizationToken': ''
        }
        token = extract_token(event)
        assert token == ''
    
    def test_extract_missing_token(self):
        """Test extracting when token is missing."""
        event = {}
        token = extract_token(event)
        assert token == ''


class TestGeneratePolicy:
    """Tests for IAM policy generation."""
    
    def test_generate_allow_policy(self):
        """Test generating Allow policy."""
        policy = generate_policy(
            principal_id='user123',
            effect='Allow',
            resource='arn:aws:execute-api:us-east-1:123456789012:abcdef/prod/GET/users',
            context={
                'userId': 'user123',
                'tenantId': 'tenant456',
                'role': 'PROGRAM_MANAGER',
                'email': 'user@example.com'
            }
        )
        
        assert policy['principalId'] == 'user123'
        assert policy['policyDocument']['Version'] == '2012-10-17'
        assert len(policy['policyDocument']['Statement']) == 1
        
        statement = policy['policyDocument']['Statement'][0]
        assert statement['Action'] == 'execute-api:Invoke'
        assert statement['Effect'] == 'Allow'
        assert statement['Resource'] == 'arn:aws:execute-api:us-east-1:123456789012:abcdef/prod/GET/users'
        
        assert policy['context']['userId'] == 'user123'
        assert policy['context']['tenantId'] == 'tenant456'
        assert policy['context']['role'] == 'PROGRAM_MANAGER'
        assert policy['context']['email'] == 'user@example.com'
    
    def test_generate_deny_policy(self):
        """Test generating Deny policy."""
        policy = generate_policy(
            principal_id='user123',
            effect='Deny',
            resource='arn:aws:execute-api:us-east-1:123456789012:abcdef/prod/GET/users',
            context={}
        )
        
        statement = policy['policyDocument']['Statement'][0]
        assert statement['Effect'] == 'Deny'


class TestValidateToken:
    """Tests for JWT token validation."""
    
    @patch.dict('os.environ', {'USER_POOL_ID': 'us-east-1_ABC123', 'AWS_REGION': 'us-east-1'})
    @patch('src.authorizer.handler.PyJWKClient')
    @patch('src.authorizer.handler.jwt.decode')
    def test_validate_valid_token(self, mock_jwt_decode, mock_jwks_client):
        """Test validating a valid token."""
        # Mock JWKS client
        mock_signing_key = MagicMock()
        mock_signing_key.key = 'mock_key'
        mock_client_instance = MagicMock()
        mock_client_instance.get_signing_key_from_jwt.return_value = mock_signing_key
        mock_jwks_client.return_value = mock_client_instance
        
        # Mock JWT decode
        expected_claims = {
            'sub': 'user123',
            'custom:tenant_id': 'tenant456',
            'custom:role': 'PROGRAM_MANAGER',
            'email': 'user@example.com',
            'exp': int(time.time()) + 3600
        }
        mock_jwt_decode.return_value = expected_claims
        
        # Validate token
        token = 'valid.jwt.token'
        claims = validate_token(token)
        
        assert claims == expected_claims
        mock_jwks_client.assert_called_once()
        mock_jwt_decode.assert_called_once()
    
    @patch.dict('os.environ', {})
    def test_validate_token_missing_user_pool_id(self):
        """Test validation fails when USER_POOL_ID is not set."""
        with pytest.raises(ValueError, match="USER_POOL_ID environment variable not set"):
            validate_token('some.jwt.token')


class TestLambdaHandler:
    """Tests for the main Lambda handler."""
    
    @patch('src.authorizer.handler.validate_token')
    def test_successful_authorization(self, mock_validate_token):
        """Test successful authorization with valid token."""
        # Mock token validation
        mock_validate_token.return_value = {
            'sub': 'user123',
            'custom:tenant_id': 'tenant456',
            'custom:role': 'PROGRAM_MANAGER',
            'email': 'user@example.com'
        }
        
        # Create event
        event = {
            'authorizationToken': 'Bearer valid.jwt.token',
            'methodArn': 'arn:aws:execute-api:us-east-1:123456789012:abcdef/prod/GET/users'
        }
        
        # Call handler
        result = lambda_handler(event, None)
        
        # Verify result
        assert result['principalId'] == 'user123'
        assert result['policyDocument']['Statement'][0]['Effect'] == 'Allow'
        assert result['context']['userId'] == 'user123'
        assert result['context']['tenantId'] == 'tenant456'
        assert result['context']['role'] == 'PROGRAM_MANAGER'
        assert result['context']['email'] == 'user@example.com'
    
    def test_missing_authorization_token(self):
        """Test authorization fails when token is missing."""
        event = {
            'methodArn': 'arn:aws:execute-api:us-east-1:123456789012:abcdef/prod/GET/users'
        }
        
        with pytest.raises(Exception, match="Unauthorized"):
            lambda_handler(event, None)
    
    @patch('src.authorizer.handler.validate_token')
    def test_missing_required_claims(self, mock_validate_token):
        """Test authorization fails when required claims are missing."""
        # Mock token validation with missing tenant_id
        mock_validate_token.return_value = {
            'sub': 'user123',
            'custom:role': 'PROGRAM_MANAGER',
            'email': 'user@example.com'
        }
        
        event = {
            'authorizationToken': 'Bearer valid.jwt.token',
            'methodArn': 'arn:aws:execute-api:us-east-1:123456789012:abcdef/prod/GET/users'
        }
        
        with pytest.raises(Exception, match="Unauthorized"):
            lambda_handler(event, None)
    
    @patch('src.authorizer.handler.validate_token')
    def test_expired_token(self, mock_validate_token):
        """Test authorization fails with expired token."""
        # Mock token validation to raise ExpiredSignatureError
        mock_validate_token.side_effect = jwt.ExpiredSignatureError("Token has expired")
        
        event = {
            'authorizationToken': 'Bearer expired.jwt.token',
            'methodArn': 'arn:aws:execute-api:us-east-1:123456789012:abcdef/prod/GET/users'
        }
        
        with pytest.raises(Exception, match="Unauthorized"):
            lambda_handler(event, None)
    
    @patch('src.authorizer.handler.validate_token')
    def test_invalid_token(self, mock_validate_token):
        """Test authorization fails with invalid token."""
        # Mock token validation to raise InvalidTokenError
        mock_validate_token.side_effect = jwt.InvalidTokenError("Invalid token")
        
        event = {
            'authorizationToken': 'Bearer invalid.jwt.token',
            'methodArn': 'arn:aws:execute-api:us-east-1:123456789012:abcdef/prod/GET/users'
        }
        
        with pytest.raises(Exception, match="Unauthorized"):
            lambda_handler(event, None)
    
    @patch('src.authorizer.handler.validate_token')
    def test_authorization_with_missing_email(self, mock_validate_token):
        """Test authorization succeeds even when email is missing."""
        # Mock token validation without email
        mock_validate_token.return_value = {
            'sub': 'user123',
            'custom:tenant_id': 'tenant456',
            'custom:role': 'PROGRAM_MANAGER'
        }
        
        event = {
            'authorizationToken': 'Bearer valid.jwt.token',
            'methodArn': 'arn:aws:execute-api:us-east-1:123456789012:abcdef/prod/GET/users'
        }
        
        result = lambda_handler(event, None)
        
        assert result['context']['email'] == ''
        assert result['context']['userId'] == 'user123'
