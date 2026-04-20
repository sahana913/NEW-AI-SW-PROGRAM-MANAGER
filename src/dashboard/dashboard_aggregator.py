"""Dashboard data aggregation logic."""

from shared.logger import get_logger
from shared.database import execute_query
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import boto3

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


logger = get_logger()

# DynamoDB client (initialized lazily)
_dynamodb = None


def get_dynamodb():
    """Get or create DynamoDB client."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb


def get_dashboard_overview(
    tenant_id: str, project_ids: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Get dashboard overview with project summaries, portfolio health, risks, and milestones.

    Validates: Requirement 20.1, 20.2, 20.3

    Args:
        tenant_id: Tenant ID
        project_ids: Optional list of project IDs to filter

    Returns:
        Dictionary with dashboard overview data
    """
    logger.info(
        f"Aggregating dashboard overview",
        extra={"tenant_id": tenant_id, "project_ids": project_ids},
    )

    # Get project summaries
    projects = get_project_summaries(tenant_id, project_ids)

    # Calculate portfolio health
    portfolio_health = calculate_portfolio_health(projects)

    # Get recent risks
    recent_risks = get_recent_risks(tenant_id, project_ids, limit=10)

    # Get upcoming milestones
    upcoming_milestones = get_upcoming_milestones(tenant_id, project_ids, days_ahead=14)

    return {
        "projects": projects,
        "portfolioHealth": portfolio_health,
        "recentRisks": recent_risks,
        "upcomingMilestones": upcoming_milestones,
        "lastUpdated": datetime.utcnow().isoformat(),
    }


