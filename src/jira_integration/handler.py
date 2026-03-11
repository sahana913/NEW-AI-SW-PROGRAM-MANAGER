"""Jira Integration Lambda handler - Configure Jira integration."""

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict
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
from shared.validators import validate_required_fields, validate_url
from shared.constants import (
    ROLE_ADMIN,
    ROLE_PROGRAM_MANAGER,
    INTEGRATION_TYPE_JIRA
)
from shared.logger import get_logger

logger = get_logger()

# Environment variables
INTEGRATIONS_TABLE_NAME = os.environ.get('INTEGRATIONS_TABLE_NAME', 'ai-sw-pm-integrations')
SECRETS_MANAGER_PREFIX = os.environ.get('SECRETS_MANAGER_PREFIX', 'ai-sw-pm')

# AWS clients (initialized lazily)
_dynamodb = None
_secrets_manager = None


def get_dynamodb():
    """Get or create DynamoDB resource."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource('dynamodb')
    return _dynamodb


def get_secrets_manager():
    """Get or create Secrets Manager client."""
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = boto3.client('secretsmanager')
    return _secrets_manager


@with_logging
@with_error_handling
@with_audit_logging
@with_tenant_isolation
def configure_jira_integration(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Configure Jira integration for a tenant.
    
    Stores encrypted credentials in AWS Secrets Manager and
    integration configuration in DynamoDB Integrations table.
    
    Validates:
    - Requirement 3.1: Authenticate with Jira API using OAuth 2.0 or API tokens
    
    Args:
        event: API Gateway event with integration configuration in body
        context: Lambda context
        
    Returns:
        API Gateway response with integration ID and status
    """
    try:
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        
        # Validate required fields
        validate_required_fields(body, [
            'jiraUrl',
            'authType',
            'credentials',
            'projectKeys',
            'syncSchedule'
        ])
        
        # Extract and validate fields
        jira_url = validate_url(body['jiraUrl'], 'jiraUrl')
        auth_type = body['authType'].upper()
        credentials = body['credentials']
        project_keys = body['projectKeys']
        sync_schedule = body['syncSchedule']
        
        # Validate auth type
        if auth_type not in ['OAUTH', 'API_TOKEN']:
            raise ValidationError(
                "authType must be either 'OAUTH' or 'API_TOKEN'",
                field="authType"
            )
        
        # Validate credentials based on auth type
        if auth_type == 'API_TOKEN':
            validate_required_fields(credentials, ['apiToken'], parent_field='credentials')
        elif auth_type == 'OAUTH':
            validate_required_fields(
                credentials,
                ['oauthClientId', 'oauthClientSecret'],
                parent_field='credentials'
            )
        
        # Validate project keys
        if not isinstance(project_keys, list) or len(project_keys) == 0:
            raise ValidationError(
                "projectKeys must be a non-empty array",
                field="projectKeys"
            )
        
        # Validate sync schedule (basic cron validation)
        if not isinstance(sync_schedule, str) or len(sync_schedule.strip()) == 0:
            raise ValidationError(
                "syncSchedule must be a non-empty string (cron expression)",
                field="syncSchedule"
            )
        
        # Get tenant_id from auth context (enforced by with_tenant_isolation)
        tenant_id = event['tenant_id']
        
        # Get requester's role from auth context
        authorizer_context = event.get('requestContext', {}).get('authorizer', {})
        requester_role = authorizer_context.get('role')
        
        # Only ADMIN and PROGRAM_MANAGER can configure integrations
        if requester_role not in [ROLE_ADMIN, ROLE_PROGRAM_MANAGER]:
            raise AuthorizationError(
                "Only administrators and program managers can configure integrations"
            )
        
        # Generate integration ID
        integration_id = str(uuid.uuid4())
        
        # Store credentials in AWS Secrets Manager
        secret_name = f"{SECRETS_MANAGER_PREFIX}/jira/{tenant_id}/{integration_id}"
        
        try:
            secrets_manager = get_secrets_manager()
            
            # Prepare secret value
            secret_value = {
                'jiraUrl': jira_url,
                'authType': auth_type,
                'credentials': credentials
            }
            
            secrets_manager.create_secret(
                Name=secret_name,
                Description=f"Jira integration credentials for tenant {tenant_id}",
                SecretString=json.dumps(secret_value),
                Tags=[
                    {'Key': 'TenantId', 'Value': tenant_id},
                    {'Key': 'IntegrationType', 'Value': INTEGRATION_TYPE_JIRA},
                    {'Key': 'IntegrationId', 'Value': integration_id}
                ]
            )
            
            logger.info(f"Created secret in Secrets Manager: {secret_name}")
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceExistsException':
                raise ValidationError(
                    "Integration with these credentials already exists",
                    field="credentials"
                )
            else:
                raise DataError(
                    f"Failed to store credentials in Secrets Manager: {e.response['Error']['Message']}",
                    data_source="SecretsManager"
                )
        
        # Store integration configuration in DynamoDB
        try:
            dynamodb = get_dynamodb()
            integrations_table = dynamodb.Table(INTEGRATIONS_TABLE_NAME)
            
            timestamp = datetime.utcnow().isoformat() + 'Z'
            
            integration_item = {
                'PK': f"TENANT#{tenant_id}",
                'SK': f"INTEGRATION#{integration_id}",
                'integrationId': integration_id,
                'tenantId': tenant_id,
                'integrationType': INTEGRATION_TYPE_JIRA,
                'configuration': {
                    'jiraUrl': jira_url,
                    'authType': auth_type,
                    'projectKeys': project_keys,
                    'syncSchedule': sync_schedule,
                    'secretName': secret_name
                },
                'status': 'ACTIVE',
                'createdAt': timestamp,
                'lastSyncAt': None,
                'nextSyncAt': None
            }
            
            integrations_table.put_item(Item=integration_item)
            
            logger.info(f"Stored integration configuration in DynamoDB: {integration_id}")
            
        except ClientError as e:
            # Rollback: delete secret from Secrets Manager
            try:
                secrets_manager = get_secrets_manager()
                secrets_manager.delete_secret(
                    SecretId=secret_name,
                    ForceDeleteWithoutRecovery=True
                )
                logger.info(f"Rolled back secret deletion: {secret_name}")
            except Exception as rollback_error:
                logger.error(
                    f"Failed to rollback secret creation for {secret_name}: {str(rollback_error)}"
                )
            
            raise DataError(
                f"Failed to store integration configuration in DynamoDB: {str(e)}",
                data_source="DynamoDB"
            )
        
        logger.info(
            f"Successfully configured Jira integration: {integration_id} for tenant: {tenant_id}"
        )
        
        # Return response
        return {
            'statusCode': 201,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'integrationId': integration_id,
                'status': 'ACTIVE'
            })
        }
        
    except (ValidationError, AuthorizationError, DataError):
        raise
    except Exception as e:
        logger.error(f"Unexpected error in configure_jira_integration: {str(e)}")
        raise
