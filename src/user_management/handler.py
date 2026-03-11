"""User Management Lambda handler - Create, list, and update users."""

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
import boto3
from botocore.exceptions import ClientError

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from shared.decorators import (
    with_logging,
    with_error_handling,
    with_tenant_isolation,
    with_audit_logging
)
from shared.errors import ValidationError, AuthorizationError, DataError
from shared.validators import validate_email, validate_role, validate_uuid, validate_required_fields
from shared.constants import VALID_ROLES, ROLE_ADMIN
from shared.logger import get_logger

logger = get_logger()

# Environment variables
USERS_TABLE_NAME = os.environ.get('USERS_TABLE_NAME', 'Users')
USER_POOL_ID = os.environ.get('USER_POOL_ID')

# AWS clients (initialized lazily)
_dynamodb = None
_cognito_client = None


def get_dynamodb():
    """Get or create DynamoDB resource."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource('dynamodb')
    return _dynamodb


def get_cognito_client():
    """Get or create Cognito client."""
    global _cognito_client
    if _cognito_client is None:
        _cognito_client = boto3.client('cognito-idp')
    return _cognito_client


@with_logging
@with_error_handling
@with_audit_logging
@with_tenant_isolation
def create_user(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Create a new user in Cognito and DynamoDB.
    
    Validates: 
    - Property 5: Single Tenant Association
    - Property 6: Role Validation
    - Requirements 2.1, 2.2, 2.5
    
    Args:
        event: API Gateway event with user data in body
        context: Lambda context
        
    Returns:
        API Gateway response with created user details
    """
    try:
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        
        # Validate required fields
        validate_required_fields(body, ['email', 'firstName', 'lastName', 'role'])
        
        # Extract and validate fields
        email = validate_email(body['email'])
        first_name = body['firstName'].strip()
        last_name = body['lastName'].strip()
        role = validate_role(body['role'])
        
        # Get tenant_id from auth context (enforced by with_tenant_isolation)
        tenant_id = event['tenant_id']
        
        # Get requester's role from auth context
        authorizer_context = event.get('requestContext', {}).get('authorizer', {})
        requester_role = authorizer_context.get('role')
        
        # Only ADMIN can create users
        if requester_role != ROLE_ADMIN:
            raise AuthorizationError("Only administrators can create users")
        
        # Generate user ID
        user_id = str(uuid.uuid4())
        
        # Generate temporary password
        temp_password = generate_temporary_password()
        
        # Create user in Cognito
        try:
            cognito_client = get_cognito_client()
            cognito_response = cognito_client.admin_create_user(
                UserPoolId=USER_POOL_ID,
                Username=email,
                UserAttributes=[
                    {'Name': 'email', 'Value': email},
                    {'Name': 'email_verified', 'Value': 'true'},
                    {'Name': 'given_name', 'Value': first_name},
                    {'Name': 'family_name', 'Value': last_name},
                    {'Name': 'custom:tenant_id', 'Value': tenant_id},
                    {'Name': 'custom:role', 'Value': role},
                    {'Name': 'custom:user_id', 'Value': user_id}
                ],
                TemporaryPassword=temp_password,
                MessageAction='SUPPRESS'  # Don't send email, return password in response
            )
            
            cognito_user_id = cognito_response['User']['Username']
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'UsernameExistsException':
                raise ValidationError("User with this email already exists", field="email")
            else:
                raise DataError(
                    f"Failed to create user in Cognito: {e.response['Error']['Message']}",
                    data_source="Cognito"
                )
        
        # Store user metadata in DynamoDB
        try:
            dynamodb = get_dynamodb()
            users_table = dynamodb.Table(USERS_TABLE_NAME)
            
            timestamp = datetime.utcnow().isoformat() + 'Z'
            
            user_item = {
                'PK': f"TENANT#{tenant_id}",
                'SK': f"USER#{user_id}",
                'userId': user_id,
                'cognitoUserId': cognito_user_id,
                'email': email,
                'firstName': first_name,
                'lastName': last_name,
                'role': role,
                'tenantId': tenant_id,
                'createdAt': timestamp,
                'GSI1PK': f"EMAIL#{email}",
                'GSI1SK': f"USER#{user_id}"
            }
            
            users_table.put_item(Item=user_item)
            
        except ClientError as e:
            # Rollback: delete user from Cognito
            try:
                cognito_client = get_cognito_client()
                cognito_client.admin_delete_user(
                    UserPoolId=USER_POOL_ID,
                    Username=cognito_user_id
                )
            except Exception:
                logger.error(f"Failed to rollback Cognito user creation for {email}")
            
            raise DataError(
                f"Failed to store user in DynamoDB: {str(e)}",
                data_source="DynamoDB"
            )
        
        logger.info(f"Successfully created user: {user_id} for tenant: {tenant_id}")
        
        # Return response
        return {
            'statusCode': 201,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'userId': user_id,
                'email': email,
                'temporaryPassword': temp_password
            })
        }
        
    except (ValidationError, AuthorizationError, DataError):
        raise
    except Exception as e:
        logger.error(f"Unexpected error in create_user: {str(e)}")
        raise


