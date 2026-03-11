"""Database connection and query utilities for RDS PostgreSQL."""

import os
import json
from typing import Any, Dict, List, Optional, Tuple
from contextlib import contextmanager
import boto3
from botocore.exceptions import ClientError

try:
    import psycopg2
    from psycopg2 import pool, sql
    from psycopg2.extras import RealDictCursor
except ImportError:
    # For local development without psycopg2
    psycopg2 = None
    pool = None
    sql = None
    RealDictCursor = None

from .logger import get_logger
from .errors import DataError

logger = get_logger()

# Environment variables
DB_SECRET_NAME = os.environ.get('DB_SECRET_NAME', 'ai-sw-pm-db-credentials')
DB_HOST = os.environ.get('DB_HOST')
DB_PORT = os.environ.get('DB_PORT', '5432')
DB_NAME = os.environ.get('DB_NAME', 'ai_sw_program_manager')

# Connection pool (initialized lazily)
_connection_pool = None
_secrets_manager = None


def get_secrets_manager():
    """Get or create Secrets Manager client."""
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = boto3.client('secretsmanager')
    return _secrets_manager


def get_db_credentials() -> Dict[str, str]:
    """
    Retrieve database credentials from AWS Secrets Manager.
    
    Returns:
        Dictionary with username and password
        
    Raises:
        DataError: If credentials cannot be retrieved
    """
    try:
        secrets_manager = get_secrets_manager()
        response = secrets_manager.get_secret_value(SecretId=DB_SECRET_NAME)
        secret_data = json.loads(response['SecretString'])
        
        return {
            'username': secret_data['username'],
            'password': secret_data['password'],
            'host': DB_HOST or secret_data.get('host'),
            'port': int(DB_PORT or secret_data.get('port', 5432)),
            'database': DB_NAME or secret_data.get('dbname', 'ai_sw_program_manager')
        }
    except ClientError as e:
        raise DataError(
            f"Failed to retrieve database credentials: {str(e)}",
            data_source="SecretsManager"
        )
    except (KeyError, ValueError) as e:
        raise DataError(
            f"Invalid database credentials format: {str(e)}",
            data_source="SecretsManager"
        )


def get_connection_pool():
    """
    Get or create database connection pool.
    
    Returns:
        psycopg2 connection pool
        
    Raises:
        DataError: If connection pool cannot be created
    """
    global _connection_pool
    
    if psycopg2 is None:
        raise DataError(
            "psycopg2 is not installed. Install with: pip install psycopg2-binary",
            data_source="Database"
        )
    
    if _connection_pool is None:
        try:
            credentials = get_db_credentials()
            
            _connection_pool = pool.SimpleConnectionPool(
                minconn=1,
                maxconn=10,
                host=credentials['host'],
                port=credentials['port'],
                database=credentials['database'],
                user=credentials['username'],
                password=credentials['password'],
                connect_timeout=10
            )
            
            logger.info("Database connection pool created successfully")
            
        except Exception as e:
            raise DataError(
                f"Failed to create database connection pool: {str(e)}",
                data_source="Database"
            )
    
    return _connection_pool


@contextmanager
def get_db_connection():
    """
    Context manager for database connections.
    
    Yields:
        Database connection
        
    Raises:
        DataError: If connection cannot be obtained
    """
    conn_pool = get_connection_pool()
    conn = None
    
    try:
        conn = conn_pool.getconn()
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        raise DataError(
            f"Database connection error: {str(e)}",
            data_source="Database"
        )
    finally:
        if conn:
            conn_pool.putconn(conn)


