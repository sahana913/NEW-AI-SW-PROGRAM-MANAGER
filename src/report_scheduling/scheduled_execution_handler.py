"""
Scheduled Execution Handler

This Lambda function is triggered by EventBridge rules to execute scheduled reports.
It generates the report and triggers email distribution.

Validates: Requirements 14.1, 17.2
"""

import json
import os
from datetime import datetime
from typing import Any, Dict

import boto3

from src.shared.decorators import with_audit_logging, with_error_handling
from src.shared.logger import get_logger

logger = get_logger(__name__)

# AWS clients
lambda_client = boto3.client("lambda")
dynamodb = boto3.resource("dynamodb")

# Environment variables
REPORT_GENERATION_LAMBDA_ARN = os.environ.get("REPORT_GENERATION_LAMBDA_ARN")
EMAIL_DISTRIBUTION_LAMBDA_ARN = os.environ.get("EMAIL_DISTRIBUTION_LAMBDA_ARN")
REPORT_SCHEDULES_TABLE = os.environ.get(
    "REPORT_SCHEDULES_TABLE", "ai-sw-pm-report-schedules"
)


@with_error_handling
@with_audit_logging
def scheduled_execution_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for scheduled report execution.

    This is triggered by EventBridge on a schedule.

    Validates: Requirements 14.1 (Weekly reports every Monday at 8:00 AM UTC)
    Validates: Requirements 17.2 (Send report to distribution list)

    Event structure:
    {
        "tenant_id": "tenant-123",
        "schedule_id": "schedule-456",
        "report_type": "WEEKLY_STATUS",
        "recipients": ["user1@example.com"],
        "project_ids": ["proj-1"],
        "format": "PDF"
    }

    Returns:
        Execution result
    """
    logger.info("Scheduled execution handler invoked", extra={"event": event})

    tenant_id = event.get("tenant_id")
    schedule_id = event.get("schedule_id")
    report_type = event.get("report_type")
    recipients = event.get("recipients", [])
    project_ids = event.get("project_ids")
    format_type = event.get("format", "PDF")

    if not tenant_id:
        logger.error("Missing tenant_id in event")
        return {"statusCode": 400, "body": "Missing tenant_id"}

    if not report_type:
        logger.error("Missing report_type in event")
        return {"statusCode": 400, "body": "Missing report_type"}

    if not recipients:
        logger.error("Missing recipients in event")
        return {"statusCode": 400, "body": "Missing recipients"}

    logger.info(
        f"Executing scheduled {report_type} report",
        extra={
            "tenant_id": tenant_id,
            "schedule_id": schedule_id,
            "report_type": report_type,
            "recipient_count": len(recipients),
        },
    )

    try:
        # Step 1: Generate report
        report_id = _generate_report(
            tenant_id=tenant_id,
            report_type=report_type,
            project_ids=project_ids,
            format_type=format_type,
        )

        logger.info(
            f"Report generated: {report_id}",
            extra={"report_id": report_id, "tenant_id": tenant_id},
        )

        # Step 2: Distribute report via email
        _distribute_report(
            report_id=report_id, tenant_id=tenant_id, recipients=recipients
        )

        logger.info(
            f"Report distributed to {len(recipients)} recipients",
            extra={"report_id": report_id, "recipient_count": len(recipients)},
        )

        # Step 3: Update schedule last run time
        if schedule_id:
            _update_schedule_last_run(tenant_id, schedule_id)

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Scheduled report executed successfully",
                    "report_id": report_id,
                    "tenant_id": tenant_id,
                    "recipients": len(recipients),
                }
            ),
        }

    except Exception as e:
        logger.error(
            f"Failed to execute scheduled report: {str(e)}",
            extra={"tenant_id": tenant_id, "schedule_id": schedule_id, "error": str(e)},
        )
        raise


def _generate_report(
    tenant_id: str, report_type: str, project_ids: list, format_type: str
) -> str:
    """
    Generate report by invoking report generation Lambda.

    Args:
        tenant_id: Tenant ID
        report_type: Report type (WEEKLY_STATUS or EXECUTIVE_SUMMARY)
        project_ids: List of project IDs
        format_type: Report format

    Returns:
        Generated report ID
    """
    # Construct event for report generation Lambda
    report_event = {
        "tenant_id": tenant_id,
        "queryStringParameters": {"format": format_type},
    }

    if project_ids:
        report_event["queryStringParameters"]["projectIds"] = ",".join(project_ids)

    # Determine which handler to invoke
    function_name = REPORT_GENERATION_LAMBDA_ARN

    logger.info(
        f"Invoking report generation Lambda",
        extra={
            "function_name": function_name,
            "report_type": report_type,
            "tenant_id": tenant_id,
        },
    )

    try:
        # Invoke report generation Lambda synchronously
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(report_event),
        )

        # Parse response
        payload = json.loads(response["Payload"].read())

        if response.get("StatusCode") != 200:
            raise Exception(f"Report generation failed: {payload}")

        # Extract report ID from response body
        body = json.loads(payload.get("body", "{}"))
        report_id = body.get("reportId")

        if not report_id:
            raise Exception("Report ID not found in response")

        logger.info(
            f"Report generation completed: {report_id}",
            extra={"report_id": report_id, "tenant_id": tenant_id},
        )

        return report_id

    except Exception as e:
        logger.error(
            f"Failed to generate report: {str(e)}",
            extra={"tenant_id": tenant_id, "report_type": report_type},
        )
        raise


def _distribute_report(report_id: str, tenant_id: str, recipients: list) -> None:
    """
    Distribute report via email by invoking email distribution Lambda.

    Validates: Requirement 17.2 - Send report to distribution list

    Args:
        report_id: Report ID
        tenant_id: Tenant ID
        recipients: List of recipient email addresses
    """
    # Construct event for email distribution Lambda
    email_event = {
        "report_id": report_id,
        "tenant_id": tenant_id,
        "recipients": recipients,
    }

    logger.info(
        f"Invoking email distribution Lambda",
        extra={
            "function_name": EMAIL_DISTRIBUTION_LAMBDA_ARN,
            "report_id": report_id,
            "recipient_count": len(recipients),
        },
    )

    try:
        # Invoke email distribution Lambda asynchronously
        response = lambda_client.invoke(
            FunctionName=EMAIL_DISTRIBUTION_LAMBDA_ARN,
            InvocationType="Event",  # Asynchronous invocation
            Payload=json.dumps(email_event),
        )

        if response.get("StatusCode") not in [200, 202]:
            raise Exception(f"Email distribution invocation failed: {response}")

        logger.info(
            f"Email distribution invoked successfully",
            extra={"report_id": report_id, "tenant_id": tenant_id},
        )

    except Exception as e:
        logger.error(
            f"Failed to invoke email distribution: {str(e)}",
            extra={"report_id": report_id, "tenant_id": tenant_id},
        )
        raise


def _update_schedule_last_run(tenant_id: str, schedule_id: str) -> None:
    """
    Update schedule's last run time in DynamoDB.

    Args:
        tenant_id: Tenant ID
        schedule_id: Schedule ID
    """
    table = dynamodb.Table(REPORT_SCHEDULES_TABLE)

    timestamp = datetime.utcnow().isoformat() + "Z"

    try:
        table.update_item(
            Key={"PK": f"TENANT#{tenant_id}", "SK": f"SCHEDULE#{schedule_id}"},
            UpdateExpression="SET lastRunTime = :timestamp, updatedAt = :timestamp",
            ExpressionAttributeValues={":timestamp": timestamp},
        )

        logger.info(
            f"Updated schedule last run time: {schedule_id}",
            extra={"schedule_id": schedule_id, "tenant_id": tenant_id},
        )

    except Exception as e:
        logger.error(
            f"Failed to update schedule last run time: {str(e)}",
            extra={"schedule_id": schedule_id, "tenant_id": tenant_id},
        )
        # Don't raise - this is not critical
