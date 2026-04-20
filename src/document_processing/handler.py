"""
Document processing Lambda handler.

Processes uploaded documents by extracting text using AWS Textract.
Handles processing failures with user notification.

Requirements: 5.5, 5.7
"""

from shared.logger import log_data_modification, log_error
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict

import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))


# Initialize AWS clients
s3_client = boto3.client("s3")
textract_client = boto3.client("textract")
dynamodb = boto3.resource("dynamodb")
sns_client = boto3.client("sns")

# Environment variables
DOCUMENTS_TABLE = os.environ.get("DOCUMENTS_TABLE", "ai-sw-pm-documents")
NOTIFICATION_TOPIC_ARN = os.environ.get("NOTIFICATION_TOPIC_ARN")

# Initialize logger
logger = Logger(service="document-processing")


def lambda_handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    """
    Handle document processing triggered by S3 upload event.

    Extracts text from uploaded documents using AWS Textract.

    Args:
        event: S3 event notification
        context: Lambda context

    Returns:
        Processing result
    """
    request_id = context.request_id

    try:
        # Process each S3 record
        for record in event.get("Records", []):
            process_document(record, request_id)

        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Documents processed successfully"}),
        }

    except Exception as e:
        log_error(logger, e, context={"request_id": request_id}, severity="CRITICAL")
        raise


def process_document(record: Dict[str, Any], request_id: str) -> None:
    """
    Process a single document.

    Args:
        record: S3 event record
        request_id: Request ID for logging
    """
    try:
        # Extract S3 information
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        logger.info(f"Processing document: s3://{bucket}/{key}")

        # Parse tenant ID and document ID from S3 key
        # Expected format: {tenant_id}/documents/{document_id}/{filename}
        key_parts = key.split("/")
        if len(key_parts) < 4 or key_parts[1] != "documents":
            logger.warning(f"Invalid S3 key format: {key}")
            return

        tenant_id = key_parts[0]
        document_id = key_parts[2]

        # Get document metadata from DynamoDB
        table = dynamodb.Table(DOCUMENTS_TABLE)
        response = table.get_item(
            Key={"PK": f"TENANT#{tenant_id}", "SK": f"DOCUMENT#{document_id}"}
        )

        if "Item" not in response:
            logger.warning(f"Document metadata not found: {document_id}")
            return

        document_metadata = response["Item"]

        # Update processing status to IN_PROGRESS
        table.update_item(
            Key={"PK": f"TENANT#{tenant_id}", "SK": f"DOCUMENT#{document_id}"},
            UpdateExpression="SET processingStatus = :status, processingStartedAt = :timestamp",
            ExpressionAttributeValues={
                ":status": "IN_PROGRESS",
                ":timestamp": datetime.utcnow().isoformat(),
            },
        )

        # Extract text using AWS Textract (Requirement 5.5)
        extracted_text = extract_text_from_document(bucket, key)

        # Update document metadata with extracted text
        table.update_item(
            Key={"PK": f"TENANT#{tenant_id}", "SK": f"DOCUMENT#{document_id}"},
            UpdateExpression="SET processingStatus = :status, extractedText = :text, "
            "processingCompletedAt = :timestamp, #st = :doc_status",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":status": "COMPLETED",
                ":text": extracted_text,
                ":timestamp": datetime.utcnow().isoformat(),
                ":doc_status": "UPLOADED",
            },
        )

        # Log successful processing
        log_data_modification(
            logger,
            user_id=document_metadata.get("uploadedBy", "SYSTEM"),
            tenant_id=tenant_id,
            operation_type="UPDATE",
            entity_type="DOCUMENT",
            entity_id=document_id,
            changes={"processingStatus": "COMPLETED"},
        )

        logger.info(f"Successfully processed document: {document_id}")

    except Exception as e:
        # Handle processing failure (Requirement 5.7)
        handle_processing_failure(
            tenant_id=tenant_id if "tenant_id" in locals() else None,
            document_id=document_id if "document_id" in locals() else None,
            document_metadata=(
                document_metadata if "document_metadata" in locals() else None
            ),
            error=e,
            request_id=request_id,
        )
        raise


def extract_text_from_document(bucket: str, key: str) -> str:
    """
    Extract text from document using AWS Textract.

    Args:
        bucket: S3 bucket name
        key: S3 object key

    Returns:
        Extracted text content

    Raises:
        ProcessingError: If text extraction fails
    """
    try:
        # Determine file type from key
        file_extension = key.lower().split(".")[-1]

        if file_extension == "txt":
            # For text files, read directly from S3
            response = s3_client.get_object(Bucket=bucket, Key=key)
            text = response["Body"].read().decode("utf-8")
            return text

        elif file_extension in ["pdf", "docx"]:
            # For PDF and DOCX, use Textract
            response = textract_client.detect_document_text(
                Document={"S3Object": {"Bucket": bucket, "Name": key}}
            )

            # Extract text from Textract response
            text_blocks = []
            for block in response.get("Blocks", []):
                if block["BlockType"] == "LINE":
                    text_blocks.append(block["Text"])

            return "\n".join(text_blocks)

        else:
            raise ProcessingError(
                f"Unsupported file format: {file_extension}",
                processing_type="text_extraction",
            )

    except ProcessingError:
        # Re-raise ProcessingError as-is
        raise
    except Exception as e:
        logger.error(f"Text extraction failed: {str(e)}")
        raise ProcessingError(
            f"Failed to extract text from document: {str(e)}",
            processing_type="text_extraction",
        )


def handle_processing_failure(
    tenant_id: str,
    document_id: str,
    document_metadata: Dict[str, Any],
    error: Exception,
    request_id: str,
) -> None:
    """
    Handle document processing failure.

    Updates document status and notifies user (Requirement 5.7).

    Args:
        tenant_id: Tenant ID
        document_id: Document ID
        document_metadata: Document metadata
        error: Exception that occurred
        request_id: Request ID for logging
    """
    try:
        # Update document status to FAILED
        if tenant_id and document_id:
            table = dynamodb.Table(DOCUMENTS_TABLE)
            table.update_item(
                Key={"PK": f"TENANT#{tenant_id}", "SK": f"DOCUMENT#{document_id}"},
                UpdateExpression="SET processingStatus = :status, processingError = :error, "
                "processingFailedAt = :timestamp",
                ExpressionAttributeValues={
                    ":status": "FAILED",
                    ":error": str(error),
                    ":timestamp": datetime.utcnow().isoformat(),
                },
            )

        # Send notification to user
        if NOTIFICATION_TOPIC_ARN and document_metadata:
            user_id = document_metadata.get("uploadedBy")
            file_name = document_metadata.get("fileName")

            notification_message = {
                "type": "DOCUMENT_PROCESSING_FAILED",
                "tenantId": tenant_id,
                "userId": user_id,
                "documentId": document_id,
                "fileName": file_name,
                "error": str(error),
                "timestamp": datetime.utcnow().isoformat(),
            }

            sns_client.publish(
                TopicArn=NOTIFICATION_TOPIC_ARN,
                Subject="Document Processing Failed",
                Message=json.dumps(notification_message),
            )

            logger.info(f"Sent failure notification for document: {document_id}")

        # Log the failure
        log_error(
            logger,
            error,
            context={
                "request_id": request_id,
                "tenant_id": tenant_id,
                "document_id": document_id,
                "file_name": (
                    document_metadata.get("fileName") if document_metadata else None
                ),
            },
            severity="ERROR",
        )

    except Exception as notification_error:
        logger.error(f"Failed to handle processing failure: {str(notification_error)}")