def execute_query(
    query: str,
    params: Optional[Tuple] = None,
    fetch: bool = True,
    commit: bool = False
) -> Optional[List[Dict[str, Any]]]:
    """
    Execute a database query.
    
    Args:
        query: SQL query string
        params: Query parameters
        fetch: Whether to fetch results
        commit: Whether to commit the transaction
        
    Returns:
        List of result rows as dictionaries (if fetch=True)
        
    Raises:
        DataError: If query execution fails
    """
    with get_db_connection() as conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                
                if commit:
                    conn.commit()
                
                if fetch:
                    results = cursor.fetchall()
                    return [dict(row) for row in results]
                
                return None
                
        except Exception as e:
            conn.rollback()
            raise DataError(
                f"Query execution failed: {str(e)}",
                data_source="Database",
                details={"query": query[:100]}  # Log first 100 chars of query
            )


def execute_batch(
    query: str,
    params_list: List[Tuple],
    commit: bool = True
) -> int:
    """
    Execute a batch of queries with different parameters.
    
    Args:
        query: SQL query string
        params_list: List of parameter tuples
        commit: Whether to commit the transaction
        
    Returns:
        Number of rows affected
        
    Raises:
        DataError: If batch execution fails
    """
    if not params_list:
        return 0
    
    with get_db_connection() as conn:
        try:
            with conn.cursor() as cursor:
                from psycopg2.extras import execute_batch
                execute_batch(cursor, query, params_list)
                
                if commit:
                    conn.commit()
                
                return cursor.rowcount
                
        except Exception as e:
            conn.rollback()
            raise DataError(
                f"Batch execution failed: {str(e)}",
                data_source="Database",
                details={"query": query[:100], "batch_size": len(params_list)}
            )


def insert_project(
    tenant_id: str,
    project_name: str,
    source: str,
    external_project_id: Optional[str] = None
) -> str:
    """
    Insert a new project or update if exists.
    
    Args:
        tenant_id: Tenant ID
        project_name: Project name
        source: Data source (JIRA, AZURE_DEVOPS)
        external_project_id: External project identifier
        
    Returns:
        Project ID (UUID)
        
    Raises:
        DataError: If insert fails
    """
    query = """
        INSERT INTO projects (tenant_id, project_name, source, external_project_id, last_sync_at)
        VALUES (%s, %s, %s, %s, NOW())
        ON CONFLICT (tenant_id, external_project_id)
        DO UPDATE SET
            project_name = EXCLUDED.project_name,
            last_sync_at = NOW()
        RETURNING project_id::text
    """
    
    # Note: This assumes a unique constraint on (tenant_id, external_project_id)
    # If not present, we'll do a simpler insert
    try:
        results = execute_query(
            query,
            (tenant_id, project_name, source, external_project_id),
            fetch=True,
            commit=True
        )
        
        if results:
            return results[0]['project_id']
        
        # Fallback: query for existing project
        query_existing = """
            SELECT project_id::text FROM projects
            WHERE tenant_id = %s AND external_project_id = %s
        """
        results = execute_query(
            query_existing,
            (tenant_id, external_project_id),
            fetch=True
        )
        
        if results:
            return results[0]['project_id']
        
        raise DataError("Failed to insert or retrieve project", data_source="Database")
        
    except Exception as e:
        # If ON CONFLICT not supported, try simple insert
        query_simple = """
            INSERT INTO projects (tenant_id, project_name, source, external_project_id, last_sync_at)
            VALUES (%s, %s, %s, %s, NOW())
            RETURNING project_id::text
        """
        
        results = execute_query(
            query_simple,
            (tenant_id, project_name, source, external_project_id),
            fetch=True,
            commit=True
        )
        
        if results:
            return results[0]['project_id']
        
        raise DataError(
            f"Failed to insert project: {str(e)}",
            data_source="Database"
        )


