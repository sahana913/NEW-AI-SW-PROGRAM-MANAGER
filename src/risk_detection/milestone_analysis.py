"""Milestone slippage analysis for detecting milestone-related risks."""

from shared.logger import get_logger
from shared.errors import DataError
from shared.database import execute_query
import os
import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


logger = get_logger()


def query_active_milestones(project_id: str) -> List[Dict[str, Any]]:
    """
    Query active (non-completed) milestones for a project.

    Args:
        project_id: Project ID to query

    Returns:
        List of milestone dictionaries

    Raises:
        DataError: If query fails
    """
    query = """
        SELECT
            milestone_id::text,
            milestone_name,
            due_date,
            completion_percentage,
            status,
            source
        FROM milestones
        WHERE project_id = %s
        AND status != 'COMPLETED'
        ORDER BY due_date ASC
    """

    try:
        results = execute_query(query, (project_id,), fetch=True)

        # Convert Decimal to float
        for milestone in results:
            if milestone.get("completion_percentage") is not None:
                milestone["completion_percentage"] = float(
                    milestone["completion_percentage"]
                )

        return results

    except Exception as e:
        raise DataError(
            f"Failed to query milestones for project {project_id}: {str(e)}",
            data_source="Database",
        )


def query_milestone_dependencies(project_id: str, milestone_id: str) -> List[str]:
    """
    Query downstream milestones that depend on the given milestone.

    Note: This is a simplified implementation. In production, you'd want
    to track milestone dependencies explicitly.

    Args:
        project_id: Project ID
        milestone_id: Milestone ID to find dependencies for

    Returns:
        List of dependent milestone IDs
    """
    # For now, return empty list
    # In production, implement milestone dependency tracking
    return []


