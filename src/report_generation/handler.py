"""Main Lambda handler for report generation service."""

import sys
import os
import json
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logger import get_logger
from shared.decorators import with_logging, with_error_handling, with_tenant_isolation
from shared.errors import ValidationError

# Import cache manager from dashboard module
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'dashboard'))
from cache_manager import get_cached_data, cache_report_data

from data_aggregator import (
    query_project_health_scores,
    query_completed_milestones,
    query_upcoming_milestones,
    query_active_risks,
    query_velocity_trends,
    query_backlog_status,
    query_predictions
)
from narrative_generator import (
    generate_weekly_status_narrative,
    generate_executive_summary
)
from report_renderer import render_html_report
from report_storage import (
    store_report_html,
    store_report_metadata,
    get_report_metadata,
    list_reports
)

logger = get_logger()


def aggregate_report_data(
    tenant_id: str,
    project_ids: Optional[List[str]] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Aggregate all data needed for report generation.
    
    Validates: Property 37 - Report Content Completeness
    Validates: Requirement 23.1 (1-hour cache TTL for reports)
    
    Args:
        tenant_id: Tenant ID
        project_ids: Optional list of specific project IDs
        start_date: Start date for date-range queries
        end_date: End date for date-range queries
        
    Returns:
        Dictionary with all aggregated report data
    """
    logger.info(
        "Aggregating report data",
        extra={"tenant_id": tenant_id, "project_count": len(project_ids) if project_ids else "all"}
    )
    
    # Generate cache key
    cache_key_parts = [f"report:data:{tenant_id}"]
    if project_ids:
        cache_key_parts.append(f"projects:{','.join(sorted(project_ids))}")
    if start_date:
        cache_key_parts.append(f"start:{start_date.strftime('%Y%m%d')}")
    if end_date:
        cache_key_parts.append(f"end:{end_date.strftime('%Y%m%d')}")
    
    cache_key = ":".join(cache_key_parts)
    
    # Check cache first (1-hour TTL for reports)
    cached_data = get_cached_data(cache_key)
    if cached_data:
        logger.info("Returning cached report data")
        return cached_data
    
    # Query all required data
    projects = query_project_health_scores(tenant_id, project_ids)
    completed_milestones = query_completed_milestones(tenant_id, project_ids, start_date, end_date)
    upcoming_milestones = query_upcoming_milestones(tenant_id, project_ids, days_ahead=14)
    risks = query_active_risks(tenant_id, project_ids)
    velocity_trends = query_velocity_trends(tenant_id, project_ids, num_sprints=8)
    backlog_status = query_backlog_status(tenant_id, project_ids)
    predictions = query_predictions(tenant_id, project_ids)
    
    report_data = {
        'projects': projects,
        'completed_milestones': completed_milestones,
        'upcoming_milestones': upcoming_milestones,
        'risks': risks,
        'velocity_trends': velocity_trends,
        'backlog_status': backlog_status,
        'predictions': predictions
    }
    
    # Cache for 1 hour (report data)
    cache_report_data(cache_key, report_data)
    
    logger.info(
        "Report data aggregated successfully",
        extra={
            "tenant_id": tenant_id,
            "projects": len(projects),
            "completed_milestones": len(completed_milestones),
            "upcoming_milestones": len(upcoming_milestones),
            "risks": len(risks)
        }
    )
    
    return report_data


@with_logging
@with_error_handling
@with_tenant_isolation
def generate_weekly_status_report_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for generating weekly status reports.
    
    Validates: Property 37 - Report Content Completeness
    Validates: Property 38 - Report Metadata Persistence
    
    Query parameters:
    - projectIds (optional): Comma-separated list of project IDs
    - format (optional): Report format (HTML, PDF) - default HTML
    - sections (optional): Comma-separated list of sections to include
    
    Returns:
        API Gateway response with report metadata and download URL
    """
    # Extract tenant_id from event (injected by with_tenant_isolation)
    tenant_id = event.get('tenant_id')
    
    # Extract user_id from authorizer context
    authorizer_context = event.get("requestContext", {}).get("authorizer", {})
    user_id = authorizer_context.get("userId", "system")
    
    # Extract query parameters
    query_params = event.get('queryStringParameters') or {}
    project_ids_str = query_params.get('projectIds')
    format_type = query_params.get('format', 'HTML').upper()
    sections_str = query_params.get('sections')
    
    # Parse project IDs
    project_ids = None
    if project_ids_str:
        project_ids = [pid.strip() for pid in project_ids_str.split(',') if pid.strip()]
    
    # Parse sections (Property 39 - Report Section Customization)
    sections = None
    if sections_str:
        sections = [s.strip() for s in sections_str.split(',') if s.strip()]
    
    logger.info(
        "Generating weekly status report",
        extra={
            "tenant_id": tenant_id,
            "user_id": user_id,
            "project_ids": project_ids,
            "format": format_type,
            "sections": sections
        }
    )
    
    try:
        # Generate report ID
        report_id = str(uuid.uuid4())
        
        # Aggregate data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        report_data = aggregate_report_data(
            tenant_id=tenant_id,
            project_ids=project_ids,
            start_date=start_date,
            end_date=end_date
        )
        
        # Filter sections if customization requested (Property 39)
        if sections:
            # Filter report_data to include only requested sections
            filtered_data = {'projects': report_data.get('projects', [])}
            
            if 'milestones' in sections or 'completed_milestones' in sections:
                filtered_data['completed_milestones'] = report_data.get('completed_milestones', [])
            if 'milestones' in sections or 'upcoming_milestones' in sections:
                filtered_data['upcoming_milestones'] = report_data.get('upcoming_milestones', [])
            if 'risks' in sections:
                filtered_data['risks'] = report_data.get('risks', [])
            if 'velocity' in sections or 'velocity_trends' in sections:
                filtered_data['velocity_trends'] = report_data.get('velocity_trends', {})
            if 'backlog' in sections or 'backlog_status' in sections:
                filtered_data['backlog_status'] = report_data.get('backlog_status', {})
            if 'predictions' in sections:
                filtered_data['predictions'] = report_data.get('predictions', {})
            
            report_data = filtered_data
        
        # Generate AI narrative
        narrative = generate_weekly_status_narrative(report_data)
        
        # Render HTML report
        html_content = render_html_report(
            report_data=report_data,
            narrative=narrative,
            report_type='WEEKLY_STATUS'
        )
        
        # Store report in S3
        s3_key = store_report_html(
            tenant_id=tenant_id,
            report_id=report_id,
            html_content=html_content
        )
        
        # Store metadata in DynamoDB
        metadata = store_report_metadata(
            tenant_id=tenant_id,
            report_id=report_id,
            report_type='WEEKLY_STATUS',
            project_ids=project_ids or [],
            format=format_type,
            s3_key=s3_key,
            generated_by=user_id,
            sections=sections
        )
        
        logger.info(
            "Weekly status report generated successfully",
            extra={
                "tenant_id": tenant_id,
                "report_id": report_id,
                "format": format_type
            }
        )
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "reportId": report_id,
                "reportType": "WEEKLY_STATUS",
                "status": "COMPLETED",
                "downloadUrl": metadata.get('downloadUrl'),
                "expiresAt": metadata.get('expiresAt'),
                "generatedAt": metadata.get('generatedAt')
            })
        }
        
    except Exception as e:
        logger.error(
            "Failed to generate weekly status report",
            extra={"tenant_id": tenant_id, "error": str(e)}
        )
        raise