def insert_sprints(project_id: str, sprints: List[Dict[str, Any]]) -> int:
    """
    Insert sprint data for a project.
    
    Args:
        project_id: Project ID
        sprints: List of sprint dictionaries
        
    Returns:
        Number of sprints inserted
        
    Raises:
        DataError: If insert fails
    """
    if not sprints:
        return 0
    
    query = """
        INSERT INTO sprints (
            project_id, sprint_name, start_date, end_date,
            velocity, completed_points, planned_points, completion_rate
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    params_list = [
        (
            project_id,
            sprint['sprintName'],
            sprint['startDate'],
            sprint['endDate'],
            sprint.get('velocity', 0),
            sprint.get('completedPoints', 0),
            sprint.get('plannedPoints', 0),
            sprint.get('completionRate', 0)
        )
        for sprint in sprints
    ]
    
    return execute_batch(query, params_list, commit=True)


def insert_backlog_items(project_id: str, backlog_data: Dict[str, Any]) -> int:
    """
    Insert backlog metrics for a project.
    
    Note: This stores aggregate metrics, not individual items.
    For individual items, we'd need a different approach.
    
    Args:
        project_id: Project ID
        backlog_data: Backlog metrics dictionary
        
    Returns:
        Number of items inserted
        
    Raises:
        DataError: If insert fails
    """
    # For now, we'll store this as metadata
    # In a full implementation, we'd store individual backlog items
    logger.info(f"Backlog data for project {project_id}: {backlog_data}")
    return 0


def insert_milestones(project_id: str, milestones: List[Dict[str, Any]], source: str) -> int:
    """
    Insert milestone data for a project.
    
    Args:
        project_id: Project ID
        milestones: List of milestone dictionaries
        source: Data source (JIRA, AZURE_DEVOPS, etc.)
        
    Returns:
        Number of milestones inserted
        
    Raises:
        DataError: If insert fails
    """
    if not milestones:
        return 0
    
    query = """
        INSERT INTO milestones (
            project_id, milestone_name, due_date,
            completion_percentage, status, source
        )
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    
    params_list = [
        (
            project_id,
            milestone['name'],
            milestone['dueDate'],
            milestone.get('completionPercentage', 0),
            milestone.get('status', 'ON_TRACK'),
            source
        )
        for milestone in milestones
        if milestone.get('dueDate')  # Only insert if due date is present
    ]
    
    if not params_list:
        return 0
    
    return execute_batch(query, params_list, commit=True)


def insert_resources(project_id: str, resources: List[Dict[str, Any]]) -> int:
    """
    Insert resource allocation data for a project.
    
    Args:
        project_id: Project ID
        resources: List of resource dictionaries
        
    Returns:
        Number of resources inserted
        
    Raises:
        DataError: If insert fails
    """
    if not resources:
        return 0
    
    from datetime import datetime, timedelta
    
    # Get current week start (Monday)
    today = datetime.now()
    week_start = today - timedelta(days=today.weekday())
    week_start_date = week_start.date()
    
    query = """
        INSERT INTO resources (
            project_id, user_name, external_user_id,
            allocated_hours, capacity, utilization_rate, week_start_date
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    
    params_list = [
        (
            project_id,
            resource['userName'],
            resource.get('userId'),
            resource.get('allocatedHours', 0),
            resource.get('capacity', 40),
            resource.get('utilizationRate', 0),
            week_start_date
        )
        for resource in resources
    ]
    
    return execute_batch(query, params_list, commit=True)


def insert_dependencies(project_id: str, dependencies: List[Dict[str, Any]]) -> int:
    """
    Insert dependency data for a project.
    
    Args:
        project_id: Project ID
        dependencies: List of dependency dictionaries
        
    Returns:
        Number of dependencies inserted
        
    Raises:
        DataError: If insert fails
    """
    if not dependencies:
        return 0
    
    query = """
        INSERT INTO dependencies (
            project_id, source_task_id, target_task_id,
            dependency_type, status
        )
        VALUES (%s, %s, %s, %s, %s)
    """
    
    params_list = [
        (
            project_id,
            dependency['sourceTaskId'],
            dependency['targetTaskId'],
            dependency.get('type', 'RELATES_TO'),
            dependency.get('status', 'ACTIVE')
        )
        for dependency in dependencies
    ]
    
    return execute_batch(query, params_list, commit=True)
