"""PDF storage utilities for S3 with tenant isolation."""

import sys
import os
from typing import Dict, Any
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3
from botocore.exceptions import ClientError

from shared.logger import get_logger
from shared.errors import DataError

logger = get_logger()

# AWS clients (initialized lazily)
_s3 = None

# Environment variables
REPORTS_BUCKET = os.environ.get('REPORTS_BUCKET', 'ai-sw-pm-reports-bucket')


def get_s3():
    """Get or create S3 client."""
    global _s3
    if _s3 is None:
        _s3 = boto3.client('s3')
    return _s3


def store_pdf_in_s3(
    tenant_id: str,
    report_id: str,
    pdf_bytes: bytes
) -> str:
    """
    Store PDF in S3 with tenant-specific access controls.
    
    Validates: Property 47 - PDF Tenant Isolation
    
    Args:
        tenant_id: Tenant ID for isolation
        report_id: Report ID
        pdf_bytes: PDF content as bytes
    
    Returns:
        S3 key where PDF was stored
    
    Raises:
        DataError: If storage fails
    """
    try:
        s3 = get_s3()
        
        # S3 key with tenant isolation (Property 47)
        s3_key = f"{tenant_id}/reports/{report_id}.pdf"
        
        logger.info(
            "Storing PDF in S3",
            extra={
                "tenant_id": tenant_id,
                "report_id": report_id,
                "s3_key": s3_key,
                "size_bytes": len(pdf_bytes)
            }
        )
        
        # Upload to S3 with encryption and tenant-specific prefix
        s3.put_object(
            Bucket=REPORTS_BUCKET,
            Key=s3_key,
            Body=pdf_bytes,
            ContentType='application/pdf',
            ServerSideEncryption='AES256',
            Metadata={
                'tenant_id': tenant_id,
                'report_id': report_id,
                'generated_at': datetime.utcnow().isoformat()
            }
        )
        
        logger.info(
            "PDF stored successfully in S3",
            extra={"tenant_id": tenant_id, "report_id": report_id, "s3_key": s3_key}
        )
        
        return s3_key
        
    except ClientError as e:
        logger.error(
            "Failed to store PDF in S3",
            extra={"tenant_id": tenant_id, "report_id": report_id, "error": str(e)}
        )
        raise DataError(
            f"Failed to store PDF in S3: {str(e)}",
            data_source="S3"
        )


def generate_pdf_download_url(
    s3_key: str,
    expiration: int = 86400
) -> str:
    """
    Generate pre-signed URL for PDF download.
    
    Validates: Property 46 - Download Link Expiration (24 hours default)
    
    Args:
        s3_key: S3 key of the PDF
        expiration: URL expiration time in seconds (default 86400 = 24 hours)
    
    Returns:
        Pre-signed URL valid for specified duration
    
    Raises:
        DataError: If URL generation fails
    """
    try:
        s3 = get_s3()
        
        logger.info(
            "Generating pre-signed URL for PDF",
            extra={"s3_key": s3_key, "expiration_seconds": expiration}
        )
        
        # Generate pre-signed URL (Property 46 - 24 hour expiration)
        url = s3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': REPORTS_BUCKET,
                'Key': s3_key,
                'ResponseContentDisposition': 'attachment',
                'ResponseContentType': 'application/pdf'
            },
            ExpiresIn=expiration
        )
        
        # Calculate expiration timestamp
        expires_at = datetime.utcnow() + timedelta(seconds=expiration)
        
        logger.info(
            "Pre-signed URL generated successfully",
            extra={"s3_key": s3_key, "expires_at": expires_at.isoformat()}
        )
        
        return url
        
    except ClientError as e:
        logger.error(
            "Failed to generate pre-signed URL",
            extra={"s3_key": s3_key, "error": str(e)}
        )
        raise DataError(
            f"Failed to generate pre-signed URL: {str(e)}",
            data_source="S3"
        )


def get_pdf_from_s3(tenant_id: str, report_id: str) -> bytes:
    """
    Retrieve PDF from S3.
    
    Args:
        tenant_id: Tenant ID
        report_id: Report ID
    
    Returns:
        PDF content as bytes
    
    Raises:
        DataError: If retrieval fails
    """
    try:
        s3 = get_s3()
        
        # Construct S3 key with tenant isolation
        s3_key = f"{tenant_id}/reports/{report_id}.pdf"
        
        logger.info(
            "Retrieving PDF from S3",
            extra={"tenant_id": tenant_id, "report_id": report_id, "s3_key": s3_key}
        )
        
        # Get object from S3
        response = s3.get_object(
            Bucket=REPORTS_BUCKET,
            Key=s3_key
        )
        
        pdf_bytes = response['Body'].read()
        
        logger.info(
            "PDF retrieved successfully",
            extra={"tenant_id": tenant_id, "report_id": report_id, "size_bytes": len(pdf_bytes)}
        )
        
        return pdf_bytes
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            logger.warning(
                "PDF not found in S3",
                extra={"tenant_id": tenant_id, "report_id": report_id}
            )
            raise DataError(
                f"PDF not found for report {report_id}",
                data_source="S3"
            )
        else:
            logger.error(
                "Failed to retrieve PDF from S3",
                extra={"tenant_id": tenant_id, "report_id": report_id, "error": str(e)}
            )
            raise DataError(
                f"Failed to retrieve PDF from S3: {str(e)}",
                data_source="S3"
            )


def delete_pdf_from_s3(tenant_id: str, report_id: str) -> bool:
    """
    Delete PDF from S3.
    
    Args:
        tenant_id: Tenant ID
        report_id: Report ID
    
    Returns:
        True if deleted successfully, False otherwise
    """
    try:
        s3 = get_s3()
        
        # Construct S3 key with tenant isolation
        s3_key = f"{tenant_id}/reports/{report_id}.pdf"
        
        logger.info(
            "Deleting PDF from S3",
            extra={"tenant_id": tenant_id, "report_id": report_id, "s3_key": s3_key}
        )
        
        # Delete object from S3
        s3.delete_object(
            Bucket=REPORTS_BUCKET,
            Key=s3_key
        )
        
        logger.info(
            "PDF deleted successfully",
            extra={"tenant_id": tenant_id, "report_id": report_id}
        )
        
        return True
        
    except ClientError as e:
        logger.error(
            "Failed to delete PDF from S3",
            extra={"tenant_id": tenant_id, "report_id": report_id, "error": str(e)}
        )
        return False
