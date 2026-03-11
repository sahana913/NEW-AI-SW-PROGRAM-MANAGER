"""
Email Distribution Lambda Handler

This Lambda function handles scheduled report distribution via Amazon SES.
It retrieves generated reports, checks user preferences, and sends emails with
PDF attachments and inline summaries.

Validates: Requirements 17.2, 17.4, 17.6, 17.7, 17.8
"""

import json
import os
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

from src.shared.logger import get_logger
from src.shared.decorators import handle_errors, log_execution_time
from src.shared.errors import ValidationError, NotFoundError

from .email_sender import EmailSender
from .delivery_logger import DeliveryLogger
from .preferences_checker import PreferencesChecker

logger = get_logger(__name__)

# Environment variables
REPORTS_TABLE = os.environ.get('REPORTS_TABLE', 'ai-sw-pm-reports')
EMAIL_DELIVERY_LOGS_TABLE = os.environ.get('EMAIL_DELIVERY_LOGS_TABLE', 'ai-sw-pm-email-delivery-logs')
EMAIL_PREFERENCES_TABLE = os.environ.get('EMAIL_PREFERENCES_TABLE', 'ai-sw-pm-email-preferences')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'noreply@ai-sw-pm.example.com')


@handle_errors
@log_execution_time
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for email distribution.
    
    Event can be triggered by:
    1. EventBridge scheduled rule (for scheduled reports)
    2. Direct invocation (for ad-hoc distribution)
    
    Args:
        event: Lambda event containing report_id and recipients
        context: Lambda context
        
    Returns:
        Response with delivery status
    """
    logger.info("Email distribution Lambda invoked", extra={"event": event})
    
    # Parse event
    if 'Records' in event:
        # EventBridge event
        record = event['Records'][0]
        detail = json.loads(record['body']) if 'body' in record else record.get('detail', {})
    else:
        # Direct invocation
        detail = event
    
    report_id = detail.get('report_id')
    recipients = detail.get('recipients', [])
    tenant_id = detail.get('tenant_id')
    
    if not report_id:
        raise ValidationError("report_id is required")
    
    if not recipients:
        raise ValidationError("recipients list is required")
    
    if not tenant_id:
        raise ValidationError("tenant_id is required")
    
    logger.info(
        f"Processing email distribution for report {report_id}",
        extra={
            "report_id": report_id,
            "recipient_count": len(recipients),
            "tenant_id": tenant_id
        }
    )
    
    # Initialize services
    email_sender = EmailSender(sender_email=SENDER_EMAIL)
    delivery_logger = DeliveryLogger(table_name=EMAIL_DELIVERY_LOGS_TABLE)
    preferences_checker = PreferencesChecker(table_name=EMAIL_PREFERENCES_TABLE)
    
    # Get report details
    report_details = _get_report_details(report_id, tenant_id)
    
    # Filter recipients based on preferences (Requirement 17.8)
    filtered_recipients = []
    for recipient in recipients:
        if preferences_checker.can_send_email(recipient, tenant_id):
            filtered_recipients.append(recipient)
        else:
            logger.info(
                f"Skipping recipient {recipient} due to unsubscribe preference",
                extra={"recipient": recipient, "report_id": report_id}
            )
            delivery_logger.log_skipped(
                report_id=report_id,
                recipient=recipient,
                tenant_id=tenant_id,
                reason="unsubscribed"
            )
    
    if not filtered_recipients:
        logger.warning(
            "No recipients to send to after filtering",
            extra={"report_id": report_id}
        )
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'No recipients to send to after filtering',
                'report_id': report_id,
                'skipped_count': len(recipients)
            })
        }
    
    # Send emails to filtered recipients
    results = []
    for recipient in filtered_recipients:
        result = _send_email_with_retry(
            email_sender=email_sender,
            delivery_logger=delivery_logger,
            report_details=report_details,
            recipient=recipient,
            tenant_id=tenant_id
        )
        results.append(result)
    
    # Summarize results
    successful = sum(1 for r in results if r['success'])
    failed = len(results) - successful
    
    logger.info(
        f"Email distribution completed for report {report_id}",
        extra={
            "report_id": report_id,
            "successful": successful,
            "failed": failed,
            "total": len(results)
        }
    )
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Email distribution completed',
            'report_id': report_id,
            'successful': successful,
            'failed': failed,
            'total': len(results),
            'results': results
        })
    }


def _get_report_details(report_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Retrieve report details from DynamoDB.
    
    Args:
        report_id: Report ID
        tenant_id: Tenant ID
        
    Returns:
        Report details including S3 key, type, and metadata
    """
    import boto3
    
    dynamodb = boto3.resource('dynamodb')
    reports_table = dynamodb.Table(REPORTS_TABLE)
    
    try:
        response = reports_table.get_item(
            Key={
                'PK': f"TENANT#{tenant_id}",
                'SK': f"REPORT#{report_id}"
            }
        )
        
        if 'Item' not in response:
            raise NotFoundError(f"Report {report_id} not found")
        
        item = response['Item']
        
        return {
            'report_id': report_id,
            'tenant_id': tenant_id,
            'report_type': item.get('reportType'),
            's3_key': item.get('s3Key'),
            'download_url': item.get('downloadUrl'),
            'generated_at': item.get('generatedAt'),
            'project_ids': item.get('projectIds', []),
            'format': item.get('format', 'PDF')
        }
        
    except Exception as e:
        logger.error(
            f"Failed to retrieve report details: {str(e)}",
            extra={"report_id": report_id, "tenant_id": tenant_id}
        )
        raise


