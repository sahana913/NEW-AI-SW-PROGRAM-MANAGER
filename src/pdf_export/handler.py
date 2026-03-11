"""Main Lambda handler for PDF export service."""

import sys
import os
import json
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3
from botocore.exceptions import ClientError

from shared.logger import get_logger
from shared.decorators import with_logging, with_error_handling, with_tenant_isolation
from shared.errors import ValidationError, ProcessingError, DataError

from .pdf_generator import convert_html_to_pdf, validate_pdf_generation
from .pdf_storage import store_pdf_in_s3, generate_pdf_download_url
from .tenant_config import get_tenant_branding_config

logger = get_logger()

# AWS clients
_s3 = None
_sns = None

# Environment variables
REPORTS_BUCKET = os.environ.get('REPORTS_BUCKET', 'ai-sw-pm-reports-bucket')
NOTIFICATION_TOPIC_ARN = os.environ.get('NOTIFICATION_TOPIC_ARN', '')


def get_s3():
    """Get or create S3 client."""
    global _s3
    if _s3 is None:
        _s3 = boto3.client('s3')
    return _s3


def get_sns():
    """Get or create SNS client."""
    global _sns
    if _sns is None:
        _sns = boto3.client('sns')
    return _sns


def get_html_from_s3(tenant_id: str, report_id: str) -> str:
    """
    Retrieve HTML report from S3.
    
    Args:
        tenant_id: Tenant ID
        report_id: Report ID
    
    Returns:
        HTML content as string
    
    Raises:
        DataError: If retrieval fails
    """
    try:
        s3 = get_s3()
        
        # Construct S3 key with tenant isolation
        s3_key = f"{tenant_id}/reports/{report_id}.html"
        
        logger.info(
            "Retrieving HTML report from S3",
            extra={"tenant_id": tenant_id, "report_id": report_id, "s3_key": s3_key}
        )
        
        # Get object from S3
        response = s3.get_object(
            Bucket=REPORTS_BUCKET,
            Key=s3_key
        )
        
        html_content = response['Body'].read().decode('utf-8')
        
        logger.info(
            "HTML report retrieved successfully",
            extra={"tenant_id": tenant_id, "report_id": report_id}
        )
        
        return html_content
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            logger.error(
                "HTML report not found in S3",
                extra={"tenant_id": tenant_id, "report_id": report_id}
            )
            raise DataError(
                f"HTML report not found for report {report_id}",
                data_source="S3"
            )
        else:
            logger.error(
                "Failed to retrieve HTML report from S3",
                extra={"tenant_id": tenant_id, "report_id": report_id, "error": str(e)}
            )
            raise DataError(
                f"Failed to retrieve HTML report: {str(e)}",
                data_source="S3"
            )


def send_failure_notification(
    tenant_id: str,
    user_id: str,
    report_id: str,
    error_message: str
):
    """
    Send notification to user about PDF generation failure.
    
    Validates: Property 48 - PDF Generation Failure Notification
    
    Args:
        tenant_id: Tenant ID
        user_id: User ID who requested the PDF
        report_id: Report ID
        error_message: Error message to include
    """
    try:
        if not NOTIFICATION_TOPIC_ARN:
            logger.warning("No notification topic configured, skipping notification")
            return
        
        sns = get_sns()
        
        message = {
            'type': 'PDF_GENERATION_FAILURE',
            'tenant_id': tenant_id,
            'user_id': user_id,
            'report_id': report_id,
            'error_message': error_message,
            'timestamp': logger.get_timestamp()
        }
        
        logger.info(
            "Sending PDF generation failure notification",
            extra={"tenant_id": tenant_id, "user_id": user_id, "report_id": report_id}
        )
        
        sns.publish(
            TopicArn=NOTIFICATION_TOPIC_ARN,
            Subject=f'PDF Generation Failed for Report {report_id}',
            Message=json.dumps(message),
            MessageAttributes={
                'tenant_id': {'DataType': 'String', 'StringValue': tenant_id},
                'user_id': {'DataType': 'String', 'StringValue': user_id},
                'notification_type': {'DataType': 'String', 'StringValue': 'PDF_GENERATION_FAILURE'}
            }
        )
        
        logger.info(
            "PDF generation failure notification sent successfully",
            extra={"tenant_id": tenant_id, "user_id": user_id, "report_id": report_id}
        )
        
    except Exception as e:
        logger.error(
            "Failed to send PDF generation failure notification",
            extra={
                "tenant_id": tenant_id,
                "user_id": user_id,
                "report_id": report_id,
                "error": str(e)
            }
        )


