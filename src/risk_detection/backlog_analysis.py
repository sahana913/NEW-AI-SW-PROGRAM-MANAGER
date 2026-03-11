"""Backlog growth analysis for detecting backlog-related risks."""

import sys
import os
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.database import execute_query
from shared.logger import get_logger
from shared.errors import DataError

logger = get_logger()


def query_backlog_metrics(project_id: str) -> Dict[str, Any]:
    """
    Query backlog metrics for a project.
    
    Args:
        project_id: Project ID to query
        
    Returns:
        Dictionary with backlog metrics:
        - total_items: Total backlog items
        - open_items: Open backlog items
        - items_by_type: Count by item type
        - items_by_priority: Count by priority
        - average_age: Average age in days
        
    Raises:
        DataError: If query fails
    """
    query = """
        SELECT 
            COUNT(*) as total_items,
            COUNT(CASE WHEN status IN ('OPEN', 'TODO', 'IN_PROGRESS') THEN 1 END) as open_items,
            COUNT(CASE WHEN item_type = 'bug' THEN 1 END) as bug_count,
            COUNT(CASE WHEN item_type = 'feature' THEN 1 END) as feature_count,
            COUNT(CASE WHEN item_type = 'technical_debt' THEN 1 END) as tech_debt_count,
            AVG(age_days) as average_age
        FROM backlog_items
        WHERE project_id = %s
    """
    
    try:
        results = execute_query(query, (project_id,), fetch=True)
        
        if not results:
            return {
                'total_items': 0,
                'open_items': 0,
                'items_by_type': {'bug': 0, 'feature': 0, 'technical_debt': 0},
                'average_age': 0
            }
        
        result = results[0]
        
        return {
            'total_items': int(result.get('total_items', 0)),
            'open_items': int(result.get('open_items', 0)),
            'items_by_type': {
                'bug': int(result.get('bug_count', 0)),
                'feature': int(result.get('feature_count', 0)),
                'technical_debt': int(result.get('tech_debt_count', 0))
            },
            'average_age': float(result.get('average_age', 0)) if result.get('average_age') else 0
        }
        
    except Exception as e:
        raise DataError(
            f"Failed to query backlog metrics for project {project_id}: {str(e)}",
            data_source="Database"
        )


def query_historical_backlog(project_id: str, weeks: int = 4) -> List[Dict[str, Any]]:
    """
    Query historical backlog counts for growth rate calculation.
    
    Note: This is a simplified implementation. In production, you'd want
    to track backlog snapshots over time in a separate table.
    
    Args:
        project_id: Project ID to query
        weeks: Number of weeks of history to retrieve
        
    Returns:
        List of historical backlog counts by week
    """
    # For now, we'll return current metrics
    # In production, implement time-series tracking
    current_metrics = query_backlog_metrics(project_id)
    
    return [{
        'week_start': datetime.utcnow().date(),
        'open_items': current_metrics['open_items']
    }]


def calculate_team_completion_rate(project_id: str) -> float:
    """
    Calculate team's average weekly completion rate from sprint data.
    
    Args:
        project_id: Project ID to analyze
        
    Returns:
        Average weekly completion rate (points per week)
    """
    query = """
        SELECT 
            AVG(completed_points) as avg_completed_points,
            AVG(EXTRACT(EPOCH FROM (end_date - start_date)) / 86400 / 7) as avg_sprint_weeks
        FROM sprints
        WHERE project_id = %s
        AND completed_points IS NOT NULL
        AND end_date > start_date
    """
    
    try:
        results = execute_query(query, (project_id,), fetch=True)
        
        if not results or not results[0].get('avg_completed_points'):
            return 0
        
        result = results[0]
        avg_completed_points = float(result.get('avg_completed_points', 0))
        avg_sprint_weeks = float(result.get('avg_sprint_weeks', 2))  # Default 2 weeks
        
        if avg_sprint_weeks == 0:
            avg_sprint_weeks = 2
        
        # Calculate weekly completion rate
        weekly_rate = avg_completed_points / avg_sprint_weeks
        
        return round(weekly_rate, 2)
        
    except Exception as e:
        logger.error(f"Failed to calculate completion rate: {str(e)}")
        return 0


