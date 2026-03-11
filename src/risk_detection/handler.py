"""Main Lambda handler for risk detection service."""

import sys
import os
import json
from typing import Dict, List, Any

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logger import get_logger
from shared.decorators import with_logging, with_error_handling, with_tenant_isolation
from shared.errors import ValidationError

from velocity_analysis import analyze_velocity_risk
from backlog_analysis import analyze_backlog_risk
from milestone_analysis import analyze_milestone_risks
from ai_explanations import enrich_risk_with_ai
from risk_storage import store_risk_alert, list_risks, dismiss_risk, publish_risk_event

logger = get_logger()


@with_logging
@with_error_handling
def detect_risks_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for detecting risks in a project.
    
    This is triggered after data ingestion completes.
    
    Event format:
    {
        "project_id": "uuid",
        "tenant_id": "uuid"
    }
    
    Returns:
        API Gateway response with detected risks
    """
    # Extract parameters
    project_id = event.get('project_id')
    tenant_id = event.get('tenant_id')
    
    if not project_id or not tenant_id:
        raise ValidationError("Missing required parameters: project_id and tenant_id")
    
    logger.info(
        f"Starting risk detection for project",
        extra={"project_id": project_id, "tenant_id": tenant_id}
    )
    
    detected_risks = []
    
    try:
        # 1. Analyze velocity trends
        velocity_risk = analyze_velocity_risk(project_id, tenant_id)
        if velocity_risk:
            # Enrich with AI explanation
            velocity_risk = enrich_risk_with_ai(velocity_risk)
            # Store risk
            risk_id = store_risk_alert(velocity_risk)
            velocity_risk['risk_id'] = risk_id
            # Publish event
            publish_risk_event(velocity_risk, 'RiskDetected')
            detected_risks.append(velocity_risk)
        
        # 2. Analyze backlog growth
        backlog_risk = analyze_backlog_risk(project_id, tenant_id)
        if backlog_risk:
            # Enrich with AI explanation
            backlog_risk = enrich_risk_with_ai(backlog_risk)
            # Store risk
            risk_id = store_risk_alert(backlog_risk)
            backlog_risk['risk_id'] = risk_id
            # Publish event
            publish_risk_event(backlog_risk, 'RiskDetected')
            detected_risks.append(backlog_risk)
        
        # 3. Analyze milestone slippage
        milestone_risks = analyze_milestone_risks(project_id, tenant_id)
        for milestone_risk in milestone_risks:
            # Enrich with AI explanation
            milestone_risk = enrich_risk_with_ai(milestone_risk)
            # Store risk
            risk_id = store_risk_alert(milestone_risk)
            milestone_risk['risk_id'] = risk_id
            # Publish event
            publish_risk_event(milestone_risk, 'RiskDetected')
            detected_risks.append(milestone_risk)
        
        logger.info(
            f"Risk detection completed",
            extra={
                "project_id": project_id,
                "risks_detected": len(detected_risks)
            }
        )
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "project_id": project_id,
                "risks_detected": len(detected_risks),
                "risks": detected_risks
            })
        }
        
    except Exception as e:
        logger.error(
            f"Risk detection failed",
            extra={"project_id": project_id, "error": str(e)}
        )
        raise


@with_logging
@with_error_handling
@with_tenant_isolation
def list_risks_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for listing risks with filtering.
    
    Query parameters:
    - projectId (optional): Filter by project
    - severity (optional): Filter by severity (LOW, MEDIUM, HIGH, CRITICAL)
    - status (optional): Filter by status (ACTIVE, DISMISSED, RESOLVED)
    - limit (optional): Maximum results (default 50)
    
    Returns:
        API Gateway response with risk list
    """
    # Extract tenant_id from event (injected by with_tenant_isolation)
    tenant_id = event.get('tenant_id')
    
    # Extract query parameters
    query_params = event.get('queryStringParameters') or {}
    project_id = query_params.get('projectId')
    severity = query_params.get('severity')
    status = query_params.get('status')
    limit = int(query_params.get('limit', 50))
    
    logger.info(
        f"Listing risks",
        extra={
            "tenant_id": tenant_id,
            "project_id": project_id,
            "severity": severity,
            "status": status
        }
    )
    
    try:
        risks = list_risks(
            tenant_id=tenant_id,
            project_id=project_id,
            severity=severity,
            status=status,
            limit=limit
        )
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "risks": risks,
                "count": len(risks)
            })
        }
        
    except Exception as e:
        logger.error(
            f"Failed to list risks",
            extra={"tenant_id": tenant_id, "error": str(e)}
        )
        raise


@with_logging
@with_error_handling
@with_tenant_isolation
def dismiss_risk_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for dismissing a risk.
    
    Path parameters:
    - riskId: Risk ID to dismiss
    
    Body:
    {
        "reason": "Explanation for dismissal"
    }
    
    Returns:
        API Gateway response with updated risk
    """
    # Extract tenant_id from event (injected by with_tenant_isolation)
    tenant_id = event.get('tenant_id')
    
    # Extract user_id from authorizer context
    authorizer_context = event.get("requestContext", {}).get("authorizer", {})
    user_id = authorizer_context.get("userId", "unknown")
    
    # Extract path parameters
    path_params = event.get('pathParameters') or {}
    risk_id = path_params.get('riskId')
    
    if not risk_id:
        raise ValidationError("Missing required parameter: riskId")
    
    # Parse body
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        raise ValidationError("Invalid JSON in request body")
    
    reason = body.get('reason', 'No reason provided')
    
    logger.info(
        f"Dismissing risk",
        extra={
            "risk_id": risk_id,
            "tenant_id": tenant_id,
            "user_id": user_id
        }
    )
    
    try:
        updated_risk = dismiss_risk(
            risk_id=risk_id,
            tenant_id=tenant_id,
            dismissed_by=user_id,
            reason=reason
        )
        
        # Publish event
        publish_risk_event(updated_risk, 'RiskDismissed')
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "risk": updated_risk
            })
        }
        
    except Exception as e:
        logger.error(
            f"Failed to dismiss risk",
            extra={"risk_id": risk_id, "error": str(e)}
        )
        raise
