"""Lambda Authorizer for API Gateway - JWT token validation."""

import json
import os
from typing import Dict, Any
import jwt
from jwt import PyJWKClient
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda Authorizer handler for API Gateway.
    
    Validates JWT tokens from AWS Cognito and returns authorization context.
    
    Args:
        event: API Gateway authorizer event containing the authorization token
        context: Lambda context object
        
    Returns:
        IAM policy document with authorization context
    """
    try:
        # Extract token from Authorization header
        token = extract_token(event)
        
        if not token:
            logger.warning("No authorization token provided")
            raise Exception("Unauthorized")
        
        # Validate and decode JWT token
        claims = validate_token(token)
        
        # Extract user information from claims
        user_id = claims.get('sub')
        tenant_id = claims.get('custom:tenant_id')
        role = claims.get('custom:role')
        email = claims.get('email')
        
        # Validate required claims
        if not user_id or not tenant_id or not role:
            logger.error(f"Missing required claims in token: userId={user_id}, tenantId={tenant_id}, role={role}")
            raise Exception("Unauthorized")
        
        logger.info(f"Successfully authenticated user: {user_id}, tenant: {tenant_id}, role: {role}")
        
        # Generate IAM policy
        policy = generate_policy(
            principal_id=user_id,
            effect="Allow",
            resource=event['methodArn'],
            context={
                'userId': user_id,
                'tenantId': tenant_id,
                'role': role,
                'email': email or ''
            }
        )
        
        return policy
        
    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        raise Exception("Unauthorized")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {str(e)}")
        raise Exception("Unauthorized")
    except Exception as e:
        logger.error(f"Authorization error: {str(e)}")
        raise Exception("Unauthorized")


def extract_token(event: Dict[str, Any]) -> str:
    """
    Extract JWT token from Authorization header.
    
    Args:
        event: API Gateway authorizer event
        
    Returns:
        JWT token string
    """
    # Check for Authorization header
    auth_header = event.get('authorizationToken', '')
    
    # Token should be in format: "Bearer <token>"
    if auth_header.startswith('Bearer '):
        return auth_header[7:]
    
    return auth_header


def validate_token(token: str) -> Dict[str, Any]:
    """
    Validate JWT token from AWS Cognito.
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded token claims
        
    Raises:
        jwt.InvalidTokenError: If token is invalid or expired
    """
    # Get Cognito configuration from environment variables
    region = os.environ.get('AWS_REGION', 'us-east-1')
    user_pool_id = os.environ.get('USER_POOL_ID')
    
    if not user_pool_id:
        raise ValueError("USER_POOL_ID environment variable not set")
    
    # Construct JWKS URL for Cognito
    jwks_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json"
    
    # Create JWKS client
    jwks_client = PyJWKClient(jwks_url)
    
    # Get signing key from token
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    
    # Decode and validate token
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        options={
            "verify_signature": True,
            "verify_exp": True,
            "verify_aud": False  # Cognito access tokens don't have aud claim
        }
    )
    
    return claims


def generate_policy(
    principal_id: str,
    effect: str,
    resource: str,
    context: Dict[str, str]
) -> Dict[str, Any]:
    """
    Generate IAM policy document for API Gateway.
    
    Args:
        principal_id: User identifier
        effect: "Allow" or "Deny"
        resource: API Gateway method ARN
        context: Authorization context to pass to downstream Lambda functions
        
    Returns:
        IAM policy document
    """
    # Build the policy document
    policy = {
        'principalId': principal_id,
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Action': 'execute-api:Invoke',
                    'Effect': effect,
                    'Resource': resource
                }
            ]
        },
        'context': context
    }
    
    return policy
