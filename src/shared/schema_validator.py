"""Schema validation for external API data.

Validates: Property 8 - Schema Validation
Requirements: 3.5, 3.6, 4.5, 4.6
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from .errors import ValidationError
from .logger import get_logger

logger = get_logger()


def validate_sprint_schema(sprint: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate sprint data schema.
    
    Args:
        sprint: Sprint data dictionary
        
    Returns:
        Validated sprint data
        
    Raises:
        ValidationError: If schema is invalid
    """
    required_fields = ['sprintName', 'startDate', 'endDate']
    
    for field in required_fields:
        if field not in sprint or sprint[field] is None:
            raise ValidationError(
                f"Sprint missing required field: {field}",
                field=field,
                details={"sprint": sprint}
            )
    
    # Validate date formats
    try:
        if sprint.get('startDate'):
            datetime.fromisoformat(sprint['startDate'].replace('Z', '+00:00'))
        if sprint.get('endDate'):
            datetime.fromisoformat(sprint['endDate'].replace('Z', '+00:00'))
    except (ValueError, AttributeError) as e:
        raise ValidationError(
            f"Invalid date format in sprint: {str(e)}",
            field="date",
            details={"sprint": sprint}
        )
    
    # Validate numeric fields
    numeric_fields = ['velocity', 'completedPoints', 'plannedPoints', 'completionRate']
    for field in numeric_fields:
        if field in sprint and sprint[field] is not None:
            try:
                float(sprint[field])
            except (ValueError, TypeError):
                raise ValidationError(
                    f"Invalid numeric value for {field}",
                    field=field,
                    details={"value": sprint[field]}
                )
    
    return sprint


