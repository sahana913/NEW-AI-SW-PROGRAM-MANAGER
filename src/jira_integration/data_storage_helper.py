"""Helper function for storing Jira project data in the workflow."""

import os
import sys
from typing import Any, Dict
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from shared.logger import get_logger
from shared.errors import DataError

logger = get_logger()


def store_jira_project_data(db_conn, project_data: Dict[str, Any]) -> None:
    """
    Store Jira project data in RDS PostgreSQL.
    
    Validates:
    - Property 8: Schema Validation (Requirements 3.5, 3.6)
    - Property 9: Metadata Persistence (Requirements 3.7)
    
    Args:
        db_conn: Database connection
        project_data: Project data dictionary with metadata
        
    Raises:
        DataError: If storage fails
    """
    try:
        cursor = db_conn.cursor()
        
        # Extract project information
        project_id = project_data.get('projectId')
        project_name = project_data.get('projectName')
        tenant_id = project_data.get('tenantId')
        source = project_data.get('source', 'JIRA')
        last_sync_at = project_data.get('lastSyncAt')
        
        logger.info(f"Storing Jira project: {project_name} (ID: {project_id})")
        
        # Insert or update project record
        cursor.execute("""
            INSERT INTO projects (project_id, tenant_id, project_name, source, external_project_id, last_sync_at, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (project_id) 
            DO UPDATE SET 
                project_name = EXCLUDED.project_name,
                last_sync_at = EXCLUDED.last_sync_at
        """, (project_id, tenant_id, project_name, source, project_id, last_sync_at))
        
        # Store metrics if available
        metrics = project_data.get('metrics', {})
        
        # Store sprints
        sprints = metrics.get('sprints', [])
        for sprint in sprints:
            cursor.execute("""
                INSERT INTO sprints (
                    sprint_id, project_id, sprint_name, start_date, end_date,
                    velocity, completed_points, planned_points, completion_rate, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (sprint_id) 
                DO UPDATE SET
                    velocity = EXCLUDED.velocity,
                    completed_points = EXCLUDED.completed_points,
                    completion_rate = EXCLUDED.completion_rate
            """, (
                sprint.get('sprintId'),
                project_id,
                sprint.get('sprintName'),
                sprint.get('startDate'),
                sprint.get('endDate'),
                sprint.get('velocity'),
                sprint.get('completedPoints'),
                sprint.get('plannedPoints'),
                sprint.get('completionRate')
            ))
        
        # Store milestones
        milestones = metrics.get('milestones', [])
        for milestone in milestones:
            cursor.execute("""
                INSERT INTO milestones (
                    milestone_id, project_id, milestone_name, due_date,
                    completion_percentage, status, source, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (milestone_id)
                DO UPDATE SET
                    completion_percentage = EXCLUDED.completion_percentage,
                    status = EXCLUDED.status
            """, (
                milestone.get('milestoneId'),
                project_id,
                milestone.get('name'),
                milestone.get('dueDate'),
                milestone.get('completionPercentage'),
                milestone.get('status'),
                source
            ))
        
        # Store resources
        resources = metrics.get('resources', [])
        for resource in resources:
            cursor.execute("""
                INSERT INTO resources (
                    resource_id, project_id, user_name, external_user_id,
                    allocated_hours, capacity, utilization_rate, week_start_date, created_at
                )
                VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, NOW())
            """, (
                project_id,
                resource.get('userName'),
                resource.get('userId'),
                resource.get('allocatedHours'),
                resource.get('capacity'),
                resource.get('utilizationRate'),
                datetime.utcnow().date()
            ))
        
        # Store dependencies
        dependencies = metrics.get('dependencies', [])
        for dependency in dependencies:
            cursor.execute("""
                INSERT INTO dependencies (
                    dependency_id, project_id, source_task_id, target_task_id,
                    dependency_type, status, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (dependency_id)
                DO UPDATE SET
                    status = EXCLUDED.status
            """, (
                dependency.get('dependencyId'),
                project_id,
                dependency.get('sourceTaskId'),
                dependency.get('targetTaskId'),
                dependency.get('type'),
                dependency.get('status')
            ))
        
        # Commit transaction
        db_conn.commit()
        
        logger.info(
            f"Successfully stored Jira project {project_name}: "
            f"{len(sprints)} sprints, {len(milestones)} milestones, "
            f"{len(resources)} resources, {len(dependencies)} dependencies"
        )
        
    except Exception as e:
        db_conn.rollback()
        error_msg = f"Failed to store Jira project data: {str(e)}"
        logger.error(error_msg)
        raise DataError(error_msg, data_source="RDS")