def get_project_summaries(
    tenant_id: str, project_ids: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Get project summaries with health scores and RAG status.

    Args:
        tenant_id: Tenant ID
        project_ids: Optional list of project IDs to filter

    Returns:
        List of project summary dictionaries
    """
    # Build query
    if project_ids:
        placeholders = ",".join(["%s"] * len(project_ids))
        query = f"""
            SELECT
                p.project_id::text,
                p.project_name,
                p.source
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
                p.source
            FROM projects p
            WHERE p.tenant_id = %s
            ORDER BY p.project_name
        """
        params = (tenant_id,)

    try:
        projects = execute_query(query, params, fetch=True)

        # Enrich with health scores and RAG status
        for project in projects:
            project_id = project["project_id"]

            # Get latest health score
            health_data = get_latest_health_score(project_id, tenant_id)
            if health_data:
                project["healthScore"] = health_data.get("health_score", 0)
                project["ragStatus"] = determine_rag_status(
                    health_data.get("health_score", 0)
                )
                project["trend"] = calculate_trend(project_id, tenant_id)
            else:
                project["healthScore"] = 0
                project["ragStatus"] = "UNKNOWN"
                project["trend"] = "STABLE"

            # Get active risk count
            project["activeRisks"] = get_active_risk_count(project_id, tenant_id)

            # Get next milestone
            project["nextMilestone"] = get_next_milestone(project_id)

        return projects

    except Exception as e:
        logger.error(f"Failed to get project summaries: {str(e)}")
        return []


def get_latest_health_score(
    project_id: str, tenant_id: str
) -> Optional[Dict[str, Any]]:
    """
    Get the most recent health score for a project.

    Args:
        project_id: Project ID
        tenant_id: Tenant ID

    Returns:
        Latest health score data or None
    """
    query = """
        SELECT
            health_score,
            velocity_score,
            backlog_score,
            milestone_score,
            risk_score,
            calculated_at
        FROM health_score_history
        WHERE project_id = %s AND tenant_id = %s
        ORDER BY calculated_at DESC
        LIMIT 1
    """

    try:
        results = execute_query(query, (project_id, tenant_id), fetch=True)
        return results[0] if results else None
    except Exception as e:
        logger.error(f"Failed to get latest health score: {str(e)}")
        return None


def determine_rag_status(health_score: int) -> str:
    """
    Determine RAG status based on health score.

    Args:
        health_score: Health score (0-100)

    Returns:
        RAG status: GREEN, AMBER, or RED
    """
    if health_score >= 80:
        return "GREEN"
    elif health_score >= 60:
        return "AMBER"
    else:
        return "RED"


def calculate_trend(project_id: str, tenant_id: str) -> str:
    """
    Calculate health score trend (IMPROVING, STABLE, DECLINING).

    Args:
        project_id: Project ID
        tenant_id: Tenant ID

    Returns:
        Trend indicator
    """
    query = """
        SELECT health_score
        FROM health_score_history
        WHERE project_id = %s AND tenant_id = %s
        ORDER BY calculated_at DESC
        LIMIT 3
    """

    try:
        results = execute_query(query, (project_id, tenant_id), fetch=True)

        if len(results) < 2:
            return "STABLE"

        scores = [r["health_score"] for r in results]

        # Compare most recent to previous
        if scores[0] > scores[1] + 5:
            return "IMPROVING"
        elif scores[0] < scores[1] - 5:
            return "DECLINING"
        else:
            return "STABLE"

    except Exception as e:
        logger.error(f"Failed to calculate trend: {str(e)}")
        return "STABLE"


def get_active_risk_count(project_id: str, tenant_id: str) -> int:
    """
    Get count of active risks for a project.

    Args:
        project_id: Project ID
        tenant_id: Tenant ID

    Returns:
        Count of active risks
    """
    # TODO: Query DynamoDB Risks table
    # For now, return 0 as placeholder
    return 0


def get_next_milestone(project_id: str) -> Optional[Dict[str, Any]]:
    """
    Get the next upcoming milestone for a project.

    Args:
        project_id: Project ID

    Returns:
        Next milestone data or None
    """
    query = """
        SELECT
            milestone_name as name,
            due_date as "dueDate",
            completion_percentage as "completionPercentage"
        FROM milestones
        WHERE project_id = %s AND due_date >= CURRENT_DATE
        ORDER BY due_date ASC
        LIMIT 1
    """

    try:
        results = execute_query(query, (project_id,), fetch=True)
        if results:
            milestone = results[0]
            # Convert date to ISO string
            if milestone.get("dueDate"):
                milestone["dueDate"] = milestone["dueDate"].isoformat()
            # Convert Decimal to float
            if milestone.get("completionPercentage") is not None:
                milestone["completionPercentage"] = float(
                    milestone["completionPercentage"]
                )
            return milestone
        return None
    except Exception as e:
        logger.error(f"Failed to get next milestone: {str(e)}")
        return None


def calculate_portfolio_health(projects: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate portfolio-level health metrics.

    Args:
        projects: List of project summaries

    Returns:
        Portfolio health metrics
    """
    if not projects:
        return {
            "overallHealthScore": 0,
            "overallRagStatus": "UNKNOWN",
            "projectsByStatus": {"red": 0, "amber": 0, "green": 0},
            "totalActiveRisks": 0,
            "criticalRisks": 0,
        }

    # Calculate average health score
    health_scores = [p.get("healthScore", 0) for p in projects]
    overall_health_score = (
        sum(health_scores) // len(health_scores) if health_scores else 0
    )

    # Count projects by RAG status
    projects_by_status = {
        "red": sum(1 for p in projects if p.get("ragStatus") == "RED"),
        "amber": sum(1 for p in projects if p.get("ragStatus") == "AMBER"),
        "green": sum(1 for p in projects if p.get("ragStatus") == "GREEN"),
    }

    # Sum active risks
    total_active_risks = sum(p.get("activeRisks", 0) for p in projects)

    return {
        "overallHealthScore": overall_health_score,
        "overallRagStatus": determine_rag_status(overall_health_score),
        "projectsByStatus": projects_by_status,
        "totalActiveRisks": total_active_risks,
        "criticalRisks": 0,  # TODO: Query DynamoDB for critical risks
    }


def get_recent_risks(
    tenant_id: str, project_ids: Optional[List[str]] = None, limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get recent risk alerts.

    Args:
        tenant_id: Tenant ID
        project_ids: Optional list of project IDs to filter
        limit: Maximum number of risks to return

    Returns:
        List of recent risks
    """
    # TODO: Query DynamoDB Risks table
    # For now, return empty list as placeholder
    return []


def get_upcoming_milestones(
    tenant_id: str, project_ids: Optional[List[str]] = None, days_ahead: int = 14
) -> List[Dict[str, Any]]:
    """
    Get upcoming milestones.

    Args:
        tenant_id: Tenant ID
        project_ids: Optional list of project IDs to filter
        days_ahead: Number of days to look ahead

    Returns:
        List of upcoming milestones
    """
    end_date = datetime.now().date() + timedelta(days=days_ahead)

    if project_ids:
        placeholders = ",".join(["%s"] * len(project_ids))
        query = f"""
            SELECT
                m.milestone_id::text,
                m.milestone_name as name,
                m.due_date as "dueDate",
                m.completion_percentage as "completionPercentage",
                m.status,
                p.project_id::text,
                p.project_name as "projectName"
            FROM milestones m
            JOIN projects p ON m.project_id = p.project_id
            WHERE p.tenant_id = %s
                AND m.due_date >= CURRENT_DATE
                AND m.due_date <= %s
                AND p.project_id::text IN ({placeholders})
            ORDER BY m.due_date ASC
            LIMIT 20
        """
        params = (tenant_id, end_date, *project_ids)
    else:
        query = """
            SELECT
                m.milestone_id::text,
                m.milestone_name as name,
                m.due_date as "dueDate",
                m.completion_percentage as "completionPercentage",
                m.status,
                p.project_id::text,
                p.project_name as "projectName"
            FROM milestones m
            JOIN projects p ON m.project_id = p.project_id
            WHERE p.tenant_id = %s
                AND m.due_date >= CURRENT_DATE
                AND m.due_date <= %s
            ORDER BY m.due_date ASC
            LIMIT 20
        """
        params = (tenant_id, end_date)

    try:
        results = execute_query(query, params, fetch=True)

        # Convert dates and decimals
        for milestone in results:
            if milestone.get("dueDate"):
                milestone["dueDate"] = milestone["dueDate"].isoformat()
            if milestone.get("completionPercentage") is not None:
                milestone["completionPercentage"] = float(
                    milestone["completionPercentage"]
                )

        return results

    except Exception as e:
        logger.error(f"Failed to get upcoming milestones: {str(e)}")
        return []


def get_project_dashboard(tenant_id: str, project_id: str) -> Optional[Dict[str, Any]]:
    """
    Get detailed dashboard for a specific project.

    Validates: Requirement 20.1, 20.4, 20.5

    Args:
        tenant_id: Tenant ID
        project_id: Project ID

    Returns:
        Project dashboard data or None if project not found
    """
    logger.info(
        f"Aggregating project dashboard",
        extra={"tenant_id": tenant_id, "project_id": project_id},
    )

    # Get project details
    query = """
        SELECT
            project_id::text,
            project_name,
            source,
            last_sync_at
        FROM projects
        WHERE project_id = %s AND tenant_id = %s
    """

    try:
        results = execute_query(query, (project_id, tenant_id), fetch=True)

        if not results:
            return None

        project = results[0]

        # Get health score and RAG status
        health_data = get_latest_health_score(project_id, tenant_id)
        if health_data:
            project["healthScore"] = health_data.get("health_score", 0)
            project["ragStatus"] = determine_rag_status(
                health_data.get("health_score", 0)
            )
        else:
            project["healthScore"] = 0
            project["ragStatus"] = "UNKNOWN"

        # Get velocity trend
        project["velocityTrend"] = get_velocity_trend(project_id)

        # Get backlog trend
        project["backlogTrend"] = get_backlog_trend(project_id)

        # Get milestone timeline
        project["milestoneTimeline"] = get_milestone_timeline(project_id)

        # Get active risks
        project["risks"] = get_project_risks(project_id, tenant_id)

        # Get predictions
        project["predictions"] = get_project_predictions(project_id, tenant_id)

        # Convert last_sync_at to ISO string
        if project.get("last_sync_at"):
            project["last_sync_at"] = project["last_sync_at"].isoformat()

        return project

    except Exception as e:
        logger.error(f"Failed to get project dashboard: {str(e)}")
        return None


def get_velocity_trend(project_id: str) -> Dict[str, Any]:
    """
    Get velocity trend chart data.

    Args:
        project_id: Project ID

    Returns:
        Chart data with labels and values
    """
    query = """
        SELECT
            sprint_name,
            velocity,
            start_date
        FROM sprints
        WHERE project_id = %s
        ORDER BY start_date DESC
        LIMIT 10
    """

    try:
        results = execute_query(query, (project_id,), fetch=True)

        if not results:
            return {"labels": [], "values": [], "trend": "STABLE"}

        # Reverse to get chronological order
        results = list(reversed(results))

        labels = [r["sprint_name"] for r in results]
        values = [
            float(r["velocity"]) if r.get("velocity") is not None else 0
            for r in results
        ]

        # Calculate trend
        if len(values) >= 2:
            if values[-1] > values[-2] * 1.1:
                trend = "IMPROVING"
            elif values[-1] < values[-2] * 0.9:
                trend = "DECLINING"
            else:
                trend = "STABLE"
        else:
            trend = "STABLE"

        return {"labels": labels, "values": values, "trend": trend}

    except Exception as e:
        logger.error(f"Failed to get velocity trend: {str(e)}")
        return {"labels": [], "values": [], "trend": "STABLE"}


def get_backlog_trend(project_id: str) -> Dict[str, Any]:
    """
    Get backlog trend chart data.

    Args:
        project_id: Project ID

    Returns:
        Chart data with labels and values
    """
    # TODO: Implement backlog trend calculation
    # For now, return placeholder data
    return {"labels": [], "values": [], "trend": "STABLE"}


def get_milestone_timeline(project_id: str) -> Dict[str, Any]:
    """
    Get milestone timeline data.

    Args:
        project_id: Project ID

    Returns:
        Milestone timeline data
    """
    query = """
        SELECT
            milestone_name as name,
            due_date as "dueDate",
            completion_percentage as "completionPercentage",
            status
        FROM milestones
        WHERE project_id = %s
        ORDER BY due_date ASC
    """

    try:
        results = execute_query(query, (project_id,), fetch=True)

        # Convert dates and decimals
        milestones = []
        for milestone in results:
            if milestone.get("dueDate"):
                milestone["dueDate"] = milestone["dueDate"].isoformat()
            if milestone.get("completionPercentage") is not None:
                milestone["completionPercentage"] = float(
                    milestone["completionPercentage"]
                )
            milestones.append(milestone)

        return {"milestones": milestones}

    except Exception as e:
        logger.error(f"Failed to get milestone timeline: {str(e)}")
        return {"milestones": []}


def get_project_risks(project_id: str, tenant_id: str) -> List[Dict[str, Any]]:
    """
    Get active risks for a project.

    Args:
        project_id: Project ID
        tenant_id: Tenant ID

    Returns:
        List of active risks
    """
    # TODO: Query DynamoDB Risks table
    # For now, return empty list as placeholder
    return []


def get_project_predictions(project_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Get latest predictions for a project.

    Args:
        project_id: Project ID
        tenant_id: Tenant ID

    Returns:
        Prediction data
    """
    # TODO: Query DynamoDB Predictions table
    # For now, return placeholder data
    return {"delayProbability": 0, "workloadImbalance": 0}


def get_metrics(
    tenant_id: str, project_id: str, metric_type: str, time_range: str
) -> Optional[Dict[str, Any]]:
    """
    Get metrics data for a project.

    Validates: Requirement 20.6

    Args:
        tenant_id: Tenant ID
        project_id: Project ID
        metric_type: velocity, backlog, or utilization
        time_range: 7d, 30d, 90d, or all

    Returns:
        Metrics data with chart data and statistics
    """
    logger.info(
        f"Getting metrics",
        extra={
            "tenant_id": tenant_id,
            "project_id": project_id,
            "metric_type": metric_type,
            "time_range": time_range,
        },
    )

    # Calculate date range
    if time_range == "all":
        start_date = None
    else:
        days = int(time_range.rstrip("d"))
        start_date = datetime.now().date() - timedelta(days=days)

    if metric_type == "velocity":
        return get_velocity_metrics(project_id, start_date)
    elif metric_type == "backlog":
        return get_backlog_metrics(project_id, start_date)
    elif metric_type == "utilization":
        return get_utilization_metrics(project_id, start_date)

    return None


def get_velocity_metrics(project_id: str, start_date: Optional[Any]) -> Dict[str, Any]:
    """
    Get velocity metrics.

    Args:
        project_id: Project ID
        start_date: Start date for filtering (None for all)

    Returns:
        Velocity metrics data
    """
    if start_date:
        query = """
            SELECT
                sprint_name,
                velocity,
                start_date
            FROM sprints
            WHERE project_id = %s AND start_date >= %s
            ORDER BY start_date ASC
        """
        params = (project_id, start_date)
    else:
        query = """
            SELECT
                sprint_name,
                velocity,
                start_date
            FROM sprints
            WHERE project_id = %s
            ORDER BY start_date ASC
        """
        params = (project_id,)

    try:
        results = execute_query(query, params, fetch=True)

        if not results:
            return None

        labels = [r["sprint_name"] for r in results]
        values = [
            float(r["velocity"]) if r.get("velocity") is not None else 0
            for r in results
        ]

        # Calculate statistics
        current = values[-1] if values else 0
        average = sum(values) / len(values) if values else 0
        min_val = min(values) if values else 0
        max_val = max(values) if values else 0

        # Calculate trend
        if len(values) >= 2:
            if values[-1] > values[-2] * 1.1:
                trend = "IMPROVING"
            elif values[-1] < values[-2] * 0.9:
                trend = "DECLINING"
            else:
                trend = "STABLE"
        else:
            trend = "STABLE"

        return {
            "metricType": "velocity",
            "data": {"labels": labels, "values": values, "trend": trend},
            "statistics": {
                "current": round(current, 2),
                "average": round(average, 2),
                "min": round(min_val, 2),
                "max": round(max_val, 2),
                "trend": trend,
            },
        }

    except Exception as e:
        logger.error(f"Failed to get velocity metrics: {str(e)}")
        return None


def get_backlog_metrics(
    project_id: str, start_date: Optional[Any]
) -> Optional[Dict[str, Any]]:
    """
    Get backlog metrics.

    Args:
        project_id: Project ID
        start_date: Start date for filtering (None for all)

    Returns:
        Backlog metrics data
    """
    # TODO: Implement backlog metrics calculation
    # For now, return None as placeholder
    return None


def get_utilization_metrics(
    project_id: str, start_date: Optional[Any]
) -> Optional[Dict[str, Any]]:
    """
    Get utilization metrics.

    Args:
        project_id: Project ID
        start_date: Start date for filtering (None for all)

    Returns:
        Utilization metrics data
    """
    if start_date:
        query = """
            SELECT
                week_start_date,
                AVG(utilization_rate) as avg_utilization
            FROM resources
            WHERE project_id = %s AND week_start_date >= %s
            GROUP BY week_start_date
            ORDER BY week_start_date ASC
        """
        params = (project_id, start_date)
    else:
        query = """
            SELECT
                week_start_date,
                AVG(utilization_rate) as avg_utilization
            FROM resources
            WHERE project_id = %s
            GROUP BY week_start_date
            ORDER BY week_start_date ASC
        """
        params = (project_id,)

    try:
        results = execute_query(query, params, fetch=True)

        if not results:
            return None

        labels = [r["week_start_date"].isoformat() for r in results]
        values = [
            float(r["avg_utilization"]) if r.get("avg_utilization") is not None else 0
            for r in results
        ]

        # Calculate statistics
        current = values[-1] if values else 0
        average = sum(values) / len(values) if values else 0
        min_val = min(values) if values else 0
        max_val = max(values) if values else 0

        # Calculate trend
        if len(values) >= 2:
            if values[-1] > values[-2] * 1.1:
                trend = "IMPROVING"
            elif values[-1] < values[-2] * 0.9:
                trend = "DECLINING"
            else:
                trend = "STABLE"
        else:
            trend = "STABLE"

        return {
            "metricType": "utilization",
            "data": {"labels": labels, "values": values, "trend": trend},
            "statistics": {
                "current": round(current, 2),
                "average": round(average, 2),
                "min": round(min_val, 2),
                "max": round(max_val, 2),
                "trend": trend,
            },
        }

    except Exception as e:
        logger.error(f"Failed to get utilization metrics: {str(e)}")
        return None