@with_logging
@with_error_handling
@with_tenant_isolation
def export_report_to_pdf_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for exporting HTML reports to PDF format.
    
    Validates: Property 44 - PDF Format Conversion
    Validates: Property 45 - Tenant Branding Application
    Validates: Property 46 - Download Link Expiration (24 hours)
    Validates: Property 47 - PDF Tenant Isolation
    Validates: Property 48 - PDF Generation Failure Notification
    
    Path parameters:
    - reportId: Report ID to export
    
    Query parameters:
    - expiration (optional): URL expiration in seconds (default 86400 = 24 hours)
    
    Returns:
        API Gateway response with PDF download URL
    """
    # Extract tenant_id from event (injected by with_tenant_isolation)
    tenant_id = event.get('tenant_id')
    
    # Extract user_id from authorizer context
    authorizer_context = event.get("requestContext", {}).get("authorizer", {})
    user_id = authorizer_context.get("userId", "unknown")
    
    # Extract path parameters
    path_params = event.get('pathParameters') or {}
    report_id = path_params.get('reportId')
    
    if not report_id:
        raise ValidationError("Missing required parameter: reportId")
    
    # Extract query parameters
    query_params = event.get('queryStringParameters') or {}
    expiration = int(query_params.get('expiration', 86400))  # Default 24 hours
    
    # Validate expiration (max 7 days)
    if expiration > 604800:
        raise ValidationError("Expiration cannot exceed 7 days (604800 seconds)")
    
    logger.info(
        "Starting PDF export",
        extra={
            "tenant_id": tenant_id,
            "user_id": user_id,
            "report_id": report_id,
            "expiration": expiration
        }
    )
    
    try:
        # Step 1: Retrieve HTML report from S3
        html_content = get_html_from_s3(tenant_id, report_id)
        
        # Step 2: Get tenant branding configuration (Property 45)
        tenant_config = get_tenant_branding_config(tenant_id)
        
        # Step 3: Convert HTML to PDF with branding (Property 44, 45)
        pdf_bytes = convert_html_to_pdf(html_content, tenant_config)
        
        # Step 4: Validate PDF generation
        if not validate_pdf_generation(pdf_bytes):
            raise ProcessingError(
                "PDF validation failed - generated PDF is invalid",
                processing_type="PDF_Generation"
            )
        
        # Step 5: Store PDF in S3 with tenant isolation (Property 47)
        s3_key = store_pdf_in_s3(tenant_id, report_id, pdf_bytes)
        
        # Step 6: Generate pre-signed download URL (Property 46)
        download_url = generate_pdf_download_url(s3_key, expiration)
        
        # Calculate expiration timestamp
        from datetime import datetime, timedelta
        expires_at = datetime.utcnow() + timedelta(seconds=expiration)
        
        logger.info(
            "PDF export completed successfully",
            extra={
                "tenant_id": tenant_id,
                "report_id": report_id,
                "pdf_size_bytes": len(pdf_bytes),
                "expires_at": expires_at.isoformat()
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
                "format": "PDF",
                "downloadUrl": download_url,
                "expiresAt": expires_at.isoformat(),
                "sizeBytes": len(pdf_bytes),
                "status": "COMPLETED"
            })
        }
        
    except (ValidationError, DataError, ProcessingError) as e:
        # Send failure notification (Property 48)
        send_failure_notification(tenant_id, user_id, report_id, str(e))
        raise
        
    except Exception as e:
        logger.error(
            "Unexpected error during PDF export",
            extra={
                "tenant_id": tenant_id,
                "report_id": report_id,
                "error": str(e)
            }
        )
        # Send failure notification (Property 48)
        send_failure_notification(tenant_id, user_id, report_id, str(e))
        raise


@with_logging
@with_error_handling
@with_tenant_isolation
def batch_export_reports_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for batch exporting multiple reports to PDF.
    
    This can be triggered by EventBridge for scheduled report generation.
    
    Body:
    {
        "reportIds": ["report-id-1", "report-id-2", ...],
        "expiration": 86400  // optional
    }
    
    Returns:
        Summary of batch export results
    """
    # Extract tenant_id from event (injected by with_tenant_isolation)
    tenant_id = event.get('tenant_id')
    
    # Extract user_id from authorizer context
    authorizer_context = event.get("requestContext", {}).get("authorizer", {})
    user_id = authorizer_context.get("userId", "system")
    
    # Parse body
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        raise ValidationError("Invalid JSON in request body")
    
    report_ids = body.get('reportIds', [])
    expiration = body.get('expiration', 86400)
    
    if not report_ids:
        raise ValidationError("Missing required field: reportIds")
    
    if not isinstance(report_ids, list):
        raise ValidationError("reportIds must be an array")
    
    logger.info(
        "Starting batch PDF export",
        extra={
            "tenant_id": tenant_id,
            "user_id": user_id,
            "report_count": len(report_ids)
        }
    )
    
    results = {
        'successful': [],
        'failed': []
    }
    
    for report_id in report_ids:
        try:
            # Retrieve HTML
            html_content = get_html_from_s3(tenant_id, report_id)
            
            # Get tenant branding
            tenant_config = get_tenant_branding_config(tenant_id)
            
            # Convert to PDF
            pdf_bytes = convert_html_to_pdf(html_content, tenant_config)
            
            # Validate
            if not validate_pdf_generation(pdf_bytes):
                raise ProcessingError("PDF validation failed")
            
            # Store in S3
            s3_key = store_pdf_in_s3(tenant_id, report_id, pdf_bytes)
            
            # Generate download URL
            download_url = generate_pdf_download_url(s3_key, expiration)
            
            results['successful'].append({
                'reportId': report_id,
                'downloadUrl': download_url,
                'sizeBytes': len(pdf_bytes)
            })
            
            logger.info(
                "PDF export successful for report",
                extra={"tenant_id": tenant_id, "report_id": report_id}
            )
            
        except Exception as e:
            logger.error(
                "PDF export failed for report",
                extra={"tenant_id": tenant_id, "report_id": report_id, "error": str(e)}
            )
            
            results['failed'].append({
                'reportId': report_id,
                'error': str(e)
            })
            
            # Send failure notification
            send_failure_notification(tenant_id, user_id, report_id, str(e))
    
    logger.info(
        "Batch PDF export completed",
        extra={
            "tenant_id": tenant_id,
            "successful_count": len(results['successful']),
            "failed_count": len(results['failed'])
        }
    )
    
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps({
            "totalReports": len(report_ids),
            "successfulExports": len(results['successful']),
            "failedExports": len(results['failed']),
            "results": results
        })
    }
