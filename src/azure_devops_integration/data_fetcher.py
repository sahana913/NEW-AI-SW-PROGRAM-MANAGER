"""Azure DevOps data fetching Lambda handler - Fetch project data from Azure DevOps API."""

from jira_integration.data_storage import store_multiple_projects
from shared.logger import get_logger
from shared.errors import AuthorizationError, DataError, ValidationError
from shared.decorators import (
    with_audit_logging,
    with_error_handling,
    with_logging,
    with_tenant_isolation,
)
from shared.constants import (
    INTEGRATION_TYPE_AZURE_DEVOPS,
    ROLE_ADMIN,
    ROLE_PROGRAM_MANAGER,
)
import base64
import json
import os
import sys
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import boto3
import requests
from botocore.exceptions import ClientError

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))


logger = get_logger()

# Import storage functionality

# Environment variables
INTEGRATIONS_TABLE_NAME = os.environ.get(
    "INTEGRATIONS_TABLE_NAME", "ai-sw-pm-integrations"
)
SECRETS_MANAGER_PREFIX = os.environ.get("SECRETS_MANAGER_PREFIX", "ai-sw-pm")
SNS_ADMIN_ALERT_TOPIC = os.environ.get("SNS_ADMIN_ALERT_TOPIC")

# AWS clients (initialized lazily)
_dynamodb = None
_secrets_manager = None
_sns = None


def get_dynamodb():
    """Get or create DynamoDB resource."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb


def get_secrets_manager():
    """Get or create Secrets Manager client."""
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = boto3.client("secretsmanager")
    return _secrets_manager


def get_sns():
    """Get or create SNS client."""
    global _sns
    if _sns is None:
        _sns = boto3.client("sns")
    return _sns


def send_admin_alert(subject: str, message: str, error_details: dict = None):
    """
    Send alert to administrator via SNS.

    Validates: Requirement 4.6 - Alert administrator on validation failures

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
            Message=alert_message,
        )

        logger.info(f"Admin alert sent: {subject}")

    except Exception as e:
        logger.error(f"Failed to send admin alert: {str(e)}")


