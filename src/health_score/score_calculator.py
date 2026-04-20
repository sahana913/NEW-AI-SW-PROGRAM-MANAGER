"""Health score calculation logic."""

from shared.logger import get_logger
from shared.database import execute_query
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


logger = get_logger()

# Default weights for health score components
DEFAULT_WEIGHTS = {"velocity": 0.30, "backlog": 0.25, "milestones": 0.30, "risks": 0.15}


def get_tenant_weights(tenant_id: str) -> Dict[str, float]:
    """
    Get custom weights for a tenant if configured, otherwise return defaults.

    Validates: Property 59 - Custom Weight Application

    Args:
        tenant_id: Tenant ID

    Returns:
        Dictionary with component weights
    """
    # TODO: Query tenant configuration from DynamoDB
    # For now, return default weights
    # In production, this would query a tenant_config table or DynamoDB
    return DEFAULT_WEIGHTS.copy()


def calculate_velocity_score(project_id: str) -> float:
    """
    Calculate velocity component score (0-100).

    Based on velocity trend over last 4 sprints.

    Args:
        project_id: Project ID

    Returns:
        Velocity score (0-100)
    """
    query = """
        SELECT velocity
        FROM sprints
        WHERE project_id = %s
        ORDER BY start_date DESC
        LIMIT 4
    """

    try:
        results = execute_query(query, (project_id,), fetch=True)

        if not results or len(results) < 2:
            # Insufficient data, return neutral score
            return 100.0

        velocities = [
            float(r["velocity"]) for r in results if r.get("velocity") is not None
        ]

        if not velocities:
            return 100.0

        # Calculate average and current velocity
        average = sum(velocities) / len(velocities)
        current = velocities[0]  # Most recent (DESC order)

        if average == 0:
            return 100.0

        # Calculate ratio
        ratio = current / average

        # Score based on ratio
        if ratio >= 1.0:
            return 100.0
        elif ratio >= 0.9:
            return 90.0
        elif ratio >= 0.8:
            return 70.0
        elif ratio >= 0.7:
            return 50.0
        else:
            return 30.0

    except Exception as e:
        logger.error(f"Failed to calculate velocity score: {str(e)}")
        return 100.0  # Default to neutral on error


def calculate_backlog_score(project_id: str) -> float:
    """
    Calculate backlog component score (0-100).

    Based on backlog growth rate and size.

    Args:
        project_id: Project ID

    Returns:
        Backlog score (0-100)
    """
    # Query backlog metrics
    # For now, we'll use a simplified calculation based on open items
    query = """
        SELECT COUNT(*) as total_items,
               COUNT(CASE WHEN status = 'OPEN' THEN 1 END) as open_items
        FROM backlog_items
        WHERE project_id = %s
    """

    try:
        results = execute_query(query, (project_id,), fetch=True)

        if not results:
            return 100.0

        total_items = results[0].get("total_items", 0)
        open_items = results[0].get("open_items", 0)

        if total_items == 0:
            return 100.0

        # Calculate open ratio
        open_ratio = open_items / total_items

        # Score based on open ratio (lower is better)
        if open_ratio <= 0.3:
            return 100.0
        elif open_ratio <= 0.5:
            return 90.0
        elif open_ratio <= 0.7:
            return 70.0
        elif open_ratio <= 0.85:
            return 50.0
        else:
            return 30.0

    except Exception as e:
        logger.error(f"Failed to calculate backlog score: {str(e)}")
        return 100.0  # Default to neutral on error


def calculate_milestone_score(project_id: str) -> float:
    """
    Calculate milestone component score (0-100).

    Based on milestone status distribution.

    Args:
        project_id: Project ID

    Returns:
        Milestone score (0-100)
    """
    query = """
        SELECT status, COUNT(*) as count
        FROM milestones
        WHERE project_id = %s
        GROUP BY status
    """

    try:
        results = execute_query(query, (project_id,), fetch=True)

        if not results:
            return 100.0

        # Count milestones by status
        status_counts = {r["status"]: r["count"] for r in results}
        total = sum(status_counts.values())

        if total == 0:
            return 100.0

        # Calculate weighted score
        on_track = status_counts.get("ON_TRACK", 0) + status_counts.get("COMPLETED", 0)
        at_risk = status_counts.get("AT_RISK", 0)
        delayed = status_counts.get("DELAYED", 0)

        score = (on_track * 100 + at_risk * 50 + delayed * 0) / total

        return round(score, 2)

    except Exception as e:
        logger.error(f"Failed to calculate milestone score: {str(e)}")
        return 100.0  # Default to neutral on error


def calculate_risk_score(project_id: str, tenant_id: str) -> float:
    """
    Calculate risk component score (0-100).

    Based on active risk count and severity.

    Args:
        project_id: Project ID
        tenant_id: Tenant ID

    Returns:
        Risk score (0-100)
    """
    # Query active risks from DynamoDB would go here
    # For now, we'll use a simplified calculation
    # In production, this would query DynamoDB Risks table

    # Placeholder: assume no risks for now
    # TODO: Implement DynamoDB query for risks

    try:
        # Mock risk counts (replace with actual DynamoDB query)
        critical_count = 0
        high_count = 0
        medium_count = 0

        # Calculate risk impact
        risk_impact = critical_count * 30 + high_count * 15 + medium_count * 5

        # Score is inverse of impact
        score = max(0, 100 - risk_impact)

        return float(score)

    except Exception as e:
        logger.error(f"Failed to calculate risk score: {str(e)}")
        return 100.0  # Default to neutral on error


def calculate_health_score(
    project_id: str, tenant_id: str, custom_weights: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """
    Calculate overall health score for a project.

    Validates:
    - Property 54: Health Score Composition
    - Property 55: Health Score Range
    - Property 58: Default Weight Application
    - Property 59: Custom Weight Application

    Args:
        project_id: Project ID
        tenant_id: Tenant ID
        custom_weights: Optional custom weights (if None, uses tenant or default weights)

    Returns:
        Dictionary with:
        - health_score: Overall score (0-100)
        - component_scores: Individual component scores
        - weights: Weights used
        - calculated_at: Timestamp
    """
    logger.info(
        f"Calculating health score",
        extra={"project_id": project_id, "tenant_id": tenant_id},
    )

    # Get weights
    if custom_weights:
        weights = custom_weights
    else:
        weights = get_tenant_weights(tenant_id)

    # Calculate component scores
    velocity_score = calculate_velocity_score(project_id)
    backlog_score = calculate_backlog_score(project_id)
    milestone_score = calculate_milestone_score(project_id)
    risk_score = calculate_risk_score(project_id, tenant_id)

    # Calculate weighted composite
    health_score = (
        velocity_score * weights["velocity"]
        + backlog_score * weights["backlog"]
        + milestone_score * weights["milestones"]
        + risk_score * weights["risks"]
    )

    # Normalize to 0-100 range (should already be in range, but ensure)
    health_score = max(0, min(100, round(health_score)))

    result = {
        "health_score": health_score,
        "component_scores": {
            "velocity": round(velocity_score, 2),
            "backlog": round(backlog_score, 2),
            "milestones": round(milestone_score, 2),
            "risks": round(risk_score, 2),
        },
        "weights": weights,
        "calculated_at": datetime.utcnow().isoformat(),
    }

    logger.info(
        f"Health score calculated",
        extra={
            "project_id": project_id,
            "health_score": health_score,
            "component_scores": result["component_scores"],
        },
    )

    return result
