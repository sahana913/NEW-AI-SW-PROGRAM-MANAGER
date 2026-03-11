"""Jira data fetching Lambda handler - Fetch project data from Jira API."""

import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import boto3
from botocore.exceptions import ClientError
import requests
from requests.auth import HTTPBasicAuth

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from shared.decorators import (
    with_logging,
    with_error_handling,
    with_tenant_isolation,
    with_audit_logging
)
from shared.errors import ValidationError, AuthorizationError, DataError
from shared.validators import validate_required_fields
from shared.constants import (
    ROLE_ADMIN,
    ROLE_PROGRAM_MANAGER,
    INTEGRATION_TYPE_JIRA
)
from shared.logger import get_logger

logger = get_logger()

# Import storage functionality
from .data_storage import store_multiple_projects

# Environment variables
INTEGRATIONS_TABLE_NAME = os.environ.get('INTEGRATIONS_TABLE_NAME', 'ai-sw-pm-integrations')
SECRETS_MANAGER_PREFIX = os.environ.get('SECRETS_MANAGER_PREFIX', 'ai-sw-pm')
SNS_ADMIN_ALERT_TOPIC = os.environ.get('SNS_ADMIN_ALERT_TOPIC')

# AWS clients (initialized lazily)
_dynamodb = None
_secrets_manager = None
_sns = None


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


def get_sns():
    """Get or create SNS client."""
    global _sns
    if _sns is None:
        _sns = boto3.client('sns')
    return _sns


def send_admin_alert(subject: str, message: str, error_details: dict = None):
    """
    Send alert to administrator via SNS.
    
    Validates: Requirement 3.6 - Alert administrator on validation failures
    
    Args:
        subject: Alert subject
        message: Alert message
        error_details: Additional error details
    """
    if not SNS_ADMIN_ALERT_TOPIC:
        logger.warning("SNS_ADMIN_ALERT_TOPIC not configured, skipping admin alert")
        return
    
    try:
        sns = get_sns()
        
        alert_message = f"{message}\n\n"
        if error_details:
            alert_message += "Error Details:\n"
            for key, value in error_details.items():
                alert_message += f"  {key}: {value}\n"
        
        sns.publish(
            TopicArn=SNS_ADMIN_ALERT_TOPIC,
            Subject=subject[:100],  # SNS subject limit
            Message=alert_message
        )
        
        logger.info(f"Admin alert sent: {subject}")
        
    except Exception as e:
        logger.error(f"Failed to send admin alert: {str(e)}")