class AzureDevOpsAPIClient:
    """Client for interacting with Azure DevOps API."""

    def __init__(self, organization_url: str, pat: str):
        """
        Initialize Azure DevOps API client.

        Args:
            organization_url: Base URL for Azure DevOps organization
            pat: Personal Access Token for authentication
        """
        self.organization_url = organization_url.rstrip("/")
        self.pat = pat
        self.session = requests.Session()

        # Set up authentication using PAT
        # Azure DevOps uses Basic Auth with empty username and PAT as password
        auth_string = f":{pat}"
        encoded_auth = base64.b64encode(auth_string.encode()).decode()

        self.session.headers.update(
            {
                "Authorization": f"Basic {encoded_auth}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def _make_request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        """
        Make HTTP request to Azure DevOps API with retry logic.

        Validates: Requirement 4.8 - Exponential backoff retry logic

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full API URL
            **kwargs: Additional arguments for requests

        Returns:
            JSON response from API

        Raises:
            DataError: If API request fails after retries
        """
        max_retries = 5
        retry_delays = [1, 2, 4, 8, 16]  # Exponential backoff

        for attempt in range(max_retries):
            try:
                response = self.session.request(method, url, **kwargs)

                # Handle rate limiting (429)
                if response.status_code == 429:
                    if attempt < max_retries - 1:
                        delay = min(retry_delays[attempt], 60)
                        logger.warning(
                            f"Rate limited by Azure DevOps API. Retrying in {delay}s (attempt {attempt + 1}/{max_retries})"
                        )
                        import time

                        time.sleep(delay)
                        continue
                    else:
                        raise DataError(
                            "Azure DevOps API rate limit exceeded after maximum retries",
                            data_source="AzureDevOpsAPI",
                        )

                # Raise for other HTTP errors
                response.raise_for_status()

                return response.json()

            except requests.exceptions.HTTPError as e:
                if attempt < max_retries - 1 and e.response.status_code >= 500:
                    delay = min(retry_delays[attempt], 60)
                    logger.warning(
                        f"Azure DevOps API error {e.response.status_code}. Retrying in {delay}s (attempt {attempt + 1}/{max_retries})"
                    )
                    import time

                    time.sleep(delay)
                    continue
                else:
                    raise DataError(
                        f"Azure DevOps API request failed: {str(e)}",
                        data_source="AzureDevOpsAPI",
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
                        f"Failed to connect to Azure DevOps API: {str(e)}",
                        data_source="AzureDevOpsAPI",
                    )

        raise DataError(
            "Maximum retries exceeded for Azure DevOps API request",
            data_source="AzureDevOpsAPI",
        )

    def fetch_work_items(
        self, project: str, wiql_query: str = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch work items from Azure DevOps.

        Validates: Requirement 4.2 - Fetch work item data

        Args:
            project: Project name
            wiql_query: Optional WIQL query (defaults to all active items)

        Returns:
            List of work items
        """
        if not wiql_query:
            wiql_query = f"SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = '{project}' AND [System.State] <> 'Closed'"

        # Execute WIQL query
        wiql_url = f"{self.organization_url}/_apis/wit/wiql?api-version=7.0"
        wiql_response = self._make_request("POST", wiql_url, json={"query": wiql_query})

        work_item_refs = wiql_response.get("workItems", [])
        if not work_item_refs:
            return []

        # Get work item IDs
        work_item_ids = [
            str(item["id"]) for item in work_item_refs[:200]
        ]  # Limit to 200

        # Fetch work item details
        ids_param = ",".join(work_item_ids)
        work_items_url = f"{self.organization_url}/_apis/wit/workitems?ids={ids_param}&$expand=all&api-version=7.0"
        work_items_response = self._make_request("GET", work_items_url)

        return work_items_response.get("value", [])

    def fetch_iterations(self, project: str, team: str = None) -> List[Dict[str, Any]]:
        """
        Fetch iterations (sprints) from Azure DevOps.

        Validates: Requirement 4.2 - Fetch sprint metrics

        Args:
            project: Project name
            team: Team name (optional, defaults to project name)

        Returns:
            List of iterations
        """
        if not team:
            team = project

        url = f"{self.organization_url}/{project}/{team}/_apis/work/teamsettings/iterations?api-version=7.0"
        response = self._make_request("GET", url)

        return response.get("value", [])

    def fetch_iteration_work_items(
        self, project: str, team: str, iteration_id: str
    ) -> Dict[str, Any]:
        """
        Fetch work items for a specific iteration.

        Args:
            project: Project name
            team: Team name
            iteration_id: Iteration ID

        Returns:
            Iteration work items data
        """
        url = f"{self.organization_url}/{project}/{team}/_apis/work/teamsettings/iterations/{iteration_id}/workitems?api-version=7.0"
        return self._make_request("GET", url)

    def fetch_builds(self, project: str) -> List[Dict[str, Any]]:
        """
        Fetch build pipeline status from Azure DevOps.

        Validates: Requirement 4.2 - Fetch build pipeline status

        Args:
            project: Project name

        Returns:
            List of recent builds
        """
        url = f"{self.organization_url}/{project}/_apis/build/builds?api-version=7.0&$top=50"
        response = self._make_request("GET", url)

        return response.get("value", [])

    def fetch_releases(self, project: str) -> List[Dict[str, Any]]:
        """
        Fetch release tracking data from Azure DevOps.

        Validates: Requirement 4.2 - Fetch release tracking

        Args:
            project: Project name

        Returns:
            List of releases
        """
        # Note: Release Management API uses a different subdomain
        release_url = self.organization_url.replace(
            "dev.azure.com", "vsrm.dev.azure.com"
        )
        url = f"{release_url}/{project}/_apis/release/releases?api-version=7.0&$top=50"

        try:
            response = self._make_request("GET", url)
            return response.get("value", [])
        except DataError as e:
            # Release Management might not be enabled for all projects
            logger.warning(f"Failed to fetch releases for {project}: {str(e)}")
            return []


def transform_sprint_data(
    iteration: Dict[str, Any], work_items: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Transform Azure DevOps iteration data to internal schema.

    Validates: Requirement 4.5 - Transform Azure DevOps data to internal schema

    Args:
        iteration: Iteration data from Azure DevOps
        work_items: Work items in the iteration

    Returns:
        Transformed sprint data
    """
    # Calculate story points
    completed_points = 0
    planned_points = 0

    for item in work_items:
        fields = item.get("fields", {})
        effort = fields.get("Microsoft.VSTS.Scheduling.Effort", 0) or fields.get(
            "Microsoft.VSTS.Scheduling.StoryPoints", 0
        )

        if effort:
            planned_points += effort
            state = fields.get("System.State", "")
            if state in ["Done", "Closed", "Completed"]:
                completed_points += effort

    completion_rate = (
        (completed_points / planned_points * 100) if planned_points > 0 else 0
    )

    attributes = iteration.get("attributes", {})

    return {
        "sprintId": iteration.get("id"),
        "sprintName": iteration.get("name"),
        "startDate": attributes.get("startDate"),
        "endDate": attributes.get("finishDate"),
        "velocity": completed_points,
        "completedPoints": completed_points,
        "plannedPoints": planned_points,
        "completionRate": round(completion_rate, 2),
    }


def transform_backlog_data(work_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Transform Azure DevOps work items to backlog metrics.

    Validates: Requirement 4.5 - Transform Azure DevOps data to internal schema

    Args:
        work_items: List of work items from Azure DevOps

    Returns:
        Transformed backlog metrics
    """
    total_issues = len(work_items)

    issues_by_type = {}
    issues_by_priority = {}
    total_age_days = 0

    for item in work_items:
        fields = item.get("fields", {})

        # Count by type
        work_item_type = fields.get("System.WorkItemType", "Unknown")
        issues_by_type[work_item_type] = issues_by_type.get(work_item_type, 0) + 1

        # Count by priority
        priority = fields.get("Microsoft.VSTS.Common.Priority", "Unknown")
        priority_name = (
            f"Priority {priority}" if isinstance(priority, int) else str(priority)
        )
        issues_by_priority[priority_name] = issues_by_priority.get(priority_name, 0) + 1

        # Calculate age
        created = fields.get("System.CreatedDate")
        if created:
            created_date = datetime.fromisoformat(created.replace("Z", "+00:00"))
            age_days = (datetime.now(created_date.tzinfo) - created_date).days
            total_age_days += age_days

    average_age = (total_age_days / total_issues) if total_issues > 0 else 0

    return {
        "totalIssues": total_issues,
        "issuesByType": issues_by_type,
        "issuesByPriority": issues_by_priority,
        "averageAge": round(average_age, 2),
        "growthRate": 0,  # Will be calculated by comparing with previous data
    }


def transform_milestone_data(iterations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Transform Azure DevOps iterations to milestone data.

    Args:
        iterations: List of iterations

    Returns:
        List of transformed milestones
    """
    milestones = []

    for iteration in iterations:
        attributes = iteration.get("attributes", {})
        finish_date = attributes.get("finishDate")

        if finish_date:
            # Determine status based on time frame
            finish_dt = datetime.fromisoformat(finish_date.replace("Z", "+00:00"))
            now = datetime.now(finish_dt.tzinfo)

            if finish_dt < now:
                status = "COMPLETED"
            else:
                status = "ON_TRACK"

            milestones.append(
                {
                    "milestoneId": iteration.get("id"),
                    "name": iteration.get("name"),
                    "dueDate": finish_date.split("T")[0],  # Extract date part
                    "completionPercentage": 0,  # Would need additional calculation
                    "status": status,
                    "dependencies": [],
                }
            )

    return milestones


def transform_resource_data(work_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Transform work item assignments to resource allocation data.

    Args:
        work_items: List of work items with assignee information

    Returns:
        List of resource allocation data
    """
    resource_map = {}

    for item in work_items:
        fields = item.get("fields", {})
        assigned_to = fields.get("System.AssignedTo")

        if assigned_to:
            # Azure DevOps returns assignee as object or string
            if isinstance(assigned_to, dict):
                user_id = assigned_to.get("uniqueName") or assigned_to.get("id")
                user_name = assigned_to.get("displayName", "Unknown")
            else:
                user_id = assigned_to
                user_name = assigned_to

            if user_id not in resource_map:
                resource_map[user_id] = {
                    "userId": user_id,
                    "userName": user_name,
                    "allocatedHours": 0,
                    "capacity": 40,  # Default 40 hours per week
                    "utilizationRate": 0,
                }

            # Estimate hours from completed work or remaining work
            completed_work = (
                fields.get("Microsoft.VSTS.Scheduling.CompletedWork", 0) or 0
            )
            remaining_work = (
                fields.get("Microsoft.VSTS.Scheduling.RemainingWork", 0) or 0
            )
            resource_map[user_id]["allocatedHours"] += completed_work + remaining_work

    # Calculate utilization rates
    resources = list(resource_map.values())
    for resource in resources:
        capacity = resource["capacity"]
        if capacity > 0:
            resource["utilizationRate"] = round(
                (resource["allocatedHours"] / capacity) * 100, 2
            )

    return resources


def transform_dependency_data(work_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Transform work item relations to dependency data.

    Args:
        work_items: List of work items with relations

    Returns:
        List of dependencies
    """
    dependencies = []

    for item in work_items:
        item_id = str(item.get("id"))
        relations = item.get("relations", [])

        for relation in relations:
            rel_type = relation.get("rel", "")

            # Check for dependency relationships
            if (
                "Predecessor" in rel_type
                or "Successor" in rel_type
                or "Dependency" in rel_type
            ):
                url = relation.get("url", "")
                # Extract target work item ID from URL
                if "/workItems/" in url:
                    target_id = url.split("/workItems/")[-1]

                    dependency_type = (
                        "BLOCKS" if "Predecessor" in rel_type else "RELATES_TO"
                    )

                    dependencies.append(
                        {
                            "dependencyId": str(uuid.uuid4()),
                            "sourceTaskId": item_id,
                            "targetTaskId": target_id,
                            "type": dependency_type,
                            "status": "ACTIVE",
                        }
                    )

    return dependencies


@with_logging
@with_error_handling
@with_audit_logging
@with_tenant_isolation
def fetch_azure_devops_data(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Fetch project data from Azure DevOps API.

    Validates:
    - Requirement 4.1: Authenticate with Azure DevOps API using Personal Access Tokens
    - Requirement 4.2: Fetch work item data, sprint metrics, build pipeline status, and release tracking
    - Requirement 4.5: Validate data schema before storage
    - Requirement 4.7: Store ingested data with timestamp and source metadata

    Args:
        event: API Gateway event or Step Functions event with integration ID
        context: Lambda context

    Returns:
        Fetched and transformed project data
    """
    try:
        # Parse input
        if "body" in event:
            # API Gateway event
            body = json.loads(event.get("body", "{}"))
            integration_id = body.get("integrationId")
        else:
            # Step Functions event
            integration_id = event.get("integrationId")

        if not integration_id:
            raise ValidationError("integrationId is required", field="integrationId")

        # Get tenant_id from auth context
        tenant_id = event.get("tenant_id") or event.get("tenantId")
        if not tenant_id:
            raise ValidationError("tenantId is required", field="tenantId")

        # Retrieve integration configuration from DynamoDB
        dynamodb = get_dynamodb()
        integrations_table = dynamodb.Table(INTEGRATIONS_TABLE_NAME)

        try:
            response = integrations_table.get_item(
                Key={"PK": f"TENANT#{tenant_id}", "SK": f"INTEGRATION#{integration_id}"}
            )

            if "Item" not in response:
                raise ValidationError(
                    f"Integration {integration_id} not found for tenant {tenant_id}",
                    field="integrationId",
                )

            integration = response["Item"]

        except ClientError as e:
            raise DataError(
                f"Failed to retrieve integration configuration: {str(e)}",
                data_source="DynamoDB",
            )

        # Retrieve credentials from Secrets Manager
        configuration = integration.get("configuration", {})
        secret_name = configuration.get("secretName")

        if not secret_name:
            raise DataError(
                "Integration configuration missing secret name", data_source="DynamoDB"
            )

        try:
            secrets_manager = get_secrets_manager()
            secret_response = secrets_manager.get_secret_value(SecretId=secret_name)
            secret_data = json.loads(secret_response["SecretString"])

        except ClientError as e:
            raise DataError(
                f"Failed to retrieve credentials from Secrets Manager: {str(e)}",
                data_source="SecretsManager",
            )

        # Initialize Azure DevOps API client (Requirement 4.1)
        organization_url = secret_data["organizationUrl"]
        pat = secret_data["pat"]
        project_name = secret_data["projectName"]

        azure_client = AzureDevOpsAPIClient(organization_url, pat)

        logger.info(f"Fetching data for Azure DevOps project: {project_name}")

        # Fetch work items (Requirement 4.2)
        try:
            work_items = azure_client.fetch_work_items(project_name)
            backlog_metrics = transform_backlog_data(work_items)
        except Exception as e:
            logger.error(f"Failed to fetch work items for {project_name}: {str(e)}")
            work_items = []
            backlog_metrics = {
                "totalIssues": 0,
                "issuesByType": {},
                "issuesByPriority": {},
                "averageAge": 0,
                "growthRate": 0,
            }

        # Fetch iterations/sprints (Requirement 4.2)
        try:
            iterations = azure_client.fetch_iterations(project_name)
            sprints = []

            for iteration in iterations[:5]:  # Limit to recent 5 sprints
                try:
                    iteration_work_items_response = (
                        azure_client.fetch_iteration_work_items(
                            project_name, project_name, iteration["id"]
                        )
                    )

                    # Fetch full work item details
                    work_item_refs = iteration_work_items_response.get(
                        "workItemRelations", []
                    )
                    if work_item_refs:
                        work_item_ids = [
                            str(ref["target"]["id"])
                            for ref in work_item_refs
                            if "target" in ref
                        ]
                        if work_item_ids:
                            ids_param = ",".join(work_item_ids[:100])
                            work_items_url = f"{organization_url}/_apis/wit/workitems?ids={ids_param}&api-version=7.0"
                            iteration_items_response = azure_client._make_request(
                                "GET", work_items_url
                            )
                            iteration_items = iteration_items_response.get("value", [])
                        else:
                            iteration_items = []
                    else:
                        iteration_items = []

                    sprint_data = transform_sprint_data(iteration, iteration_items)
                    sprints.append(sprint_data)

                except Exception as e:
                    logger.warning(
                        f"Failed to fetch iteration {iteration.get('name')}: {str(e)}"
                    )
                    continue

            milestones = transform_milestone_data(iterations)

        except Exception as e:
            logger.error(f"Failed to fetch iterations for {project_name}: {str(e)}")
            sprints = []
            milestones = []

        # Fetch resource allocation
        try:
            resources = transform_resource_data(work_items)
        except Exception as e:
            logger.error(f"Failed to transform resources for {project_name}: {str(e)}")
            resources = []

        # Fetch dependencies
        try:
            dependencies = transform_dependency_data(work_items)
        except Exception as e:
            logger.error(
                f"Failed to transform dependencies for {project_name}: {str(e)}"
            )
            dependencies = []

        # Fetch build pipeline status (Requirement 4.2)
        try:
            builds = azure_client.fetch_builds(project_name)
            logger.info(f"Fetched {len(builds)} builds for {project_name}")
        except Exception as e:
            logger.error(f"Failed to fetch builds for {project_name}: {str(e)}")
            builds = []

        # Fetch release tracking (Requirement 4.2)
        try:
            releases = azure_client.fetch_releases(project_name)
            logger.info(f"Fetched {len(releases)} releases for {project_name}")
        except Exception as e:
            logger.error(f"Failed to fetch releases for {project_name}: {str(e)}")
            releases = []

        # Prepare project data with metadata (Requirement 4.7)
        project_data = {
            "projectId": str(uuid.uuid4()),
            "projectName": project_name,
            "source": "AZURE_DEVOPS",
            "lastSyncAt": datetime.utcnow().isoformat() + "Z",
            "metrics": {
                "sprints": sprints,
                "backlog": backlog_metrics,
                "milestones": milestones,
                "resources": resources,
                "dependencies": dependencies,
            },
        }

        project_data_list = [project_data]

        logger.info(
            f"Successfully fetched data for project {project_name} from Azure DevOps"
        )

        # Store validated data in RDS PostgreSQL (Requirements 4.5, 4.7)
        logger.info("Storing project data in database")

        try:
            storage_results = store_multiple_projects(
                tenant_id=tenant_id, projects=project_data_list, source="AZURE_DEVOPS"
            )

            # Alert administrator if any projects failed validation or storage (Requirement 4.6)
            if storage_results["failed"] > 0:
                send_admin_alert(
                    subject=f"Azure DevOps Data Ingestion Failures - Tenant {tenant_id}",
                    message=f"Failed to store {storage_results['failed']} out of {storage_results['total']} projects",
                    error_details={
                        "tenant_id": tenant_id,
                        "integration_id": integration_id,
                        "successful": storage_results["successful"],
                        "failed": storage_results["failed"],
                        "errors": storage_results["errors"][
                            :5
                        ],  # Limit to first 5 errors
                    },
                )

            logger.info(
                f"Data storage complete: {storage_results['successful']}/{storage_results['total']} successful"
            )

        except Exception as e:
            logger.error(f"Critical error during data storage: {str(e)}")

            # Alert administrator about critical storage failure (Requirement 4.6)
            send_admin_alert(
                subject=f"Critical: Azure DevOps Data Storage Failed - Tenant {tenant_id}",
                message=f"Complete storage failure for integration {integration_id}",
                error_details={
                    "tenant_id": tenant_id,
                    "integration_id": integration_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )

            raise DataError(
                f"Failed to store project data: {str(e)}", data_source="Database"
            )

        # Update integration last sync time
        try:
            timestamp = datetime.utcnow().isoformat() + "Z"
            integrations_table.update_item(
                Key={
                    "PK": f"TENANT#{tenant_id}",
                    "SK": f"INTEGRATION#{integration_id}",
                },
                UpdateExpression="SET lastSyncAt = :timestamp",
                ExpressionAttributeValues={":timestamp": timestamp},
            )
        except ClientError as e:
            logger.error(f"Failed to update integration sync time: {str(e)}")

        # Return response with storage results
        result = {
            "tenantId": tenant_id,
            "integrationId": integration_id,
            "projects": project_data_list,
            "storageResults": storage_results,
            "syncedAt": datetime.utcnow().isoformat() + "Z",
        }

        if "body" in event:
            # API Gateway response
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps(result),
            }
        else:
            # Step Functions response
            return result

    except (ValidationError, AuthorizationError, DataError):
        raise
    except Exception as e:
        logger.error(f"Unexpected error in fetch_azure_devops_data: {str(e)}")
        raise