def validate_backlog_schema(backlog: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate backlog data schema.
    
    Args:
        backlog: Backlog data dictionary
        
    Returns:
        Validated backlog data
        
    Raises:
        ValidationError: If schema is invalid
    """
    required_fields = ['totalIssues', 'issuesByType', 'issuesByPriority']
    
    for field in required_fields:
        if field not in backlog:
            raise ValidationError(
                f"Backlog missing required field: {field}",
                field=field,
                details={"backlog": backlog}
            )
    
    # Validate totalIssues is a number
    try:
        int(backlog['totalIssues'])
    except (ValueError, TypeError):
        raise ValidationError(
            "Invalid totalIssues value",
            field="totalIssues",
            details={"value": backlog['totalIssues']}
        )
    
    # Validate issuesByType is a dictionary
    if not isinstance(backlog['issuesByType'], dict):
        raise ValidationError(
            "issuesByType must be a dictionary",
            field="issuesByType"
        )
    
    # Validate issuesByPriority is a dictionary
    if not isinstance(backlog['issuesByPriority'], dict):
        raise ValidationError(
            "issuesByPriority must be a dictionary",
            field="issuesByPriority"
        )
    
    # Validate numeric fields
    numeric_fields = ['averageAge', 'growthRate']
    for field in numeric_fields:
        if field in backlog and backlog[field] is not None:
            try:
                float(backlog[field])
            except (ValueError, TypeError):
                raise ValidationError(
                    f"Invalid numeric value for {field}",
                    field=field,
                    details={"value": backlog[field]}
                )
    
    return backlog


def validate_milestone_schema(milestone: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate milestone data schema.
    
    Args:
        milestone: Milestone data dictionary
        
    Returns:
        Validated milestone data
        
    Raises:
        ValidationError: If schema is invalid
    """
    required_fields = ['name']
    
    for field in required_fields:
        if field not in milestone or milestone[field] is None:
            raise ValidationError(
                f"Milestone missing required field: {field}",
                field=field,
                details={"milestone": milestone}
            )
    
    # Validate dueDate if present
    if milestone.get('dueDate'):
        try:
            datetime.fromisoformat(milestone['dueDate'].replace('Z', '+00:00'))
        except (ValueError, AttributeError) as e:
            raise ValidationError(
                f"Invalid date format in milestone: {str(e)}",
                field="dueDate",
                details={"milestone": milestone}
            )
    
    # Validate completionPercentage
    if 'completionPercentage' in milestone and milestone['completionPercentage'] is not None:
        try:
            percentage = float(milestone['completionPercentage'])
            if percentage < 0 or percentage > 100:
                raise ValidationError(
                    "completionPercentage must be between 0 and 100",
                    field="completionPercentage",
                    details={"value": percentage}
                )
        except (ValueError, TypeError):
            raise ValidationError(
                "Invalid completionPercentage value",
                field="completionPercentage",
                details={"value": milestone['completionPercentage']}
            )
    
    # Validate status
    valid_statuses = ['ON_TRACK', 'AT_RISK', 'DELAYED', 'COMPLETED']
    if 'status' in milestone and milestone['status'] not in valid_statuses:
        raise ValidationError(
            f"Invalid milestone status. Must be one of: {', '.join(valid_statuses)}",
            field="status",
            details={"value": milestone['status']}
        )
    
    return milestone


def validate_resource_schema(resource: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate resource allocation data schema.
    
    Args:
        resource: Resource data dictionary
        
    Returns:
        Validated resource data
        
    Raises:
        ValidationError: If schema is invalid
    """
    required_fields = ['userName']
    
    for field in required_fields:
        if field not in resource or resource[field] is None:
            raise ValidationError(
                f"Resource missing required field: {field}",
                field=field,
                details={"resource": resource}
            )
    
    # Validate numeric fields
    numeric_fields = ['allocatedHours', 'capacity', 'utilizationRate']
    for field in numeric_fields:
        if field in resource and resource[field] is not None:
            try:
                value = float(resource[field])
                if value < 0:
                    raise ValidationError(
                        f"{field} cannot be negative",
                        field=field,
                        details={"value": value}
                    )
            except (ValueError, TypeError):
                raise ValidationError(
                    f"Invalid numeric value for {field}",
                    field=field,
                    details={"value": resource[field]}
                )
    
    return resource


def validate_dependency_schema(dependency: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate dependency data schema.
    
    Args:
        dependency: Dependency data dictionary
        
    Returns:
        Validated dependency data
        
    Raises:
        ValidationError: If schema is invalid
    """
    required_fields = ['sourceTaskId', 'targetTaskId']
    
    for field in required_fields:
        if field not in dependency or dependency[field] is None:
            raise ValidationError(
                f"Dependency missing required field: {field}",
                field=field,
                details={"dependency": dependency}
            )
    
    # Validate type
    valid_types = ['BLOCKS', 'RELATES_TO']
    if 'type' in dependency and dependency['type'] not in valid_types:
        raise ValidationError(
            f"Invalid dependency type. Must be one of: {', '.join(valid_types)}",
            field="type",
            details={"value": dependency['type']}
        )
    
    # Validate status
    valid_statuses = ['ACTIVE', 'RESOLVED']
    if 'status' in dependency and dependency['status'] not in valid_statuses:
        raise ValidationError(
            f"Invalid dependency status. Must be one of: {', '.join(valid_statuses)}",
            field="status",
            details={"value": dependency['status']}
        )
    
    return dependency


def validate_project_data(project_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate complete project data schema.
    
    Validates: Property 8 - Schema Validation
    Requirements: 3.5, 3.6, 4.5, 4.6
    
    Args:
        project_data: Complete project data dictionary
        
    Returns:
        Validated project data
        
    Raises:
        ValidationError: If schema is invalid
    """
    # Validate top-level fields
    required_fields = ['projectName', 'source', 'metrics']
    
    for field in required_fields:
        if field not in project_data or project_data[field] is None:
            raise ValidationError(
                f"Project data missing required field: {field}",
                field=field,
                details={"project": project_data.get('projectName', 'unknown')}
            )
    
    # Validate source
    valid_sources = ['JIRA', 'AZURE_DEVOPS']
    if project_data['source'] not in valid_sources:
        raise ValidationError(
            f"Invalid data source. Must be one of: {', '.join(valid_sources)}",
            field="source",
            details={"value": project_data['source']}
        )
    
    # Validate metrics structure
    metrics = project_data['metrics']
    if not isinstance(metrics, dict):
        raise ValidationError(
            "Project metrics must be a dictionary",
            field="metrics"
        )
    
    # Validate sprints
    if 'sprints' in metrics and metrics['sprints']:
        if not isinstance(metrics['sprints'], list):
            raise ValidationError(
                "Sprints must be a list",
                field="metrics.sprints"
            )
        
        for i, sprint in enumerate(metrics['sprints']):
            try:
                validate_sprint_schema(sprint)
            except ValidationError as e:
                logger.error(f"Sprint validation failed at index {i}: {str(e)}")
                raise ValidationError(
                    f"Invalid sprint data at index {i}: {str(e)}",
                    field=f"metrics.sprints[{i}]",
                    details={"sprint": sprint}
                )
    
    # Validate backlog
    if 'backlog' in metrics and metrics['backlog']:
        try:
            validate_backlog_schema(metrics['backlog'])
        except ValidationError as e:
            logger.error(f"Backlog validation failed: {str(e)}")
            raise ValidationError(
                f"Invalid backlog data: {str(e)}",
                field="metrics.backlog",
                details={"backlog": metrics['backlog']}
            )
    
    # Validate milestones
    if 'milestones' in metrics and metrics['milestones']:
        if not isinstance(metrics['milestones'], list):
            raise ValidationError(
                "Milestones must be a list",
                field="metrics.milestones"
            )
        
        for i, milestone in enumerate(metrics['milestones']):
            try:
                validate_milestone_schema(milestone)
            except ValidationError as e:
                logger.error(f"Milestone validation failed at index {i}: {str(e)}")
                raise ValidationError(
                    f"Invalid milestone data at index {i}: {str(e)}",
                    field=f"metrics.milestones[{i}]",
                    details={"milestone": milestone}
                )
    
    # Validate resources
    if 'resources' in metrics and metrics['resources']:
        if not isinstance(metrics['resources'], list):
            raise ValidationError(
                "Resources must be a list",
                field="metrics.resources"
            )
        
        for i, resource in enumerate(metrics['resources']):
            try:
                validate_resource_schema(resource)
            except ValidationError as e:
                logger.error(f"Resource validation failed at index {i}: {str(e)}")
                raise ValidationError(
                    f"Invalid resource data at index {i}: {str(e)}",
                    field=f"metrics.resources[{i}]",
                    details={"resource": resource}
                )
    
    # Validate dependencies
    if 'dependencies' in metrics and metrics['dependencies']:
        if not isinstance(metrics['dependencies'], list):
            raise ValidationError(
                "Dependencies must be a list",
                field="metrics.dependencies"
            )
        
        for i, dependency in enumerate(metrics['dependencies']):
            try:
                validate_dependency_schema(dependency)
            except ValidationError as e:
                logger.error(f"Dependency validation failed at index {i}: {str(e)}")
                raise ValidationError(
                    f"Invalid dependency data at index {i}: {str(e)}",
                    field=f"metrics.dependencies[{i}]",
                    details={"dependency": dependency}
                )
    
    logger.info(
        f"Project data validation successful for {project_data['projectName']}"
    )
    
    return project_data
