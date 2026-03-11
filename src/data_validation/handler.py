"""Data Validation Lambda handler - Validate ingested data against schema."""

import json
import os
from typing import Any, Dict, List
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from shared.logger import get_logger
from shared.schema_validator import validate_project_data

logger = get_logger()


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Validate ingested data from external APIs against expected schema.
    
    Validates:
    - Requirement 3.5: Validate Jira API data schema before storage
    - Requirement 4.5: Validate Azure DevOps API data schema before storage
    
    Args:
        event: Step Functions event with fetchResults from parallel fetch
        context: Lambda context
        
    Returns:
        Validation result with validated data or errors
    """
    try:
        logger.info("Starting data validation")
        
        # Extract fetch results from event
        fetch_results = event.get('fetchResults', [])
        
        if not fetch_results:
            logger.error("No fetch results provided")
            return {
                'statusCode': 400,
                'valid': False,
                'errors': ['No data to validate']
            }
        
        validated_data = []
        validation_errors = []
        
        # Validate each source's data
        for result in fetch_results:
            source = result.get('source', 'UNKNOWN')
            status_code = result.get('statusCode', 500)
            body = result.get('body', {})
            
            logger.info(f"Validating data from source: {source}")
            
            # Check if fetch was successful
            if status_code != 200:
                error_msg = f"Fetch from {source} failed with status {status_code}"
                logger.error(error_msg)
                validation_errors.append({
                    'source': source,
                    'error': error_msg,
                    'details': body
                })
                continue
            
            # Parse body if it's a string
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except json.JSONDecodeError as e:
                    error_msg = f"Invalid JSON from {source}: {str(e)}"
                    logger.error(error_msg)
                    validation_errors.append({
                        'source': source,
                        'error': error_msg
                    })
                    continue
            
            # Extract project data
            projects = body.get('projects', [])
            
            if not projects:
                logger.warning(f"No projects found in data from {source}")
                continue
            
            # Validate each project
            for project in projects:
                try:
                    # Validate project data schema
                    is_valid, errors = validate_project_data(project, source)
                    
                    if is_valid:
                        validated_data.append({
                            'source': source,
                            'project': project
                        })
                        logger.info(
                            f"Successfully validated project {project.get('projectId')} from {source}"
                        )
                    else:
                        validation_errors.append({
                            'source': source,
                            'projectId': project.get('projectId', 'unknown'),
                            'errors': errors
                        })
                        logger.error(
                            f"Validation failed for project {project.get('projectId')} from {source}: {errors}"
                        )
                        
                except Exception as e:
                    error_msg = f"Validation error for project from {source}: {str(e)}"
                    logger.error(error_msg)
                    validation_errors.append({
                        'source': source,
                        'projectId': project.get('projectId', 'unknown'),
                        'error': error_msg
                    })
        
        # Determine overall validation status
        if validation_errors:
            logger.warning(
                f"Validation completed with {len(validation_errors)} errors and "
                f"{len(validated_data)} valid projects"
            )
            
            # If all validations failed, return error
            if not validated_data:
                return {
                    'statusCode': 400,
                    'valid': False,
                    'errors': validation_errors
                }
            
            # Partial success - return valid data with warnings
            return {
                'statusCode': 200,
                'valid': True,
                'validatedData': validated_data,
                'warnings': validation_errors
            }
        
        logger.info(f"Validation completed successfully for {len(validated_data)} projects")
        
        return {
            'statusCode': 200,
            'valid': True,
            'validatedData': validated_data
        }
        
    except Exception as e:
        logger.error(f"Unexpected error in data validation: {str(e)}")
        return {
            'statusCode': 500,
            'valid': False,
            'errors': [{
                'error': 'Internal validation error',
                'details': str(e)
            }]
        }