def calculate_backlog_growth_rate(
    historical_data: List[Dict[str, Any]]
) -> float:
    """
    Calculate weekly backlog growth rate.
    
    Args:
        historical_data: List of historical backlog counts
        
    Returns:
        Growth rate as percentage (e.g., 30.0 for 30% growth)
    """
    if len(historical_data) < 2:
        return 0
    
    # Get most recent and previous week
    current = historical_data[-1]['open_items']
    previous = historical_data[-2]['open_items']
    
    if previous == 0:
        return 0 if current == 0 else 100
    
    growth_rate = ((current - previous) / previous) * 100
    
    return round(growth_rate, 2)


def detect_backlog_growth_risk(
    backlog_metrics: Dict[str, Any],
    growth_rate: float,
    completion_rate: float
) -> Optional[Dict[str, Any]]:
    """
    Detect backlog growth risk based on metrics.
    
    Validates: Property 17 - Backlog Growth Risk Detection
    
    Detection criteria:
    - Backlog grows by more than 30% in a single week, OR
    - Backlog size exceeds 2x the team's average weekly completion rate
    
    Args:
        backlog_metrics: Current backlog metrics
        growth_rate: Weekly growth rate percentage
        completion_rate: Team's average weekly completion rate
        
    Returns:
        Risk alert dictionary if risk detected, None otherwise
    """
    open_items = backlog_metrics['open_items']
    
    # Check growth rate threshold
    rapid_growth = growth_rate > 30
    
    # Check backlog size vs completion rate
    excessive_backlog = False
    if completion_rate > 0:
        excessive_backlog = open_items > (2 * completion_rate)
    
    if rapid_growth or excessive_backlog:
        # Determine severity
        if growth_rate >= 50 or (completion_rate > 0 and open_items > 3 * completion_rate):
            severity = 'CRITICAL'
        elif growth_rate >= 40 or (completion_rate > 0 and open_items > 2.5 * completion_rate):
            severity = 'HIGH'
        elif growth_rate >= 30 or excessive_backlog:
            severity = 'MEDIUM'
        else:
            severity = 'LOW'
        
        # Build title
        if rapid_growth and excessive_backlog:
            title = f'Backlog Crisis: {growth_rate:.1f}% growth, {open_items} items vs {completion_rate:.1f} weekly capacity'
        elif rapid_growth:
            title = f'Rapid Backlog Growth: {growth_rate:.1f}% increase in one week'
        else:
            title = f'Excessive Backlog: {open_items} items vs {completion_rate:.1f} weekly capacity'
        
        return {
            'type': 'BACKLOG_GROWTH',
            'severity': severity,
            'title': title,
            'metrics': {
                'open_items': open_items,
                'total_items': backlog_metrics['total_items'],
                'growth_rate': growth_rate,
                'completion_rate': completion_rate,
                'items_by_type': backlog_metrics['items_by_type'],
                'average_age': backlog_metrics['average_age']
            },
            'detected_at': datetime.utcnow().isoformat()
        }
    
    return None


def analyze_backlog_risk(project_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    """
    Analyze backlog metrics and detect risks for a project.
    
    This is the main entry point for backlog risk analysis.
    
    Args:
        project_id: Project ID to analyze
        tenant_id: Tenant ID for context
        
    Returns:
        Risk alert dictionary if risk detected, None otherwise
        
    Raises:
        DataError: If analysis fails
    """
    try:
        # Query current backlog metrics
        backlog_metrics = query_backlog_metrics(project_id)
        
        if backlog_metrics['total_items'] == 0:
            logger.info(
                f"No backlog items found for project",
                extra={"project_id": project_id}
            )
            return None
        
        # Query historical data for growth rate
        historical_data = query_historical_backlog(project_id, weeks=4)
        growth_rate = calculate_backlog_growth_rate(historical_data)
        
        # Calculate team completion rate
        completion_rate = calculate_team_completion_rate(project_id)
        
        logger.info(
            f"Backlog metrics calculated",
            extra={
                "project_id": project_id,
                "open_items": backlog_metrics['open_items'],
                "growth_rate": growth_rate,
                "completion_rate": completion_rate
            }
        )
        
        # Detect backlog growth risk
        risk = detect_backlog_growth_risk(backlog_metrics, growth_rate, completion_rate)
        
        if risk:
            risk['project_id'] = project_id
            risk['tenant_id'] = tenant_id
            
            logger.info(
                f"Backlog growth risk detected",
                extra={
                    "project_id": project_id,
                    "severity": risk['severity'],
                    "growth_rate": growth_rate
                }
            )
        
        return risk
        
    except Exception as e:
        logger.error(
            f"Backlog risk analysis failed for project {project_id}",
            extra={"error": str(e)}
        )
        raise
