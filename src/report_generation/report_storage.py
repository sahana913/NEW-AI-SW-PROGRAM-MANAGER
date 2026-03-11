"""Report storage utilities for DynamoDB and S3."""

import sys
import os
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import uuid

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError

from shared.logger import get_logger
from shared.errors import DataError

logger = get_logger()

# AWS clients (initialized lazily)
_dynamodb = None
_s3 = None

# Environment variables
REPORTS_TABLE = os.environ.get('REPORTS_TABLE', 'ai-sw-pm-reports')
REPORTS_BUCKET = os.environ.get('REPORTS_BUCKET', 'ai-sw-pm-reports-bucket')


def get_dynamodb():
    """Get or create DynamoDB resource."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource('dynamodb')
    return _dynamodb


def get_s3():
    """Get or create S3 client."""
    global _s3
    if _s3 is None:
        _s3 = boto3.client('s3')
    return _s3


def store_report_html(
    tenant_id: str,
    report_id: str,
    html_content: str
) -> str:
    """
    Store HTML report in S3.
    
    Args:
        tenant_id: Tenant ID
        report_id: Report ID
        html_content: HTML content to store
        
    Returns:
        S3 key where report was stored
        
    Raises:
        DataError: If storage fails
    """
    try:
        s3 = get_s3()
        
        # S3 key with tenant isolation
        s3_key = f"{tenant_id}/reports/{report_id}.html"
        
        # Upload to S3
        s3.put_object(
            Bucket=REPORTS_BUCKET,
            Key=s3_key,
            Body=html_content.encode('utf-8'),
            ContentType='text/html',
            ServerSideEncryption='AES256'
        )
        
        logger.info(
            f"Report HTML stored in S3",
            extra={"tenant_id": tenant_id, "report_id": report_id, "s3_key": s3_key}
        )
        
        return s3_key
        
    except ClientError as e:
        raise DataError(
            f"Failed to store report in S3: {str(e)}",
            data_source="S3"
        )


def generate_presigned_url(s3_key: str, expiration: int = 86400) -> str:
    """
    Generate pre-signed URL for report download.
    
    Validates: Property 46 - Download Link Expiration (24 hours)
    
    Args:
        s3_key: S3 key of the report
        expiration: URL expiration time in seconds (default 24 hours)
        
    Returns:
        Pre-signed URL
        
    Raises:
        DataError: If URL generation fails
    """
    try:
        s3 = get_s3()
        
        url = s3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': REPORTS_BUCKET,
                'Key': s3_key
            },
            ExpiresIn=expiration
        )
        
        return url
        
    except ClientError as e:
        raise DataError(
            f"Failed to generate pre-signed URL: {str(e)}",
            data_source="S3"
        )


def store_report_metadata(
    tenant_id: str,
    report_id: str,
    report_type: str,
    project_ids: List[str],
    format: str,
    s3_key: str,
    generated_by: str,
    sections: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Store report metadata in DynamoDB.
    
    Validates: Property 38 - Report Metadata Persistence
    
    Args:
        tenant_id: Tenant ID
        report_id: Report ID
        report_type: Type of report (WEEKLY_STATUS, EXECUTIVE_SUMMARY)
        project_ids: List of project IDs included in report
        format: Report format (HTML, PDF)
        s3_key: S3 key where report is stored
        generated_by: User ID who generated the report
        sections: Optional list of sections included (for customization)
        
    Returns:
        Stored report metadata
        
    Raises:
        DataError: If storage fails
    """
    try:
        dynamodb = get_dynamodb()
        reports_table = dynamodb.Table(REPORTS_TABLE)
        
        now = datetime.utcnow()
        expires_at = now + timedelta(days=1)  # 24 hour expiration
        
        # Generate download URL
        download_url = generate_presigned_url(s3_key, expiration=86400)
        
        # Prepare item
        item = {
            'PK': f'TENANT#{tenant_id}',
            'SK': f'REPORT#{report_id}',
            'reportId': report_id,
            'reportType': report_type,
            'projectIds': project_ids,
            'format': format,
            's3Key': s3_key,
            'generatedAt': now.isoformat(),
            'generatedBy': generated_by,
            'downloadUrl': download_url,
            'expiresAt': expires_at.isoformat(),
            'GSI1PK': f'TENANT#{tenant_id}#TYPE#{report_type}',
            'GSI1SK': f'REPORT#{now.isoformat()}'
        }
        
        if sections:
            item['sections'] = sections
        
        # Store in DynamoDB
        reports_table.put_item(Item=item)
        
        logger.info(
            f"Report metadata stored",
            extra={
                "tenant_id": tenant_id,
                "report_id": report_id,
                "report_type": report_type
            }
        )
        
        return item
        
    except ClientError as e:
        raise DataError(
            f"Failed to store report metadata: {str(e)}",
            data_source="DynamoDB"
        )


