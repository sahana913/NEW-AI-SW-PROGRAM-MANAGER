"""Velocity trend analysis for detecting velocity decline risks."""

import sys
import os
from typing import Dict, List, Any, Optional
from datetime import datetime
from decimal import Decimal

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.database import execute_query
from shared.logger import get_logger
from shared.errors import DataError

logger = get_logger()


def query_last_sprints(project_id: str, limit: int = 4) -> List[Dict[str, Any]]:
    """
    Query the last N sprints for a project ordered by start date descending.
    
    Validates: Property 15 - Velocity Trend Calculation
    
    Args:
        project_id: Project ID to query
        limit: Number of sprints to retrieve (default 4)
        
    Returns:
        List of sprint dictionaries with velocity data
        
    Raises:
        DataError: If query fails
    """
    query = """
        SELECT 
            sprint_id::text,
            sprint_name,
            start_date,
            end_date,
            velocity,
            completed_points,
            planned_points,
            completion_rate
        FROM sprints
        WHERE project_id = %s
        ORDER BY start_date DESC
        LIMIT %s
    """
    
    try:
        results = execute_query(query, (project_id, limit), fetch=True)
        
        # Convert Decimal to float for easier calculations
        for sprint in results:
            if sprint.get('velocity') is not None:
                sprint['velocity'] = float(sprint['velocity'])
            if sprint.get('completed_points') is not None:
                sprint['completed_points'] = float(sprint['completed_points'])
            if sprint.get('planned_points') is not None:
                sprint['planned_points'] = float(sprint['planned_points'])
            if sprint.get('completion_rate') is not None:
                sprint['completion_rate'] = float(sprint['completion_rate'])
        
        # Reverse to get chronological order (oldest first)
        return list(reversed(results))
        
    except Exception as e:
        raise DataError(
            f"Failed to query sprints for project {project_id}: {str(e)}",
            data_source="Database"
        )


def calculate_velocity_trend(sprints: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate velocity trend and moving average from sprint data.
    
    Validates: Property 15 - Velocity Trend Calculation
    
    Args:
        sprints: List of sprint dictionaries (chronological order)
        
    Returns:
        Dictionary with velocity metrics:
        - moving_average: 4-sprint moving average
        - current_velocity: Most recent sprint velocity
        - previous_velocity: Second most recent sprint velocity
        - trend: 'IMPROVING', 'STABLE', or 'DECLINING'
        - decline_percentage: Percentage decline (if declining)
        - historical_data: List of velocity values
    """
    if not sprints:
        return {
            'moving_average': 0,
            'current_velocity': 0,
            'previous_velocity': 0,
            'trend': 'STABLE',
            'decline_percentage': 0,
            'historical_data': []
        }
    
    # Extract velocity values
    velocities = [s.get('velocity', 0) for s in sprints if s.get('velocity') is not None]
    
    if not velocities:
        return {
            'moving_average': 0,
            'current_velocity': 0,
            'previous_velocity': 0,
            'trend': 'STABLE',
            'decline_percentage': 0,
            'historical_data': []
        }
    
    # Calculate moving average
    moving_average = sum(velocities) / len(velocities)
    
    # Get current and previous velocities
    current_velocity = velocities[-1] if len(velocities) >= 1 else 0
    previous_velocity = velocities[-2] if len(velocities) >= 2 else current_velocity
    
    # Determine trend
    if current_velocity > moving_average * 1.05:  # 5% threshold
        trend = 'IMPROVING'
    elif current_velocity < moving_average * 0.95:  # 5% threshold
        trend = 'DECLINING'
    else:
        trend = 'STABLE'
    
    # Calculate decline percentage
    decline_percentage = 0
    if moving_average > 0:
        decline_percentage = ((moving_average - current_velocity) / moving_average) * 100
    
    return {
        'moving_average': round(moving_average, 2),
        'current_velocity': round(current_velocity, 2),
        'previous_velocity': round(previous_velocity, 2),
        'trend': trend,
        'decline_percentage': round(decline_percentage, 2),
        'historical_data': [round(v, 2) for v in velocities]
    }


def detect_velocity_decline(
    sprints: List[Dict[str, Any]],
    velocity_metrics: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Detect velocity decline risk based on sprint data.
    
    Validates: Property 16 - Velocity Decline Risk Detection
    
    Detection criteria:
    - Velocity decreases by more than 20% over 2 consecutive sprints
    
    Args:
        sprints: List of sprint dictionaries (chronological order)
        velocity_metrics: Velocity trend metrics from calculate_velocity_trend
        
    Returns:
        Risk alert dictionary if risk detected, None otherwise
    """
    if len(sprints) < 2:
        return None
    
    velocities = [s.get('velocity', 0) for s in sprints if s.get('velocity') is not None]
    
    if len(velocities) < 2:
        return None
    
    # Check for decline over last 2 sprints
    current_velocity = velocities[-1]
    previous_velocity = velocities[-2]
    
    if previous_velocity == 0:
        return None
    
    decline_percentage = ((previous_velocity - current_velocity) / previous_velocity) * 100
    
    # Detect if decline > 20% over 2 consecutive sprints
    if decline_percentage > 20:
        # Determine severity based on decline percentage
        if decline_percentage >= 40:
            severity = 'CRITICAL'
        elif decline_percentage >= 30:
            severity = 'HIGH'
        elif decline_percentage >= 20:
            severity = 'MEDIUM'
        else:
            severity = 'LOW'
        
        return {
            'type': 'VELOCITY_DECLINE',
            'severity': severity,
            'title': f'Velocity Decline Detected: {decline_percentage:.1f}% drop',
            'metrics': {
                'current_velocity': current_velocity,
                'previous_velocity': previous_velocity,
                'moving_average': velocity_metrics['moving_average'],
                'decline_percentage': decline_percentage,
                'trend': velocity_metrics['trend'],
                'historical_data': velocity_metrics['historical_data']
            },
            'detected_at': datetime.utcnow().isoformat()
        }
    
    return None


def analyze_velocity_risk(project_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    """
    Analyze velocity trends and detect risks for a project.
    
    This is the main entry point for velocity risk analysis.
    
    Args:
        project_id: Project ID to analyze
        tenant_id: Tenant ID for context
        
    Returns:
        Risk alert dictionary if risk detected, None otherwise
        
    Raises:
        DataError: If analysis fails
    """
    try:
        # Query last 4 sprints
        sprints = query_last_sprints(project_id, limit=4)
        
        if len(sprints) < 2:
            logger.info(
                f"Insufficient sprint data for velocity analysis",
                extra={"project_id": project_id, "sprint_count": len(sprints)}
            )
            return None
        
        # Calculate velocity trend
        velocity_metrics = calculate_velocity_trend(sprints)
        
        logger.info(
            f"Velocity metrics calculated",
            extra={
                "project_id": project_id,
                "metrics": velocity_metrics
            }
        )
        
        # Detect velocity decline risk
        risk = detect_velocity_decline(sprints, velocity_metrics)
        
        if risk:
            risk['project_id'] = project_id
            risk['tenant_id'] = tenant_id
            
            logger.info(
                f"Velocity decline risk detected",
                extra={
                    "project_id": project_id,
                    "severity": risk['severity'],
                    "decline_percentage": risk['metrics']['decline_percentage']
                }
            )
        
        return risk
        
    except Exception as e:
        logger.error(
            f"Velocity risk analysis failed for project {project_id}",
            extra={"error": str(e)}
        )
        raise
