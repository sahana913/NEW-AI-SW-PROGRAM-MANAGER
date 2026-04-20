"""HTML report rendering with charts for weekly status reports."""

from shared.logger import get_logger
from shared.errors import ProcessingError
import base64
import os
import sys
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import matplotlib

    matplotlib.use("Agg")  # Use non-interactive backend
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure
except ImportError:
    matplotlib = None
    plt = None
    mdates = None
    Figure = None


logger = get_logger()


def generate_velocity_chart(
    velocity_data: Dict[str, List[Dict[str, Any]]]
) -> Optional[str]:
    """
    Generate velocity trend chart as base64-encoded PNG.

    Args:
        velocity_data: Dictionary mapping project_id to sprint velocity data

    Returns:
        Base64-encoded PNG image string, or None if matplotlib not available
    """
    if not plt:
        logger.warning("matplotlib not available, skipping chart generation")
        return None

    try:
        fig, ax = plt.subplots(figsize=(10, 6))

        # Plot velocity for each project
        for project_id, sprints in velocity_data.items():
            if not sprints:
                continue

            # Sort by start date
            sprints_sorted = sorted(sprints, key=lambda s: s.get("start_date", ""))

            sprint_names = [s.get("sprint_name", "")[:15] for s in sprints_sorted]
            velocities = [s.get("velocity", 0) for s in sprints_sorted]

            project_name = sprints_sorted[0].get("project_name", project_id)[:20]

            ax.plot(
                sprint_names, velocities, marker="o", label=project_name, linewidth=2
            )

        ax.set_xlabel("Sprint", fontsize=12)
        ax.set_ylabel("Velocity (Story Points)", fontsize=12)
        ax.set_title("Sprint Velocity Trends", fontsize=14, fontweight="bold")
        ax.legend(loc="best")
        ax.grid(True, alpha=0.3)

        # Rotate x-axis labels for readability
        plt.xticks(rotation=45, ha="right")

        plt.tight_layout()

        # Convert to base64
        buffer = BytesIO()
        plt.savefig(buffer, format="png", dpi=100, bbox_inches="tight")
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode("utf-8")
        plt.close(fig)

        return image_base64

    except Exception as e:
        logger.error(f"Failed to generate velocity chart: {str(e)}")
        return None