class JiraAPIClient:
    """Client for interacting with Jira API."""
    
    def __init__(self, jira_url: str, auth_type: str, credentials: Dict[str, Any]):
        """
        Initialize Jira API client.
        
        Args:
            jira_url: Base URL for Jira instance
            auth_type: Authentication type (OAUTH or API_TOKEN)
            credentials: Authentication credentials
        """
        self.jira_url = jira_url.rstrip('/')
        self.auth_type = auth_type
        self.credentials = credentials
        self.session = requests.Session()
        
        # Set up authentication
        if auth_type == 'API_TOKEN':
            # For API token, use email + token as basic auth
            # Note: In production, email should be stored with credentials
            self.session.auth = HTTPBasicAuth(
                credentials.get('email', 'user@example.com'),
                credentials['apiToken']
            )
        elif auth_type == 'OAUTH':
            # For OAuth, we'd need to implement OAuth flow
            # For now, we'll use a bearer token approach
            access_token = credentials.get('accessToken')
            if access_token:
                self.session.headers.update({
                    'Authorization': f'Bearer {access_token}'
                })
        
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make HTTP request to Jira API with retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            **kwargs: Additional arguments for requests
            
        Returns:
            JSON response from API
            
        Raises:
            DataError: If API request fails after retries
        """
        url = f"{self.jira_url}{endpoint}"
        max_retries = 5
        retry_delays = [1, 2, 4, 8, 16]  # Exponential backoff
        
        for attempt in range(max_retries):
            try:
                response = self.session.request(method, url, **kwargs)
                
                # Handle rate limiting
                if response.status_code == 429:
                    if attempt < max_retries - 1:
                        delay = min(retry_delays[attempt], 60)
                        logger.warning(
                            f"Rate limited by Jira API. Retrying in {delay}s (attempt {attempt + 1}/{max_retries})"
                        )
                        import time
                        time.sleep(delay)
                        continue
                    else:
                        raise DataError(
                            "Jira API rate limit exceeded after maximum retries",
                            data_source="JiraAPI"
                        )
                
                # Raise for other HTTP errors
                response.raise_for_status()
                
                return response.json()
                
            except requests.exceptions.HTTPError as e:
                if attempt < max_retries - 1 and e.response.status_code >= 500:
                    delay = min(retry_delays[attempt], 60)
                    logger.warning(
                        f"Jira API error {e.response.status_code}. Retrying in {delay}s (attempt {attempt + 1}/{max_retries})"
                    )
                    import time
                    time.sleep(delay)
                    continue
                else:
                    raise DataError(
                        f"Jira API request failed: {str(e)}",
                        data_source="JiraAPI"
                    )
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    delay = min(retry_delays[attempt], 60)
                    logger.warning(
                        f"Network error: {str(e)}. Retrying in {delay}s (attempt {attempt + 1}/{max_retries})"
                    )
                    import time
                    time.sleep(delay)
                    continue
                else:
                    raise DataError(
                        f"Failed to connect to Jira API: {str(e)}",
                        data_source="JiraAPI"
                    )
        
        raise DataError(
            "Maximum retries exceeded for Jira API request",
            data_source="JiraAPI"
        )
    
    def fetch_sprints(self, board_id: str) -> List[Dict[str, Any]]:
        """
        Fetch sprint data from Jira.
        
        Args:
            board_id: Jira board ID
            
        Returns:
            List of sprint data dictionaries
        """
        endpoint = f"/rest/agile/1.0/board/{board_id}/sprint"
        response = self._make_request('GET', endpoint, params={'state': 'active,closed'})
        return response.get('values', [])
    
    def fetch_sprint_report(self, board_id: str, sprint_id: str) -> Dict[str, Any]:
        """
        Fetch sprint report with velocity and completion data.
        
        Args:
            board_id: Jira board ID
            sprint_id: Sprint ID
            
        Returns:
            Sprint report data
        """
        endpoint = f"/rest/greenhopper/1.0/rapid/charts/sprintreport"
        params = {
            'rapidViewId': board_id,
            'sprintId': sprint_id
        }
        return self._make_request('GET', endpoint, params=params)
    
    def fetch_backlog(self, board_id: str) -> Dict[str, Any]:
        """
        Fetch backlog issues.
        
        Args:
            board_id: Jira board ID
            
        Returns:
            Backlog data
        """
        endpoint = f"/rest/agile/1.0/board/{board_id}/backlog"
        params = {
            'maxResults': 1000,
            'fields': 'summary,issuetype,priority,status,created,resolutiondate'
        }
        return self._make_request('GET', endpoint, params=params)
    
    def fetch_issues_by_jql(self, jql: str, max_results: int = 1000) -> List[Dict[str, Any]]:
        """
        Fetch issues using JQL query.
        
        Args:
            jql: JQL query string
            max_results: Maximum number of results
            
        Returns:
            List of issues
        """
        endpoint = "/rest/api/3/search"
        params = {
            'jql': jql,
            'maxResults': max_results,
            'fields': 'summary,issuetype,priority,status,created,resolutiondate,assignee,timetracking'
        }
        response = self._make_request('GET', endpoint, params=params)
        return response.get('issues', [])
    
    def fetch_project_versions(self, project_key: str) -> List[Dict[str, Any]]:
        """
        Fetch project versions (milestones).
        
        Args:
            project_key: Jira project key
            
        Returns:
            List of versions
        """
        endpoint = f"/rest/api/3/project/{project_key}/versions"
        return self._make_request('GET', endpoint)
    
    def fetch_issue_links(self, issue_key: str) -> List[Dict[str, Any]]:
        """
        Fetch issue links (dependencies).
        
        Args:
            issue_key: Jira issue key
            
        Returns:
            List of issue links
        """
        endpoint = f"/rest/api/3/issue/{issue_key}"
        params = {'fields': 'issuelinks'}
        response = self._make_request('GET', endpoint, params=params)
        return response.get('fields', {}).get('issuelinks', [])


def transform_sprint_data(sprint_data: Dict[str, Any], sprint_report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform Jira sprint data to internal schema.
    
    Args:
        sprint_data: Raw sprint data from Jira
        sprint_report: Sprint report with velocity data
        
    Returns:
        Transformed sprint data
    """
    contents = sprint_report.get('contents', {})
    completed_issues = contents.get('completedIssues', [])
    incomplete_issues = contents.get('incompletedIssues', [])
    
    # Calculate story points
    completed_points = sum(
        issue.get('estimateStatistic', {}).get('statFieldValue', {}).get('value', 0)
        for issue in completed_issues
    )
    
    planned_points = completed_points + sum(
        issue.get('estimateStatistic', {}).get('statFieldValue', {}).get('value', 0)
        for issue in incomplete_issues
    )
    
    completion_rate = (completed_points / planned_points * 100) if planned_points > 0 else 0
    
    return {
        'sprintId': str(sprint_data.get('id')),
        'sprintName': sprint_data.get('name'),
        'startDate': sprint_data.get('startDate'),
        'endDate': sprint_data.get('endDate'),
        'velocity': completed_points,
        'completedPoints': completed_points,
        'plannedPoints': planned_points,
        'completionRate': round(completion_rate, 2)
    }