def _send_email_with_retry(
    email_sender: EmailSender,
    delivery_logger: DeliveryLogger,
    report_details: Dict[str, Any],
    recipient: str,
    tenant_id: str,
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    Send email with exponential backoff retry logic (Requirement 17.6).
    
    Args:
        email_sender: EmailSender instance
        delivery_logger: DeliveryLogger instance
        report_details: Report details
        recipient: Recipient email address
        tenant_id: Tenant ID
        max_retries: Maximum number of retry attempts (default: 3)
        
    Returns:
        Result dictionary with success status and details
    """
    report_id = report_details['report_id']
    attempt = 0
    last_error = None
    
    while attempt < max_retries:
        attempt += 1
        
        try:
            logger.info(
                f"Sending email to {recipient} (attempt {attempt}/{max_retries})",
                extra={
                    "report_id": report_id,
                    "recipient": recipient,
                    "attempt": attempt
                }
            )
            
            # Send email (Requirement 17.4: PDF attachment + inline summary)
            message_id = email_sender.send_report_email(
                recipient=recipient,
                report_details=report_details,
                tenant_id=tenant_id
            )
            
            # Log successful delivery (Requirement 17.7)
            delivery_logger.log_success(
                report_id=report_id,
                recipient=recipient,
                tenant_id=tenant_id,
                message_id=message_id,
                attempt=attempt
            )
            
            logger.info(
                f"Email sent successfully to {recipient}",
                extra={
                    "report_id": report_id,
                    "recipient": recipient,
                    "message_id": message_id,
                    "attempt": attempt
                }
            )
            
            return {
                'success': True,
                'recipient': recipient,
                'message_id': message_id,
                'attempts': attempt
            }
            
        except Exception as e:
            last_error = str(e)
            
            logger.warning(
                f"Email send attempt {attempt} failed for {recipient}: {last_error}",
                extra={
                    "report_id": report_id,
                    "recipient": recipient,
                    "attempt": attempt,
                    "error": last_error
                }
            )
            
            # Log failed attempt (Requirement 17.7)
            delivery_logger.log_attempt(
                report_id=report_id,
                recipient=recipient,
                tenant_id=tenant_id,
                attempt=attempt,
                success=False,
                error=last_error
            )
            
            if attempt < max_retries:
                # Exponential backoff: 2^attempt seconds (2s, 4s, 8s)
                backoff_time = 2 ** attempt
                logger.info(
                    f"Retrying in {backoff_time} seconds",
                    extra={
                        "report_id": report_id,
                        "recipient": recipient,
                        "backoff_time": backoff_time
                    }
                )
                time.sleep(backoff_time)
    
    # All retries exhausted
    logger.error(
        f"Failed to send email to {recipient} after {max_retries} attempts",
        extra={
            "report_id": report_id,
            "recipient": recipient,
            "last_error": last_error
        }
    )
    
    # Log final failure (Requirement 17.7)
    delivery_logger.log_failure(
        report_id=report_id,
        recipient=recipient,
        tenant_id=tenant_id,
        attempts=max_retries,
        error=last_error
    )
    
    return {
        'success': False,
        'recipient': recipient,
        'error': last_error,
        'attempts': max_retries
    }