def generate_backlog_chart(backlog_data: Dict[str, Dict[str, Any]]) -> Optional[str]:
    """
    Generate backlog status chart as base64-encoded PNG.

    Args:
        backlog_data: Dictionary mapping project_id to backlog metrics

    Returns:
        Base64-encoded PNG image string, or None if matplotlib not available
    """
    if not plt:
        logger.warning("matplotlib not available, skipping chart generation")
        return None

    try:
        if not backlog_data:
            return None

        fig, ax = plt.subplots(figsize=(10, 6))

        # Prepare data
        projects = []
        open_items = []
        bugs = []
        features = []
        tech_debt = []

        for project_id, data in list(backlog_data.items())[:10]:  # Limit to 10 projects
            projects.append(data.get("project_name", project_id)[:20])
            open_items.append(data.get("open_items", 0))
            bugs.append(data.get("bugs", 0))
            features.append(data.get("features", 0))
            tech_debt.append(data.get("tech_debt", 0))

        # Create stacked bar chart
        x = range(len(projects))
        width = 0.6

        ax.bar(x, bugs, width, label="Bugs", color="#e74c3c")
        ax.bar(x, features, width, bottom=bugs, label="Features", color="#3498db")

        # Calculate bottom for tech debt
        bottom = [bugs[i] + features[i] for i in range(len(bugs))]
        ax.bar(x, tech_debt, width, bottom=bottom, label="Tech Debt", color="#f39c12")

        ax.set_xlabel("Project", fontsize=12)
        ax.set_ylabel("Number of Items", fontsize=12)
        ax.set_title("Backlog Status by Project", fontsize=14, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(projects, rotation=45, ha="right")
        ax.legend(loc="best")
        ax.grid(True, alpha=0.3, axis="y")

        plt.tight_layout()

        # Convert to base64
        buffer = BytesIO()
        plt.savefig(buffer, format="png", dpi=100, bbox_inches="tight")
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode("utf-8")
        plt.close(fig)

        return image_base64

    except Exception as e:
        logger.error(f"Failed to generate backlog chart: {str(e)}")
        return None


def generate_risk_distribution_chart(risks: List[Dict[str, Any]]) -> Optional[str]:
    """
    Generate risk distribution pie chart as base64-encoded PNG.

    Args:
        risks: List of risk alerts

    Returns:
        Base64-encoded PNG image string, or None if matplotlib not available
    """
    if not plt:
        logger.warning("matplotlib not available, skipping chart generation")
        return None

    try:
        if not risks:
            return None

        # Count risks by severity
        severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for risk in risks:
            severity = risk.get("severity", "LOW")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        # Filter out zero counts
        labels = []
        sizes = []
        colors = []
        color_map = {
            "CRITICAL": "#c0392b",
            "HIGH": "#e74c3c",
            "MEDIUM": "#f39c12",
            "LOW": "#3498db",
        }

        for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            if severity_counts[severity] > 0:
                labels.append(severity)
                sizes.append(severity_counts[severity])
                colors.append(color_map[severity])

        if not sizes:
            return None

        fig, ax = plt.subplots(figsize=(8, 6))

        ax.pie(
            sizes,
            labels=labels,
            colors=colors,
            autopct="%1.1f%%",
            startangle=90,
            textprops={"fontsize": 12},
        )
        ax.set_title("Risk Distribution by Severity", fontsize=14, fontweight="bold")

        plt.tight_layout()

        # Convert to base64
        buffer = BytesIO()
        plt.savefig(buffer, format="png", dpi=100, bbox_inches="tight")
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode("utf-8")
        plt.close(fig)

        return image_base64

    except Exception as e:
        logger.error(f"Failed to generate risk distribution chart: {str(e)}")
        return None


def render_html_report(
    report_data: Dict[str, Any], narrative: str, report_type: str = "WEEKLY_STATUS"
) -> str:
    """
    Render HTML report with narrative and charts.

    Validates: Property 37 - Report Content Completeness

    Args:
        report_data: Aggregated report data
        narrative: AI-generated narrative summary
        report_type: Type of report (WEEKLY_STATUS or EXECUTIVE_SUMMARY)

    Returns:
        HTML string
    """
    try:
        # Generate charts
        velocity_chart = None
        backlog_chart = None
        risk_chart = None

        if report_type == "WEEKLY_STATUS":
            velocity_data = report_data.get("velocity_trends", {})
            if velocity_data:
                velocity_chart = generate_velocity_chart(velocity_data)

            backlog_data = report_data.get("backlog_status", {})
            if backlog_data:
                backlog_chart = generate_backlog_chart(backlog_data)

        risks = report_data.get("risks", [])
        if risks:
            risk_chart = generate_risk_distribution_chart(risks)

        # Build HTML
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{report_type.replace('_', ' ').title()}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header h1 {{
            margin: 0;
            font-size: 2.5em;
        }}
        .header .date {{
            margin-top: 10px;
            font-size: 1.1em;
            opacity: 0.9;
        }}
        .section {{
            background: white;
            padding: 25px;
            margin-bottom: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .section h2 {{
            color: #667eea;
            border-bottom: 3px solid #667eea;
            padding-bottom: 10px;
            margin-top: 0;
        }}
        .narrative {{
            font-size: 1.1em;
            line-height: 1.8;
            color: #555;
        }}
        .chart {{
            text-align: center;
            margin: 20px 0;
        }}
        .chart img {{
            max-width: 100%;
            height: auto;
            border-radius: 5px;
        }}
        .milestone-list, .risk-list {{
            list-style: none;
            padding: 0;
        }}
        .milestone-item, .risk-item {{
            padding: 15px;
            margin: 10px 0;
            border-left: 4px solid #3498db;
            background: #f8f9fa;
            border-radius: 4px;
        }}
        .risk-item.critical {{
            border-left-color: #c0392b;
            background: #fde8e8;
        }}
        .risk-item.high {{
            border-left-color: #e74c3c;
            background: #fdeaea;
        }}
        .risk-item.medium {{
            border-left-color: #f39c12;
            background: #fef5e7;
        }}
        .milestone-item strong, .risk-item strong {{
            display: block;
            margin-bottom: 5px;
            color: #2c3e50;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: bold;
            margin-left: 10px;
        }}
        .badge.critical {{
            background: #c0392b;
            color: white;
        }}
        .badge.high {{
            background: #e74c3c;
            color: white;
        }}
        .badge.medium {{
            background: #f39c12;
            color: white;
        }}
        .badge.low {{
            background: #3498db;
            color: white;
        }}
        .badge.completed {{
            background: #27ae60;
            color: white;
        }}
        .badge.at-risk {{
            background: #e67e22;
            color: white;
        }}
        .footer {{
            text-align: center;
            margin-top: 40px;
            padding: 20px;
            color: #7f8c8d;
            font-size: 0.9em;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #667eea;
            color: white;
            font-weight: bold;
        }}
        tr:hover {{
            background: #f5f5f5;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{report_type.replace('_', ' ').title()}</h1>
        <div class="date">Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p UTC')}</div>
    </div>

    <div class="section">
        <h2>Executive Summary</h2>
        <div class="narrative">{narrative}</div>
    </div>
"""

        # Add project health overview if available
        projects = report_data.get("projects", [])
        if projects and report_type == "WEEKLY_STATUS":
            html += """
    <div class="section">
        <h2>Project Health Overview</h2>
        <table>
            <thead>
                <tr>
                    <th>Project</th>
                    <th>Source</th>
                    <th>Last Sync</th>
                </tr>
            </thead>
            <tbody>
"""
            for project in projects[:10]:  # Limit to 10
                last_sync = project.get("last_sync_at", "N/A")
                if last_sync and last_sync != "N/A":
                    try:
                        last_sync = datetime.fromisoformat(str(last_sync)).strftime(
                            "%Y-%m-%d %H:%M"
                        )
                    except:
                        pass

                html += f"""
                <tr>
                    <td>{project.get('project_name', 'Unknown')}</td>
                    <td>{project.get('source', 'N/A')}</td>
                    <td>{last_sync}</td>
                </tr>
"""
            html += """
            </tbody>
        </table>
    </div>
"""

        # Add completed milestones
        completed_milestones = report_data.get("completed_milestones", [])
        if completed_milestones:
            html += """
    <div class="section">
        <h2>Completed Milestones</h2>
        <ul class="milestone-list">
"""
            for milestone in completed_milestones[:10]:  # Limit to 10
                html += f"""
            <li class="milestone-item">
                <strong>{milestone.get('milestone_name', 'Unknown')}</strong>
                <span class="badge completed">COMPLETED</span>
                <div>Project: {milestone.get('project_name', 'Unknown')}</div>
                <div>Due Date: {milestone.get('due_date', 'N/A')}</div>
            </li>
"""
            html += """
        </ul>
    </div>
"""

        # Add upcoming milestones
        upcoming_milestones = report_data.get("upcoming_milestones", [])
        if upcoming_milestones:
            html += """
    <div class="section">
        <h2>Upcoming Milestones (Next 2 Weeks)</h2>
        <ul class="milestone-list">
"""
            for milestone in upcoming_milestones[:10]:  # Limit to 10
                status = milestone.get("status", "ON_TRACK")
                badge_class = "at-risk" if status == "AT_RISK" else "completed"
                completion = milestone.get("completion_percentage", 0)

                html += f"""
            <li class="milestone-item">
                <strong>{milestone.get('milestone_name', 'Unknown')}</strong>
                <span class="badge {badge_class}">{status.replace('_', ' ')}</span>
                <div>Project: {milestone.get('project_name', 'Unknown')}</div>
                <div>Due Date: {milestone.get('due_date', 'N/A')} | Completion: {completion:.0f}%</div>
            </li>
"""
            html += """
        </ul>
    </div>
"""

        # Add risk alerts
        if risks:
            html += """
    <div class="section">
        <h2>Active Risk Alerts</h2>
        <ul class="risk-list">
"""
            for risk in risks[:15]:  # Limit to 15
                severity = risk.get("severity", "LOW").lower()
                html += f"""
            <li class="risk-item {severity}">
                <strong>{risk.get('title', 'Unknown Risk')}</strong>
                <span class="badge {severity}">{risk.get('severity', 'LOW')}</span>
                <div>Type: {risk.get('type', 'Unknown').replace('_', ' ')}</div>
                <div>{risk.get('description', 'No description available')[:200]}</div>
            </li>
"""
            html += """
        </ul>
    </div>
"""

        # Add charts
        if report_type == "WEEKLY_STATUS":
            if velocity_chart:
                html += f"""
    <div class="section">
        <h2>Velocity Trends</h2>
        <div class="chart">
            <img src="data:image/png;base64,{velocity_chart}" alt="Velocity Trends Chart">
        </div>
    </div>
"""

            if backlog_chart:
                html += f"""
    <div class="section">
        <h2>Backlog Status</h2>
        <div class="chart">
            <img src="data:image/png;base64,{backlog_chart}" alt="Backlog Status Chart">
        </div>
    </div>
"""

        if risk_chart:
            html += f"""
    <div class="section">
        <h2>Risk Distribution</h2>
        <div class="chart">
            <img src="data:image/png;base64,{risk_chart}" alt="Risk Distribution Chart">
        </div>
    </div>
"""

        # Add predictions if available
        predictions = report_data.get("predictions", {})
        if predictions and report_type == "WEEKLY_STATUS":
            html += """
    <div class="section">
        <h2>Predictions & Insights</h2>
        <table>
            <thead>
                <tr>
                    <th>Project</th>
                    <th>Prediction Type</th>
                    <th>Value</th>
                    <th>Confidence</th>
                </tr>
            </thead>
            <tbody>
"""
            for project_id, pred_types in list(predictions.items())[:10]:
                for pred_type, pred in pred_types.items():
                    value = pred.get("predictionValue", 0)
                    confidence = pred.get("confidenceScore", 0)
                    html += f"""
                <tr>
                    <td>{project_id[:20]}</td>
                    <td>{pred_type.replace('_', ' ').title()}</td>
                    <td>{value:.1f}%</td>
                    <td>{confidence:.2f}</td>
                </tr>
"""
            html += """
            </tbody>
        </table>
    </div>
"""

        html += """
    <div class="footer">
        <p>This report was automatically generated by the AI SW Program Manager platform.</p>
        <p>For questions or concerns, please contact your program management team.</p>
    </div>
</body>
</html>
"""

        return html

    except Exception as e:
        logger.error(f"Failed to render HTML report: {str(e)}")
        raise ProcessingError(
            f"Failed to render HTML report: {str(e)}",
            processing_type="Report_Rendering",
        )