def get_report_metadata(tenant_id: str, report_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve report metadata from DynamoDB.
    
    Args:
        tenant_id: Tenant ID
        report_id: Report ID
        
    Returns:
        Report metadata or None if not found
        
    Raises:
        DataError: If retrieval fails
    """
    try:
        dynamodb = get_dynamodb()
        reports_table = dynamodb.Table(REPORTS_TABLE)
        
        response = reports_table.get_item(
            Key={
                'PK': f'TENANT#{tenant_id}',
                'SK': f'REPORT#{report_id}'
            }
        )
        
        return response.get('Item')
        
    except ClientError as e:
        raise DataError(
            f"Failed to retrieve report metadata: {str(e)}",
            data_source="DynamoDB"
        )


def list_reports(
    tenant_id: str,
    report_type: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    List reports for a tenant.
    
    Args:
        tenant_id: Tenant ID
        report_type: Optional filter by report type
        limit: Maximum number of reports to return
        
    Returns:
        List of report metadata
        
    Raises:
        DataError: If query fails
    """
    try:
        dynamodb = get_dynamodb()
        reports_table = dynamodb.Table(REPORTS_TABLE)
        
        if report_type:
            # Query using GSI for type filtering
            response = reports_table.query(
                IndexName='GSI1',
                KeyConditionExpression=Key('GSI1PK').eq(f'TENANT#{tenant_id}#TYPE#{report_type}'),
                ScanIndexForward=False,  # Most recent first
                Limit=limit
            )
        else:
            # Query all reports for tenant
            response = reports_table.query(
                KeyConditionExpression=Key('PK').eq(f'TENANT#{tenant_id}') & Key('SK').begins_with('REPORT#'),
                ScanIndexForward=False,  # Most recent first
                Limit=limit
            )
        
        return response.get('Items', [])
        
    except ClientError as e:
        raise DataError(
            f"Failed to list reports: {str(e)}",
            data_source="DynamoDB"
        )


def delete_expired_reports():
    """
    Delete expired reports from S3 and DynamoDB.
    
    This would typically be run as a scheduled Lambda function.
    
    Returns:
        Number of reports deleted
    """
    try:
        dynamodb = get_dynamodb()
        s3 = get_s3()
        reports_table = dynamodb.Table(REPORTS_TABLE)
        
        now = datetime.utcnow().isoformat()
        
        # Scan for expired reports (in production, use a more efficient approach)
        response = reports_table.scan(
            FilterExpression=Attr('expiresAt').lt(now)
        )
        
        expired_reports = response.get('Items', [])
        deleted_count = 0
        
        for report in expired_reports:
            try:
                # Delete from S3
                s3_key = report.get('s3Key')
                if s3_key:
                    s3.delete_object(Bucket=REPORTS_BUCKET, Key=s3_key)
                
                # Delete from DynamoDB
                reports_table.delete_item(
                    Key={
                        'PK': report['PK'],
                        'SK': report['SK']
                    }
                )
                
                deleted_count += 1
                
            except Exception as e:
                logger.error(
                    f"Failed to delete expired report",
                    extra={"report_id": report.get('reportId'), "error": str(e)}
                )
        
        logger.info(f"Deleted {deleted_count} expired reports")
        
        return deleted_count
        
    except Exception as e:
        logger.error(f"Failed to delete expired reports: {str(e)}")
        return 0