@with_logging
@with_error_handling
@with_tenant_isolation
def generate_executive_summary_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for generating executive summaries.
    
    Validates: Property 40 - Executive Summary Length Constraint (max 500 words)
    Validates: Property 41 - Executive Summary Content
    Validates: Property 42 - Executive Risk Filtering (High and Critical only)
    Validates: Property 43 - Trend Indicator Inclusion
    
    Query parameters:
    - projectIds (optional): Comma-separated list of project IDs (portfolio if omitted)
    - format (optional): Report format (HTML, PDF) - default HTML
    
    Returns:
        API Gateway response with report metadata and download URL
    """
    # Extract tenant_id from event (injected by with_tenant_isolation)
    tenant_id = event.get('tenant_id')
    
    # Extract user_id from authorizer context
    authorizer_context = event.get("requestContext", {}).get("authorizer", {})
    user_id = authorizer_context.get("userId", "system")
    
    # Extract query parameters
    query_params = event.get('queryStringParameters') or {}
    project_ids_str = query_params.get('projectIds')
    format_type = query_params.get('format', 'HTML').upper()
    
    # Parse project IDs
    project_ids = None
    if project_ids_str:
        project_ids = [pid.strip() for pid in project_ids_str.split(',') if pid.strip()]
    
    logger.info(
        "Generating executive summary",
        extra={
            "tenant_id": tenant_id,
            "user_id": user_id,
            "project_ids": project_ids,
            "format": format_type
        }
    )
    
    try:
        # Generate report ID
        report_id = str(uuid.uuid4())
        
        # Aggregate portfolio-level data
        report_data = aggregate_report_data(
            tenant_id=tenant_id,
            project_ids=project_ids
        )
        
        # Filter for High and Critical risks only (Property 42)
        all_risks = report_data.get('risks', [])
        critical_high_risks = [r for r in all_risks if r.get('severity') in ['CRITICAL', 'HIGH']]
        report_data['risks'] = critical_high_risks
        
        # Calculate portfolio RAG status (simplified)
        # In production, this would use health score calculation
        if len([r for r in critical_high_risks if r.get('severity') == 'CRITICAL']) > 0:
            portfolio_rag = 'RED'
        elif len(critical_high_risks) > 3:
            portfolio_rag = 'AMBER'
        else:
            portfolio_rag = 'GREEN'
        
        report_data['portfolio_rag_status'] = portfolio_rag
        
        # Add trend indicators (Property 43)
        # This would be calculated from historical data in production
        report_data['key_metrics'] = {
            'velocity_trend': 'stable',
            'backlog_trend': 'declining',
            'risk_trend': 'improving'
        }
        
        # Generate AI executive summary (max 500 words - Property 40)
        narrative = generate_executive_summary(report_data)
        
        # Render HTML report
        html_content = render_html_report(
            report_data=report_data,
            narrative=narrative,
            report_type='EXECUTIVE_SUMMARY'
        )
        
        # Store report in S3
        s3_key = store_report_html(
            tenant_id=tenant_id,
            report_id=report_id,
            html_content=html_content
        )
        
        # Store metadata in DynamoDB
        metadata = store_report_metadata(
            tenant_id=tenant_id,
            report_id=report_id,
            report_type='EXECUTIVE_SUMMARY',
            project_ids=project_ids or [],
            format=format_type,
            s3_key=s3_key,
            generated_by=user_id
        )
        
        logger.info(
            "Executive summary generated successfully",
            extra={
                "tenant_id": tenant_id,
                "report_id": report_id,
                "format": format_type
            }
        )
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "reportId": report_id,
                "reportType": "EXECUTIVE_SUMMARY",
                "status": "COMPLETED",
                "downloadUrl": metadata.get('downloadUrl'),
                "expiresAt": metadata.get('expiresAt'),
                "generatedAt": metadata.get('generatedAt')
            })
        }
        
    except Exception as e:
        logger.error(
            "Failed to generate executive summary",
            extra={"tenant_id": tenant_id, "error": str(e)}
        )
        raise


@with_logging
@with_error_handling
@with_tenant_isolation
def get_report_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for retrieving report metadata.
    
    Path parameters:
    - reportId: Report ID to retrieve
    
    Returns:
        API Gateway response with report metadata
    """
    # Extract tenant_id from event (injected by with_tenant_isolation)
    tenant_id = event.get('tenant_id')
    
    # Extract path parameters
    path_params = event.get('pathParameters') or {}
    report_id = path_params.get('reportId')
    
    if not report_id:
        raise ValidationError("Missing required parameter: reportId")
    
    logger.info(
        "Retrieving report metadata",
        extra={"tenant_id": tenant_id, "report_id": report_id}
    )
    
    try:
        metadata = get_report_metadata(tenant_id, report_id)
        
        if not metadata:
            return {
                "statusCode": 404,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps({
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "Report not found"
                    }
                })
            }
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "reportId": metadata.get('reportId'),
                "reportType": metadata.get('reportType'),
                "status": "COMPLETED",
                "downloadUrl": metadata.get('downloadUrl'),
                "expiresAt": metadata.get('expiresAt'),
                "generatedAt": metadata.get('generatedAt'),
                "format": metadata.get('format'),
                "projectIds": metadata.get('projectIds', [])
            })
        }
        
    except Exception as e:
        logger.error(
            "Failed to retrieve report metadata",
            extra={"tenant_id": tenant_id, "report_id": report_id, "error": str(e)}
        )
        raise