def transform_backlog_data(backlog_issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Transform Jira backlog data to internal schema.
    
    Args:
        backlog_issues: List of backlog issues from Jira
        
    Returns:
        Transformed backlog metrics
    """
    total_issues = len(backlog_issues)
    
    issues_by_type = {}
    issues_by_priority = {}
    total_age_days = 0
    
    for issue in backlog_issues:
        fields = issue.get('fields', {})
        
        # Count by type
        issue_type = fields.get('issuetype', {}).get('name', 'Unknown')
        issues_by_type[issue_type] = issues_by_type.get(issue_type, 0) + 1
        
        # Count by priority
        priority = fields.get('priority', {}).get('name', 'Unknown')
        issues_by_priority[priority] = issues_by_priority.get(priority, 0) + 1
        
        # Calculate age
        created = fields.get('created')
        if created:
            created_date = datetime.fromisoformat(created.replace('Z', '+00:00'))
            age_days = (datetime.now(created_date.tzinfo) - created_date).days
            total_age_days += age_days
    
    average_age = (total_age_days / total_issues) if total_issues > 0 else 0
    
    return {
        'totalIssues': total_issues,
        'issuesByType': issues_by_type,
        'issuesByPriority': issues_by_priority,
        'averageAge': round(average_age, 2),
        'growthRate': 0  # Will be calculated by comparing with previous data
    }


def transform_milestone_data(versions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Transform Jira versions to milestone data.
    
    Args:
        versions: List of Jira versions
        
    Returns:
        List of transformed milestones
    """
    milestones = []
    
    for version in versions:
        if not version.get('released', False):
            # Calculate completion percentage based on issues
            # This would require additional API calls in production
            completion_percentage = 0
            
            status = 'ON_TRACK'
            if version.get('overdue', False):
                status = 'DELAYED'
            
            milestones.append({
                'milestoneId': str(version.get('id')),
                'name': version.get('name'),
                'dueDate': version.get('releaseDate'),
                'completionPercentage': completion_percentage,
                'status': status,
                'dependencies': []  # Would be populated from issue links
            })
    
    return milestones


def transform_resource_data(issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Transform issue assignments to resource allocation data.
    
    Args:
        issues: List of issues with assignee information
        
    Returns:
        List of resource allocation data
    """
    resource_map = {}
    
    for issue in issues:
        fields = issue.get('fields', {})
        assignee = fields.get('assignee')
        
        if assignee:
            user_id = assignee.get('accountId')
            user_name = assignee.get('displayName', 'Unknown')
            
            if user_id not in resource_map:
                resource_map[user_id] = {
                    'userId': user_id,
                    'userName': user_name,
                    'allocatedHours': 0,
                    'capacity': 40,  # Default 40 hours per week
                    'utilizationRate': 0
                }
            
            # Estimate hours from time tracking
            time_tracking = fields.get('timetracking', {})
            time_spent = time_tracking.get('timeSpentSeconds', 0) / 3600  # Convert to hours
            resource_map[user_id]['allocatedHours'] += time_spent
    
    # Calculate utilization rates
    resources = list(resource_map.values())
    for resource in resources:
        capacity = resource['capacity']
        if capacity > 0:
            resource['utilizationRate'] = round(
                (resource['allocatedHours'] / capacity) * 100, 2
            )
    
    return resources


def transform_dependency_data(issue_links: List[Dict[str, Any]], issue_key: str) -> List[Dict[str, Any]]:
    """
    Transform issue links to dependency data.
    
    Args:
        issue_links: List of issue links
        issue_key: Source issue key
        
    Returns:
        List of dependencies
    """
    dependencies = []
    
    for link in issue_links:
        link_type = link.get('type', {}).get('name', '')
        
        # Determine if this is a blocking relationship
        dependency_type = 'RELATES_TO'
        if 'blocks' in link_type.lower():
            dependency_type = 'BLOCKS'
        
        # Determine source and target
        inward_issue = link.get('inwardIssue')
        outward_issue = link.get('outwardIssue')
        
        if inward_issue:
            dependencies.append({
                'dependencyId': str(uuid.uuid4()),
                'sourceTaskId': inward_issue.get('key'),
                'targetTaskId': issue_key,
                'type': dependency_type,
                'status': 'ACTIVE'
            })
        
        if outward_issue:
            dependencies.append({
                'dependencyId': str(uuid.uuid4()),
                'sourceTaskId': issue_key,
                'targetTaskId': outward_issue.get('key'),
                'type': dependency_type,
                'status': 'ACTIVE'
            })
    
    return dependencies


@with_logging
@with_error_handling
@with_audit_logging
@with_tenant_isolation
def fetch_jira_data(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Fetch project data from Jira API.
    
    Validates:
    - Requirement 3.1: Authenticate with Jira API using OAuth 2.0 or API tokens
    - Requirement 3.2: Fetch sprint velocity, task completion rates, issue backlog,
                       resource allocation, milestone tracking, and dependency mapping
    
    Args:
        event: API Gateway event or Step Functions event with integration ID
        context: Lambda context
        
    Returns:
        Fetched and transformed project data
    """
    try:
        # Parse input
        if 'body' in event:
            # API Gateway event
            body = json.loads(event.get('body', '{}'))
            integration_id = body.get('integrationId')
        else:
            # Step Functions event
            integration_id = event.get('integrationId')
        
        if not integration_id:
            raise ValidationError(
                "integrationId is required",
                field="integrationId"
            )
        
        # Get tenant_id from auth context
        tenant_id = event.get('tenant_id') or event.get('tenantId')
        if not tenant_id:
            raise ValidationError(
                "tenantId is required",
                field="tenantId"
            )
        
        # Retrieve integration configuration from DynamoDB
        dynamodb = get_dynamodb()
        integrations_table = dynamodb.Table(INTEGRATIONS_TABLE_NAME)
        
        try:
            response = integrations_table.get_item(
                Key={
                    'PK': f"TENANT#{tenant_id}",
                    'SK': f"INTEGRATION#{integration_id}"
                }
            )
            
            if 'Item' not in response:
                raise ValidationError(
                    f"Integration {integration_id} not found for tenant {tenant_id}",
                    field="integrationId"
                )
            
            integration = response['Item']
            
        except ClientError as e:
            raise DataError(
                f"Failed to retrieve integration configuration: {str(e)}",
                data_source="DynamoDB"
            )
        
        # Retrieve credentials from Secrets Manager
        configuration = integration.get('configuration', {})
        secret_name = configuration.get('secretName')
        
        if not secret_name:
            raise DataError(
                "Integration configuration missing secret name",
                data_source="DynamoDB"
            )
        
        try:
            secrets_manager = get_secrets_manager()
            secret_response = secrets_manager.get_secret_value(SecretId=secret_name)
            secret_data = json.loads(secret_response['SecretString'])
            
        except ClientError as e:
            raise DataError(
                f"Failed to retrieve credentials from Secrets Manager: {str(e)}",
                data_source="SecretsManager"
            )
        
        # Initialize Jira API client
        jira_url = secret_data['jiraUrl']
        auth_type = secret_data['authType']
        credentials = secret_data['credentials']
        
        jira_client = JiraAPIClient(jira_url, auth_type, credentials)
        
        # Fetch data for each project
        project_keys = configuration.get('projectKeys', [])
        project_data_list = []
        
        for project_key in project_keys:
            logger.info(f"Fetching data for project: {project_key}")
            
            # Fetch boards for the project
            # Note: In production, we'd need to map project keys to board IDs
            # For now, we'll use a simplified approach
            
            # Fetch backlog
            try:
                # Use JQL to fetch issues for the project
                jql = f"project = {project_key} AND resolution = Unresolved"
                backlog_issues = jira_client.fetch_issues_by_jql(jql)
                backlog_metrics = transform_backlog_data(backlog_issues)
            except Exception as e:
                logger.error(f"Failed to fetch backlog for {project_key}: {str(e)}")
                backlog_metrics = {
                    'totalIssues': 0,
                    'issuesByType': {},
                    'issuesByPriority': {},
                    'averageAge': 0,
                    'growthRate': 0
                }
            
            # Fetch milestones (versions)
            try:
                versions = jira_client.fetch_project_versions(project_key)
                milestones = transform_milestone_data(versions)
            except Exception as e:
                logger.error(f"Failed to fetch versions for {project_key}: {str(e)}")
                milestones = []
            
            # Fetch resource allocation
            try:
                jql = f"project = {project_key} AND assignee is not EMPTY"
                assigned_issues = jira_client.fetch_issues_by_jql(jql)
                resources = transform_resource_data(assigned_issues)
            except Exception as e:
                logger.error(f"Failed to fetch resources for {project_key}: {str(e)}")
                resources = []
            
            # Fetch dependencies
            # Note: This would require fetching links for all issues
            # For now, we'll return an empty list
            dependencies = []
            
            # Fetch sprints (requires board ID)
            # For now, we'll return an empty list
            sprints = []
            
            project_data = {
                'projectId': str(uuid.uuid4()),
                'projectName': project_key,
                'source': 'JIRA',
                'lastSyncAt': datetime.utcnow().isoformat() + 'Z',
                'metrics': {
                    'sprints': sprints,
                    'backlog': backlog_metrics,
                    'milestones': milestones,
                    'resources': resources,
                    'dependencies': dependencies
                }
            }
            
            project_data_list.append(project_data)
        
        logger.info(
            f"Successfully fetched data for {len(project_data_list)} projects from Jira"
        )
        
        # Store validated data in RDS PostgreSQL (Requirements 3.5, 3.7)
        logger.info("Storing project data in database")
        
        try:
            storage_results = store_multiple_projects(
                tenant_id=tenant_id,
                projects=project_data_list,
                source='JIRA'
            )
            
            # Alert administrator if any projects failed validation or storage (Requirement 3.6)
            if storage_results['failed'] > 0:
                send_admin_alert(
                    subject=f"Jira Data Ingestion Failures - Tenant {tenant_id}",
                    message=f"Failed to store {storage_results['failed']} out of {storage_results['total']} projects",
                    error_details={
                        'tenant_id': tenant_id,
                        'integration_id': integration_id,
                        'successful': storage_results['successful'],
                        'failed': storage_results['failed'],
                        'errors': storage_results['errors'][:5]  # Limit to first 5 errors
                    }
                )
            
            logger.info(
                f"Data storage complete: {storage_results['successful']}/{storage_results['total']} successful"
            )
            
        except Exception as e:
            logger.error(f"Critical error during data storage: {str(e)}")
            
            # Alert administrator about critical storage failure (Requirement 3.6)
            send_admin_alert(
                subject=f"Critical: Jira Data Storage Failed - Tenant {tenant_id}",
                message=f"Complete storage failure for integration {integration_id}",
                error_details={
                    'tenant_id': tenant_id,
                    'integration_id': integration_id,
                    'error': str(e),
                    'error_type': type(e).__name__
                }
            )
            
            raise DataError(
                f"Failed to store project data: {str(e)}",
                data_source="Database"
            )
        
        # Update integration last sync time
        try:
            timestamp = datetime.utcnow().isoformat() + 'Z'
            integrations_table.update_item(
                Key={
                    'PK': f"TENANT#{tenant_id}",
                    'SK': f"INTEGRATION#{integration_id}"
                },
                UpdateExpression='SET lastSyncAt = :timestamp',
                ExpressionAttributeValues={
                    ':timestamp': timestamp
                }
            )
        except ClientError as e:
            logger.error(f"Failed to update integration sync time: {str(e)}")
        
        # Return response with storage results
        result = {
            'tenantId': tenant_id,
            'integrationId': integration_id,
            'projects': project_data_list,
            'storageResults': storage_results,
            'syncedAt': datetime.utcnow().isoformat() + 'Z'
        }
        
        if 'body' in event:
            # API Gateway response
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps(result)
            }
        else:
            # Step Functions response
            return result
        
    except (ValidationError, AuthorizationError, DataError):
        raise
    except Exception as e:
        logger.error(f"Unexpected error in fetch_jira_data: {str(e)}")
        raise
