"""Data storage handler for Jira integration.

Validates and stores fetched data in RDS PostgreSQL.

Validates:
- Property 8: Schema Validation (Requirements 3.5, 3.6)
- Property 9: Metadata Persistence (Requirements 3.7)
"""

import os
import sys
from typing import Any, Dict, List
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from shared.logger import get_logger
from shared.errors import ValidationError, DataError
from shared.schema_validator import validate_project_data
from shared.database import (
    insert_project,
    insert_sprints,
    insert_milestones,
    insert_resources,
    insert_dependencies
)

logger = get_logger()


def store_project_data(
    tenant_id: str,
    project_data: Dict[str, Any],
    source: str = 'JIRA'
) -> Dict[str, Any]:
    """
    Validate and store project data in RDS PostgreSQL.
    
    Validates:
    - Property 8: Schema Validation (Requirements 3.5, 3.6)
    - Property 9: Metadata Persistence (Requirements 3.7)
    
    Args:
        tenant_id: Tenant ID
        project_data: Project data dictionary
        source: Data source (JIRA or AZURE_DEVOPS)
        
    Returns:
        Storage result with project ID and counts
        
    Raises:
        ValidationError: If data validation fails
        DataError: If storage fails
    """
    try:
        # Step 1: Validate data schema (Property 8)
        logger.info(f"Validating project data for {project_data.get('projectName', 'unknown')}")
        validated_data = validate_project_data(project_data)
        
        # Step 2: Insert project record with metadata (Property 9)
        logger.info(f"Storing project: {validated_data['projectName']}")
        
        project_id = insert_project(
            tenant_id=tenant_id,
            project_name=validated_data['projectName'],
            source=source,
            external_project_id=validated_data.get('projectId')
        )
        
        logger.info(f"Project stored with ID: {project_id}")
        
        # Step 3: Store metrics data
        metrics = validated_data.get('metrics', {})
        storage_counts = {
            'project_id': project_id,
            'sprints': 0,
            'milestones': 0,
            'resources': 0,
            'dependencies': 0
        }
        
        # Store sprints
        if metrics.get('sprints'):
            try:
                count = insert_sprints(project_id, metrics['sprints'])
                storage_counts['sprints'] = count
                logger.info(f"Stored {count} sprints for project {project_id}")
            except Exception as e:
                logger.error(f"Failed to store sprints: {str(e)}")
                # Continue with other data even if sprints fail
        
        # Store milestones
        if metrics.get('milestones'):
            try:
                count = insert_milestones(project_id, metrics['milestones'], source)
                storage_counts['milestones'] = count
                logger.info(f"Stored {count} milestones for project {project_id}")
            except Exception as e:
                logger.error(f"Failed to store milestones: {str(e)}")
        
        # Store resources
        if metrics.get('resources'):
            try:
                count = insert_resources(project_id, metrics['resources'])
                storage_counts['resources'] = count
                logger.info(f"Stored {count} resources for project {project_id}")
            except Exception as e:
                logger.error(f"Failed to store resources: {str(e)}")
        
        # Store dependencies
        if metrics.get('dependencies'):
            try:
                count = insert_dependencies(project_id, metrics['dependencies'])
                storage_counts['dependencies'] = count
                logger.info(f"Stored {count} dependencies for project {project_id}")
            except Exception as e:
                logger.error(f"Failed to store dependencies: {str(e)}")
        
        logger.info(
            f"Successfully stored project data: {storage_counts}"
        )
        
        return {
            'success': True,
            'project_id': project_id,
            'project_name': validated_data['projectName'],
            'storage_counts': storage_counts,
            'stored_at': datetime.utcnow().isoformat() + 'Z'
        }
        
    except ValidationError as e:
        # Log validation error and alert administrator (Requirement 3.6)
        logger.error(
            f"Data validation failed for project {project_data.get('projectName', 'unknown')}: {str(e)}",
            extra={
                'error_type': 'ValidationError',
                'tenant_id': tenant_id,
                'project_name': project_data.get('projectName'),
                'error_code': e.error_code,
                'details': e.details
            }
        )
        
        # Re-raise to trigger administrator alert
        raise
        
    except DataError as e:
        # Log storage error and alert administrator
        logger.error(
            f"Data storage failed for project {project_data.get('projectName', 'unknown')}: {str(e)}",
            extra={
                'error_type': 'DataError',
                'tenant_id': tenant_id,
                'project_name': project_data.get('projectName'),
                'data_source': e.data_source,
                'details': e.details
            }
        )
        
        # Re-raise to trigger administrator alert
        raise


def store_multiple_projects(
    tenant_id: str,
    projects: List[Dict[str, Any]],
    source: str = 'JIRA'
) -> Dict[str, Any]:
    """
    Validate and store multiple projects.
    
    Args:
        tenant_id: Tenant ID
        projects: List of project data dictionaries
        source: Data source (JIRA or AZURE_DEVOPS)
        
    Returns:
        Storage results with success/failure counts
    """
    results = {
        'total': len(projects),
        'successful': 0,
        'failed': 0,
        'projects': [],
        'errors': []
    }
    
    for project_data in projects:
        try:
            result = store_project_data(tenant_id, project_data, source)
            results['successful'] += 1
            results['projects'].append(result)
            
        except (ValidationError, DataError) as e:
            results['failed'] += 1
            results['errors'].append({
                'project_name': project_data.get('projectName', 'unknown'),
                'error': str(e),
                'error_type': type(e).__name__
            })
            
            # Log but continue with other projects
            logger.warning(
                f"Failed to store project {project_data.get('projectName')}: {str(e)}"
            )
    
    logger.info(
        f"Batch storage complete: {results['successful']}/{results['total']} successful"
    )
    
    return results