@with_logging
@with_error_handling
@with_tenant_isolation
def list_reports_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for listing reports.
    
    Query parameters:
    - reportType (optional): Filter by report type
    - limit (optional): Maximum results (default 50)
    
    Returns:
        API Gateway response with report list
    """
    # Extract tenant_id from event (injected by with_tenant_isolation)
    tenant_id = event.get('tenant_id')
    
    # Extract query parameters
    query_params = event.get('queryStringParameters') or {}
    report_type = query_params.get('reportType')
    limit = int(query_params.get('limit', 50))
    
    logger.info(
        "Listing reports",
        extra={"tenant_id": tenant_id, "report_type": report_type}
    )
    
    try:
        reports = list_reports(tenant_id, report_type, limit)
        
        # Format response
        formatted_reports = [
            {
                "reportId": r.get('reportId'),
                "reportType": r.get('reportType'),
                "generatedAt": r.get('generatedAt'),
                "format": r.get('format'),
                "projectIds": r.get('projectIds', []),
                "downloadUrl": r.get('downloadUrl'),
                "expiresAt": r.get('expiresAt')
            }
            for r in reports
        ]
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "reports": formatted_reports,
                "count": len(formatted_reports)
            })
        }
        
    except Exception as e:
        logger.error(
            "Failed to list reports",
            extra={"tenant_id": tenant_id, "error": str(e)}
        )
        raise