def calculate_milestone_metrics(milestone: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate completion and time metrics for a milestone.

    Validates: Property 18 - Milestone Slippage Risk Detection

    Args:
        milestone: Milestone dictionary with due_date and completion_percentage

    Returns:
        Dictionary with calculated metrics:
        - completion_percentage: Current completion percentage
        - time_remaining_days: Days until due date
        - time_elapsed_percentage: Percentage of time elapsed (estimated)
        - time_remaining_percentage: Percentage of time remaining
        - is_at_risk: Boolean indicating if milestone is at risk
    """
    completion_pct = milestone.get("completion_percentage", 0)
    due_date = milestone.get("due_date")

    if not due_date:
        return {
            "completion_percentage": completion_pct,
            "time_remaining_days": 0,
            "time_elapsed_percentage": 0,
            "time_remaining_percentage": 0,
            "is_at_risk": False,
        }

    # Convert due_date to date object if it's a string
    if isinstance(due_date, str):
        due_date = datetime.fromisoformat(due_date.replace("Z", "+00:00")).date()
    elif isinstance(due_date, datetime):
        due_date = due_date.date()

    today = date.today()

    # Calculate time remaining
    time_remaining_days = (due_date - today).days

    # Estimate total duration (assume milestone started 90 days before due date)
    # In production, track actual start dates
    estimated_total_days = 90
    time_elapsed_days = estimated_total_days - time_remaining_days

    if time_elapsed_days < 0:
        time_elapsed_days = 0

    # Calculate percentages
    if estimated_total_days > 0:
        time_elapsed_pct = (time_elapsed_days / estimated_total_days) * 100
        time_remaining_pct = (time_remaining_days / estimated_total_days) * 100
    else:
        time_elapsed_pct = 100
        time_remaining_pct = 0

    # Ensure percentages are within bounds
    time_elapsed_pct = max(0, min(100, time_elapsed_pct))
    time_remaining_pct = max(0, min(100, time_remaining_pct))

    # Check if at risk: < 70% complete with < 20% time remaining
    is_at_risk = completion_pct < 70 and time_remaining_pct < 20

    return {
        "completion_percentage": completion_pct,
        "time_remaining_days": time_remaining_days,
        "time_elapsed_percentage": round(time_elapsed_pct, 2),
        "time_remaining_percentage": round(time_remaining_pct, 2),
        "is_at_risk": is_at_risk,
    }


def estimate_delay_days(
    completion_pct: float, time_remaining_days: int, project_id: str
) -> int:
    """
    Estimate delay in days based on current progress and velocity.

    Args:
        completion_pct: Current completion percentage
        time_remaining_days: Days until due date
        project_id: Project ID for velocity lookup

    Returns:
        Estimated delay in days
    """
    if completion_pct >= 100:
        return 0

    if time_remaining_days <= 0:
        # Already past due date
        return abs(time_remaining_days)

    # Calculate required daily progress rate
    remaining_work = 100 - completion_pct
    required_daily_rate = (
        remaining_work / time_remaining_days if time_remaining_days > 0 else 0
    )

    # Query recent velocity to estimate actual daily rate
    # Simplified: assume 1% per day based on typical sprint velocity
    # In production, calculate from actual sprint data
    estimated_daily_rate = 1.0

    if estimated_daily_rate >= required_daily_rate:
        return 0  # On track

    # Calculate additional days needed
    if estimated_daily_rate > 0:
        days_needed = remaining_work / estimated_daily_rate
        delay_days = int(days_needed - time_remaining_days)
        return max(0, delay_days)

    return int(remaining_work)  # Worst case: 1 day per percentage point


def detect_milestone_slippage_risk(
    milestone: Dict[str, Any], metrics: Dict[str, Any], project_id: str
) -> Optional[Dict[str, Any]]:
    """
    Detect milestone slippage risk based on completion and time metrics.

    Validates: Property 18 - Milestone Slippage Risk Detection

    Detection criteria:
    - Milestone is less than 70% complete with less than 20% time remaining

    Args:
        milestone: Milestone dictionary
        metrics: Calculated milestone metrics
        project_id: Project ID for context

    Returns:
        Risk alert dictionary if risk detected, None otherwise
    """
    if not metrics["is_at_risk"]:
        return None

    completion_pct = metrics["completion_percentage"]
    time_remaining_pct = metrics["time_remaining_percentage"]
    time_remaining_days = metrics["time_remaining_days"]

    # Estimate delay
    estimated_delay_days = estimate_delay_days(
        completion_pct, time_remaining_days, project_id
    )

    # Determine severity
    if completion_pct < 50 and time_remaining_pct < 10:
        severity = "CRITICAL"
    elif completion_pct < 60 and time_remaining_pct < 15:
        severity = "HIGH"
    elif completion_pct < 70 and time_remaining_pct < 20:
        severity = "MEDIUM"
    else:
        severity = "LOW"

    # Query dependent milestones
    dependent_milestones = query_milestone_dependencies(
        project_id, milestone["milestone_id"]
    )

    return {
        "type": "MILESTONE_SLIPPAGE",
        "severity": severity,
        "title": f"Milestone at Risk: {milestone['milestone_name']}",
        "milestone_id": milestone["milestone_id"],
        "milestone_name": milestone["milestone_name"],
        "metrics": {
            "completion_percentage": completion_pct,
            "time_remaining_days": time_remaining_days,
            "time_remaining_percentage": time_remaining_pct,
            "estimated_delay_days": estimated_delay_days,
            "due_date": str(milestone["due_date"]),
            "dependent_milestones": dependent_milestones,
        },
        "detected_at": datetime.utcnow().isoformat(),
    }


def analyze_milestone_risks(project_id: str, tenant_id: str) -> List[Dict[str, Any]]:
    """
    Analyze all milestones and detect slippage risks for a project.

    This is the main entry point for milestone risk analysis.

    Args:
        project_id: Project ID to analyze
        tenant_id: Tenant ID for context

    Returns:
        List of risk alert dictionaries (may be empty)

    Raises:
        DataError: If analysis fails
    """
    try:
        # Query active milestones
        milestones = query_active_milestones(project_id)

        if not milestones:
            logger.info(
                f"No active milestones found for project",
                extra={"project_id": project_id},
            )
            return []

        risks = []

        # Analyze each milestone
        for milestone in milestones:
            # Calculate metrics
            metrics = calculate_milestone_metrics(milestone)

            # Detect risk
            risk = detect_milestone_slippage_risk(milestone, metrics, project_id)

            if risk:
                risk["project_id"] = project_id
                risk["tenant_id"] = tenant_id
                risks.append(risk)

                logger.info(
                    f"Milestone slippage risk detected",
                    extra={
                        "project_id": project_id,
                        "milestone_name": milestone["milestone_name"],
                        "severity": risk["severity"],
                        "completion": metrics["completion_percentage"],
                        "time_remaining": metrics["time_remaining_percentage"],
                    },
                )

        return risks

    except Exception as e:
        logger.error(
            f"Milestone risk analysis failed for project {project_id}",
            extra={"error": str(e)},
        )
        raise
