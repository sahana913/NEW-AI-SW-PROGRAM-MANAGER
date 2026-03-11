"""Data aggregation utilities for report generation."""

import sys
import os
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from decimal import Decimal

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3
from boto3.dynamodb.conditions import Key, Attr

from shared.logger import get_logger
from shared.database import execute_query
from shared.errors import DataError

logger = get_logger()

# DynamoDB client (initialized lazily)
_dynamodb = None


def get_dynamodb():
    """Get or create DynamoDB resource."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource('dynamodb')
    return _dynamodb


def query_project_health_scores(tenant_id: str, project_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Query health scores and RAG status for projects.
    
    Args:
        tenant_id: Tenant ID
        project_ids: Optional list of specific project IDs
        
    Returns:
        List of project health data
    """
    try:
        # Query from RDS
        if project_ids:
            placeholders = ','.join(['%s'] * len(project_ids))
            query = f"""
                SELECT 
                    p.project_id::text,
                    p.project_name,
                    p.source,
                    p.last_sync_at
                FROM projects p
                WHERE p.tenant_id = %s AND p.project_id::text IN ({placeholders})
                ORDER BY p.project_name
            """
            params = (tenant_id, *project_ids)
        else:
            query = """
                SELECT 
                    p.project_id::text,
                    p.project_name,
                    p.source,
                    p.last_sync_at
                FROM projects p
                WHERE p.tenant_id = %s
                ORDER BY p.project_name
            """
            params = (tenant_id,)
        
        projects = execute_query(query, params, fetch=True)
        
        # For each project, we would query health scores from DynamoDB
        # For now, return basic project info
        return projects or []
        
    except Exception as e:
        logger.error(f"Failed to query project health scores: {str(e)}")
        raise DataError(
            f"Failed to query project health scores: {str(e)}",
            data_source="RDS"
        )