@with_logging
@with_error_handling
@with_audit_logging
@with_tenant_isolation
def list_users(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    List all users for a tenant.
    
    Validates:
    - Property 1: Tenant Data Isolation
    - Requirement 2.1
    
    Args:
        event: API Gateway event
        context: Lambda context
        
    Returns:
        API Gateway response with list of users
    """
    try:
        # Get tenant_id from auth context (enforced by with_tenant_isolation)
        tenant_id = event['tenant_id']
        
        # Get pagination parameters
        query_params = event.get('queryStringParameters') or {}
        limit = int(query_params.get('limit', 50))
        next_token = query_params.get('nextToken')
        
        # Validate limit
        if limit < 1 or limit > 100:
            raise ValidationError("Limit must be between 1 and 100", field="limit")
        
        # Query DynamoDB for users in this tenant
        dynamodb = get_dynamodb()
        users_table = dynamodb.Table(USERS_TABLE_NAME)
        
        query_params_ddb = {
            'KeyConditionExpression': 'PK = :pk AND begins_with(SK, :sk_prefix)',
            'ExpressionAttributeValues': {
                ':pk': f"TENANT#{tenant_id}",
                ':sk_prefix': 'USER#'
            },
            'Limit': limit
        }
        
        if next_token:
            query_params_ddb['ExclusiveStartKey'] = json.loads(next_token)
        
        response = users_table.query(**query_params_ddb)
        
        # Transform items to user objects
        users = []
        for item in response.get('Items', []):
            users.append({
                'userId': item['userId'],
                'email': item['email'],
                'firstName': item['firstName'],
                'lastName': item['lastName'],
                'role': item['role'],
                'tenantId': item['tenantId'],
                'createdAt': item['createdAt'],
                'lastLogin': item.get('lastLogin')
            })
        
        # Prepare response
        result = {'users': users}
        
        if 'LastEvaluatedKey' in response:
            result['nextToken'] = json.dumps(response['LastEvaluatedKey'])
        
        logger.info(f"Listed {len(users)} users for tenant: {tenant_id}")
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(result)
        }
        
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in list_users: {str(e)}")
        raise


@with_logging
@with_error_handling
@with_audit_logging
@with_tenant_isolation
def update_user_role(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Update a user's role.
    
    Validates:
    - Property 6: Role Validation
    - Property 1: Tenant Data Isolation
    - Requirement 2.5
    
    Args:
        event: API Gateway event with role in body
        context: Lambda context
        
    Returns:
        API Gateway response with updated user details
    """
    try:
        # Get tenant_id from auth context
        tenant_id = event['tenant_id']
        
        # Get requester's role from auth context
        authorizer_context = event.get('requestContext', {}).get('authorizer', {})
        requester_role = authorizer_context.get('role')
        
        # Only ADMIN can update roles
        if requester_role != ROLE_ADMIN:
            raise AuthorizationError("Only administrators can update user roles")
        
        # Get user_id from path parameters
        path_params = event.get('pathParameters', {})
        user_id = validate_uuid(path_params.get('userId'), 'userId')
        
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        validate_required_fields(body, ['role'])
        
        # Validate role
        new_role = validate_role(body['role'])
        
        # Get user from DynamoDB to verify tenant ownership
        dynamodb = get_dynamodb()
        users_table = dynamodb.Table(USERS_TABLE_NAME)
        
        try:
            response = users_table.get_item(
                Key={
                    'PK': f"TENANT#{tenant_id}",
                    'SK': f"USER#{user_id}"
                }
            )
            
            if 'Item' not in response:
                raise ValidationError(f"User not found: {user_id}", field="userId")
            
            user_item = response['Item']
            email = user_item['email']
            cognito_user_id = user_item.get('cognitoUserId', email)
            
        except ClientError as e:
            raise DataError(
                f"Failed to retrieve user from DynamoDB: {str(e)}",
                data_source="DynamoDB"
            )
        
        # Update role in Cognito
        try:
            cognito_client = get_cognito_client()
            cognito_client.admin_update_user_attributes(
                UserPoolId=USER_POOL_ID,
                Username=cognito_user_id,
                UserAttributes=[
                    {'Name': 'custom:role', 'Value': new_role}
                ]
            )
        except ClientError as e:
            raise DataError(
                f"Failed to update user role in Cognito: {e.response['Error']['Message']}",
                data_source="Cognito"
            )
        
        # Update role in DynamoDB
        try:
            timestamp = datetime.utcnow().isoformat() + 'Z'
            
            users_table.update_item(
                Key={
                    'PK': f"TENANT#{tenant_id}",
                    'SK': f"USER#{user_id}"
                },
                UpdateExpression='SET #role = :role, updatedAt = :timestamp',
                ExpressionAttributeNames={
                    '#role': 'role'
                },
                ExpressionAttributeValues={
                    ':role': new_role,
                    ':timestamp': timestamp
                }
            )
        except ClientError as e:
            raise DataError(
                f"Failed to update user role in DynamoDB: {str(e)}",
                data_source="DynamoDB"
            )
        
        logger.info(f"Successfully updated role for user {user_id} to {new_role}")
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'userId': user_id,
                'role': new_role
            })
        }
        
    except (ValidationError, AuthorizationError, DataError):
        raise
    except Exception as e:
        logger.error(f"Unexpected error in update_user_role: {str(e)}")
        raise


def generate_temporary_password() -> str:
    """
    Generate a secure temporary password.
    
    Returns:
        Temporary password string
    """
    import secrets
    import string
    
    # Generate password with uppercase, lowercase, digits, and special characters
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(secrets.choice(alphabet) for _ in range(12))
    
    # Ensure password meets Cognito requirements
    # (at least one uppercase, one lowercase, one digit, one special char)
    if not any(c.isupper() for c in password):
        password = password[:-1] + secrets.choice(string.ascii_uppercase)
    if not any(c.islower() for c in password):
        password = password[:-2] + secrets.choice(string.ascii_lowercase) + password[-1]
    if not any(c.isdigit() for c in password):
        password = password[:-3] + secrets.choice(string.digits) + password[-2:]
    if not any(c in "!@#$%^&*" for c in password):
        password = password[:-4] + secrets.choice("!@#$%^&*") + password[-3:]
    
    return password
