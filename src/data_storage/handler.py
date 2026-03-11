"""Data Storage Lambda handler - Store validated data in RDS and DynamoDB."""

import json
import os
from typing import Any, Dict
from datetime import datetime
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from shared.logger import get_logger
from shared.database import get_db_connection
from jira_integration.data_storage_helper import store_jira_project_data
from azure_devops_integration.data_storage import store_azure_devops_project_data

logger = get_logger()


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Store validated project data in RDS PostgreSQL and DynamoDB.
    
    Validates:
    - Requirement 3.7: Store ingested data with timestamp and source metadata
    - Requirement 4.7: Store ingested data with timestamp and source metadata
    
    Args:
        event: Step Functions event with validated data
        context: Lambda context
        
    Returns:
        Storage result with stored project IDs
    """
    try:
        logger.info("Starting data storage")
        
        # Extract validated data from event
        validated_data = event.get('validatedData', [])
        
        if not validated_data:
            logger.error("No validated data to store")
            return {
                'statusCode': 400,
                'stored': False,
                'errors': ['No validated data provided']
            }
        
        stored_projects = []
        storage_errors = []
        
        # Get database connection
        try:
            db_conn = get_db_connection()
        except Exception as e:
            logger.error(f"Failed to connect to database: {str(e)}")
            return {
                'statusCode': 500,
                'stored': False,
                'errors': [{
                    'error': 'Database connection failed',
                    'details': str(e)
                }]
            }
        
        # Store each project's data
        for item in validated_data:
            source = item.get('source')
            project = item.get('project')
            
            if not project:
                logger.warning(f"Skipping empty project from {source}")
                continue
            
            project_id = project.get('projectId')
            logger.info(f"Storing project {project_id} from {source}")
            
            try:
                # Add timestamp and source metadata
                project['lastSyncAt'] = datetime.utcnow().isoformat() + 'Z'
                project['source'] = source
                
                # Store based on source type
                if source == 'JIRA':
                    store_jira_project_data(db_conn, project)
                elif source == 'AZURE_DEVOPS':
                    store_azure_devops_project_data(db_conn, project)
                else:
                    raise ValueError(f"Unknown source type: {source}")
                
                stored_projects.append({
                    'projectId': project_id,
                    'source': source,
                    'storedAt': project['lastSyncAt']
                })
                
                logger.info(f"Successfully stored project {project_id} from {source}")
                
            except Exception as e:
                error_msg = f"Failed to store project {project_id} from {source}: {str(e)}"
                logger.error(error_msg)
                storage_errors.append({
                    'projectId': project_id,
                    'source': source,
                    'error': error_msg
                })
        
        # Close database connection
        try:
            db_conn.close()
        except Exception as e:
            logger.warning(f"Failed to close database connection: {str(e)}")
        
        # Determine overall storage status
        if storage_errors:
            logger.warning(
                f"Storage completed with {len(storage_errors)} errors and "
                f"{len(stored_projects)} successful stores"
            )
            
            # If all storage operations failed, return error
            if not stored_projects:
                return {
                    'statusCode': 500,
                    'stored': False,
                    'errors': storage_errors
                }
            
            # Partial success
            return {
                'statusCode': 200,
                'stored': True,
                'storedProjects': stored_projects,
                'warnings': storage_errors
            }
        
        logger.info(f"Storage completed successfully for {len(stored_projects)} projects")
        
        return {
            'statusCode': 200,
            'stored': True,
            'storedProjects': stored_projects
        }
        
    except Exception as e:
        logger.error(f"Unexpected error in data storage: {str(e)}")
        return {
            'statusCode': 500,
            'stored': False,
            'errors': [{
                'error': 'Internal storage error',
                'details': str(e)
            }]
        }