def query_completed_milestones(
    tenant_id: str,
    project_ids: Optional[List[str]] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """
    Query completed milestones within a date range.
    
    Args:
        tenant_id: Tenant ID
        project_ids: Optional list of specific project IDs
        start_date: Start of date range
        end_date: End of date range
        
    Returns:
        List of completed milestones
    """
    try:
        # Default to last 7 days if not specified
        if not end_date:
            end_date = datetime.now()
        if not start_date:
            start_date = end_date - timedelta(days=7)
        
        # Build query
        if project_ids:
            placeholders = ','.join(['%s'] * len(project_ids))
            query = f"""
                SELECT 
                    m.milestone_id::text,
                    m.project_id::text,
                    p.project_name,
                    m.milestone_name,
                    m.due_date,
                    m.completion_percentage,
                    m.status,
                    m.source
                FROM milestones m
                JOIN projects p ON m.project_id = p.project_id
                WHERE p.tenant_id = %s 
                    AND m.status = 'COMPLETED'
                    AND m.project_id::text IN ({placeholders})
                    AND m.due_date BETWEEN %s AND %s
                ORDER BY m.due_date DESC
            """
            params = (tenant_id, *project_ids, start_date.date(), end_date.date())
        else:
            query = """
                SELECT 
                    m.milestone_id::text,
                    m.project_id::text,
                    p.project_name,
                    m.milestone_name,
                    m.due_date,
                    m.completion_percentage,
                    m.status,
                    m.source
                FROM milestones m
                JOIN projects p ON m.project_id = p.project_id
                WHERE p.tenant_id = %s 
                    AND m.status = 'COMPLETED'
                    AND m.due_date BETWEEN %s AND %s
                ORDER BY m.due_date DESC
            """
            params = (tenant_id, start_date.date(), end_date.date())
        
        milestones = execute_query(query, params, fetch=True)
        
        # Convert date objects to strings
        for milestone in milestones or []:
            if 'due_date' in milestone and milestone['due_date']:
                milestone['due_date'] = milestone['due_date'].isoformat()
            if 'completion_percentage' in milestone and isinstance(milestone['completion_percentage'], Decimal):
                milestone['completion_percentage'] = float(milestone['completion_percentage'])
        
        return milestones or []
        
    except Exception as e:
        logger.error(f"Failed to query completed milestones: {str(e)}")
        raise DataError(
            f"Failed to query completed milestones: {str(e)}",
            data_source="RDS"
        )


def query_upcoming_milestones(
    tenant_id: str,
    project_ids: Optional[List[str]] = None,
    days_ahead: int = 14
) -> List[Dict[str, Any]]:
    """
    Query upcoming milestones within the next N days.
    
    Args:
        tenant_id: Tenant ID
        project_ids: Optional list of specific project IDs
        days_ahead: Number of days to look ahead (default 14)
        
    Returns:
        List of upcoming milestones
    """
    try:
        today = datetime.now().date()
        future_date = today + timedelta(days=days_ahead)
        
        # Build query
        if project_ids:
            placeholders = ','.join(['%s'] * len(project_ids))
            query = f"""
                SELECT 
                    m.milestone_id::text,
                    m.project_id::text,
                    p.project_name,
                    m.milestone_name,
                    m.due_date,
                    m.completion_percentage,
                    m.status,
                    m.source
                FROM milestones m
                JOIN projects p ON m.project_id = p.project_id
                WHERE p.tenant_id = %s 
                    AND m.status != 'COMPLETED'
                    AND m.project_id::text IN ({placeholders})
                    AND m.due_date BETWEEN %s AND %s
                ORDER BY m.due_date ASC
            """
            params = (tenant_id, *project_ids, today, future_date)
        else:
            query = """
                SELECT 
                    m.milestone_id::text,
                    m.project_id::text,
                    p.project_name,
                    m.milestone_name,
                    m.due_date,
                    m.completion_percentage,
                    m.status,
                    m.source
                FROM milestones m
                JOIN projects p ON m.project_id = p.project_id
                WHERE p.tenant_id = %s 
                    AND m.status != 'COMPLETED'
                    AND m.due_date BETWEEN %s AND %s
                ORDER BY m.due_date ASC
            """
            params = (tenant_id, today, future_date)
        
        milestones = execute_query(query, params, fetch=True)
        
        # Convert date objects to strings
        for milestone in milestones or []:
            if 'due_date' in milestone and milestone['due_date']:
                milestone['due_date'] = milestone['due_date'].isoformat()
            if 'completion_percentage' in milestone and isinstance(milestone['completion_percentage'], Decimal):
                milestone['completion_percentage'] = float(milestone['completion_percentage'])
        
        return milestones or []
        
    except Exception as e:
        logger.error(f"Failed to query upcoming milestones: {str(e)}")
        raise DataError(
            f"Failed to query upcoming milestones: {str(e)}",
            data_source="RDS"
        )


def query_active_risks(
    tenant_id: str,
    project_ids: Optional[List[str]] = None,
    severity_filter: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Query active risk alerts from DynamoDB.
    
    Args:
        tenant_id: Tenant ID
        project_ids: Optional list of specific project IDs
        severity_filter: Optional list of severity levels to include
        
    Returns:
        List of active risks
    """
    try:
        dynamodb = get_dynamodb()
        risks_table = dynamodb.Table(os.environ.get('RISKS_TABLE', 'ai-sw-pm-risks'))
        
        # Query risks for tenant
        response = risks_table.query(
            KeyConditionExpression=Key('PK').eq(f'TENANT#{tenant_id}') & Key('SK').begins_with('RISK#'),
            FilterExpression=Attr('status').eq('ACTIVE')
        )
        
        risks = response.get('Items', [])
        
        # Filter by project IDs if specified
        if project_ids:
            risks = [r for r in risks if r.get('projectId') in project_ids]
        
        # Filter by severity if specified
        if severity_filter:
            risks = [r for r in risks if r.get('severity') in severity_filter]
        
        # Sort by severity (CRITICAL > HIGH > MEDIUM > LOW)
        severity_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
        risks.sort(key=lambda r: severity_order.get(r.get('severity', 'LOW'), 4))
        
        return risks
        
    except Exception as e:
        logger.error(f"Failed to query active risks: {str(e)}")
        raise DataError(
            f"Failed to query active risks: {str(e)}",
            data_source="DynamoDB"
        )


def query_velocity_trends(
    tenant_id: str,
    project_ids: Optional[List[str]] = None,
    num_sprints: int = 8
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Query velocity trends for projects.
    
    Args:
        tenant_id: Tenant ID
        project_ids: Optional list of specific project IDs
        num_sprints: Number of recent sprints to include
        
    Returns:
        Dictionary mapping project_id to list of sprint velocity data
    """
    try:
        # Build query
        if project_ids:
            placeholders = ','.join(['%s'] * len(project_ids))
            query = f"""
                SELECT 
                    s.project_id::text,
                    p.project_name,
                    s.sprint_name,
                    s.start_date,
                    s.end_date,
                    s.velocity,
                    s.completed_points,
                    s.planned_points,
                    s.completion_rate
                FROM sprints s
                JOIN projects p ON s.project_id = p.project_id
                WHERE p.tenant_id = %s AND s.project_id::text IN ({placeholders})
                ORDER BY s.project_id, s.start_date DESC
            """
            params = (tenant_id, *project_ids)
        else:
            query = """
                SELECT 
                    s.project_id::text,
                    p.project_name,
                    s.sprint_name,
                    s.start_date,
                    s.end_date,
                    s.velocity,
                    s.completed_points,
                    s.planned_points,
                    s.completion_rate
                FROM sprints s
                JOIN projects p ON s.project_id = p.project_id
                WHERE p.tenant_id = %s
                ORDER BY s.project_id, s.start_date DESC
            """
            params = (tenant_id,)
        
        sprints = execute_query(query, params, fetch=True) or []
        
        # Group by project and limit to num_sprints per project
        velocity_by_project = {}
        for sprint in sprints:
            project_id = sprint['project_id']
            if project_id not in velocity_by_project:
                velocity_by_project[project_id] = []
            
            if len(velocity_by_project[project_id]) < num_sprints:
                # Convert Decimal to float
                if isinstance(sprint.get('velocity'), Decimal):
                    sprint['velocity'] = float(sprint['velocity'])
                if isinstance(sprint.get('completed_points'), Decimal):
                    sprint['completed_points'] = float(sprint['completed_points'])
                if isinstance(sprint.get('planned_points'), Decimal):
                    sprint['planned_points'] = float(sprint['planned_points'])
                if isinstance(sprint.get('completion_rate'), Decimal):
                    sprint['completion_rate'] = float(sprint['completion_rate'])
                
                # Convert dates to strings
                if sprint.get('start_date'):
                    sprint['start_date'] = sprint['start_date'].isoformat()
                if sprint.get('end_date'):
                    sprint['end_date'] = sprint['end_date'].isoformat()
                
                velocity_by_project[project_id].append(sprint)
        
        return velocity_by_project
        
    except Exception as e:
        logger.error(f"Failed to query velocity trends: {str(e)}")
        raise DataError(
            f"Failed to query velocity trends: {str(e)}",
            data_source="RDS"
        )


def query_backlog_status(
    tenant_id: str,
    project_ids: Optional[List[str]] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Query current backlog status for projects.
    
    Args:
        tenant_id: Tenant ID
        project_ids: Optional list of specific project IDs
        
    Returns:
        Dictionary mapping project_id to backlog metrics
    """
    try:
        # Build query
        if project_ids:
            placeholders = ','.join(['%s'] * len(project_ids))
            query = f"""
                SELECT 
                    b.project_id::text,
                    p.project_name,
                    COUNT(*) as total_items,
                    COUNT(CASE WHEN b.status = 'OPEN' THEN 1 END) as open_items,
                    COUNT(CASE WHEN b.item_type = 'bug' THEN 1 END) as bugs,
                    COUNT(CASE WHEN b.item_type = 'feature' THEN 1 END) as features,
                    COUNT(CASE WHEN b.item_type = 'technical_debt' THEN 1 END) as tech_debt,
                    AVG(b.age_days) as avg_age_days
                FROM backlog_items b
                JOIN projects p ON b.project_id = p.project_id
                WHERE p.tenant_id = %s AND b.project_id::text IN ({placeholders})
                GROUP BY b.project_id, p.project_name
            """
            params = (tenant_id, *project_ids)
        else:
            query = """
                SELECT 
                    b.project_id::text,
                    p.project_name,
                    COUNT(*) as total_items,
                    COUNT(CASE WHEN b.status = 'OPEN' THEN 1 END) as open_items,
                    COUNT(CASE WHEN b.item_type = 'bug' THEN 1 END) as bugs,
                    COUNT(CASE WHEN b.item_type = 'feature' THEN 1 END) as features,
                    COUNT(CASE WHEN b.item_type = 'technical_debt' THEN 1 END) as tech_debt,
                    AVG(b.age_days) as avg_age_days
                FROM backlog_items b
                JOIN projects p ON b.project_id = p.project_id
                WHERE p.tenant_id = %s
                GROUP BY b.project_id, p.project_name
            """
            params = (tenant_id,)
        
        results = execute_query(query, params, fetch=True) or []
        
        # Convert to dictionary keyed by project_id
        backlog_by_project = {}
        for row in results:
            project_id = row['project_id']
            # Convert Decimal to int/float
            backlog_by_project[project_id] = {
                'project_name': row['project_name'],
                'total_items': int(row.get('total_items', 0)),
                'open_items': int(row.get('open_items', 0)),
                'bugs': int(row.get('bugs', 0)),
                'features': int(row.get('features', 0)),
                'tech_debt': int(row.get('tech_debt', 0)),
                'avg_age_days': float(row.get('avg_age_days', 0)) if row.get('avg_age_days') else 0
            }
        
        return backlog_by_project
        
    except Exception as e:
        logger.error(f"Failed to query backlog status: {str(e)}")
        raise DataError(
            f"Failed to query backlog status: {str(e)}",
            data_source="RDS"
        )


def query_predictions(
    tenant_id: str,
    project_ids: Optional[List[str]] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Query latest predictions for projects from DynamoDB.
    
    Args:
        tenant_id: Tenant ID
        project_ids: Optional list of specific project IDs
        
    Returns:
        Dictionary mapping project_id to latest predictions
    """
    try:
        dynamodb = get_dynamodb()
        predictions_table = dynamodb.Table(os.environ.get('PREDICTIONS_TABLE', 'ai-sw-pm-predictions'))
        
        # Query predictions for tenant
        response = predictions_table.query(
            KeyConditionExpression=Key('PK').eq(f'TENANT#{tenant_id}') & Key('SK').begins_with('PREDICTION#'),
            ScanIndexForward=False,  # Get most recent first
            Limit=100  # Reasonable limit
        )
        
        predictions = response.get('Items', [])
        
        # Filter by project IDs if specified
        if project_ids:
            predictions = [p for p in predictions if p.get('projectId') in project_ids]
        
        # Group by project and prediction type, keeping only the latest
        predictions_by_project = {}
        for pred in predictions:
            project_id = pred.get('projectId')
            pred_type = pred.get('predictionType')
            
            if project_id not in predictions_by_project:
                predictions_by_project[project_id] = {}
            
            # Keep only if we don't have this type yet (since sorted by date desc)
            if pred_type not in predictions_by_project[project_id]:
                predictions_by_project[project_id][pred_type] = pred
        
        return predictions_by_project
        
    except Exception as e:
        logger.error(f"Failed to query predictions: {str(e)}")
        raise DataError(
            f"Failed to query predictions: {str(e)}",
            data_source="DynamoDB"
        )
