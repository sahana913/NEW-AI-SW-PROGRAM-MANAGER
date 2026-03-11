"""
Document upload Lambda handler.

Implements upload_document endpoint with pre-signed S3 URL generation.
Validates file format (PDF, DOCX, TXT) and file size (max 50MB).
Stores document metadata in DynamoDB Documents table.

Requirements: 5.1, 5.2, 5.3, 5.4
"""

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict

import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from shared.constants import (
    ALLOWED_FILE_FORMATS,
    MAX_FILE_SIZE_BYTES,
    VALID_DOCUMENT_TYPES
)
from shared.errors import ValidationError, AppError
from shared.validators import (
    validate_tenant_id,
    validate_uuid,
    validate_file_format,
    validate_file_size,
    validate_required_fields
)
from shared.logger import log_error, log_api_request, log_data_modification

# Initialize AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# Environment variables
DOCUMENTS_BUCKET = os.environ.get('DOCUMENTS_BUCKET')
DOCUMENTS_TABLE = os.environ.get('DOCUMENTS_TABLE', 'ai-sw-pm-documents')

# Initialize logger
logger = Logger(service="document-upload")

# Pre-signed URL expiration (15 minutes)
PRESIGNED_URL_EXPIRATION = 900


def lambda_handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    """
    Handle document upload request.
    
    Generates pre-signed S3 URL for document upload and stores metadata.
    
    Args:
        event: Lambda event containing request data
        context: Lambda context
        
    Returns:
        API Gateway response with pre-signed URL
    """
    request_id = context.request_id
    start_time = datetime.utcnow()
    
    try:
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        
        # Extract authorization context
        authorizer_context = event.get('requestContext', {}).get('authorizer', {})
        user_id = authorizer_context.get('userId')
        tenant_id = authorizer_context.get('tenantId')
        
        if not user_id or not tenant_id:
            raise ValidationError("Missing authorization context")
        
        # Validate tenant ID
        tenant_id = validate_tenant_id(tenant_id)
        
        # Validate required fields
        validate_required_fields(body, [
            'projectId',
            'documentType',
            'fileName',
            'fileSize',
            'contentType'
        ])
        
        # Extract and validate request parameters
        project_id = validate_uuid(body['projectId'], 'projectId')
        document_type = body['documentType'].upper()
        file_name = body['fileName']
        file_size = int(body['fileSize'])
        content_type = body['contentType']
        
        # Validate document type
        if document_type not in VALID_DOCUMENT_TYPES:
            raise ValidationError(
                f"Invalid document type. Must be one of: {', '.join(VALID_DOCUMENT_TYPES)}",
                field="documentType"
            )
        
        # Validate file format (Requirement 5.1, 5.3)
        validate_file_format(file_name, ALLOWED_FILE_FORMATS)
        
        # Validate file size (Requirement 5.2)
        validate_file_size(file_size, max_size_mb=50)
        
        # Generate document ID
        document_id = str(uuid.uuid4())
        
        # Generate S3 key with tenant-specific prefix (Requirement 5.4)
        s3_key = f"{tenant_id}/documents/{document_id}/{file_name}"
        
        # Generate pre-signed URL for upload
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': DOCUMENTS_BUCKET,
                'Key': s3_key,
                'ContentType': content_type,
                'ContentLength': file_size
            },
            ExpiresIn=PRESIGNED_URL_EXPIRATION
        )
        
        # Store document metadata in DynamoDB (Requirement 5.4)
        table = dynamodb.Table(DOCUMENTS_TABLE)
        timestamp = datetime.utcnow().isoformat()
        
        document_metadata = {
            'PK': f"TENANT#{tenant_id}",
            'SK': f"DOCUMENT#{document_id}",
            'GSI1PK': f"PROJECT#{project_id}",
            'GSI1SK': f"DOCUMENT#{timestamp}",
            'documentId': document_id,
            'tenantId': tenant_id,
            'projectId': project_id,
            'documentType': document_type,
            'fileName': file_name,
            'fileSize': file_size,
            'contentType': content_type,
            's3Key': s3_key,
            's3Bucket': DOCUMENTS_BUCKET,
            'uploadedBy': user_id,
            'uploadedAt': timestamp,
            'status': 'PENDING_UPLOAD',
            'processingStatus': 'NOT_STARTED'
        }
        
        table.put_item(Item=document_metadata)
        
        # Log data modification
        log_data_modification(
            logger,
            user_id=user_id,
            tenant_id=tenant_id,
            operation_type='CREATE',
            entity_type='DOCUMENT',
            entity_id=document_id,
            changes={'fileName': file_name, 'documentType': document_type}
        )
        
        # Calculate response time
        response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        # Log API request
        log_api_request(
            logger,
            request_id=request_id,
            user_id=user_id,
            tenant_id=tenant_id,
            endpoint='/documents/upload',
            method='POST',
            response_time_ms=response_time_ms,
            status_code=200
        )
        
        # Return response
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'documentId': document_id,
                'uploadUrl': presigned_url,
                'expiresIn': PRESIGNED_URL_EXPIRATION
            })
        }
        
    except ValidationError as e:
        response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        log_error(logger, e, context={'request_id': request_id})
        
        if 'user_id' in locals() and 'tenant_id' in locals():
            log_api_request(
                logger,
                request_id=request_id,
                user_id=user_id,
                tenant_id=tenant_id,
                endpoint='/documents/upload',
                method='POST',
                response_time_ms=response_time_ms,
                status_code=e.status_code,
                error=e.message
            )
        
        return {
            'statusCode': e.status_code,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(e.to_dict())
        }
        
    except Exception as e:
        response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        log_error(logger, e, context={'request_id': request_id}, severity='CRITICAL')
        
        if 'user_id' in locals() and 'tenant_id' in locals():
            log_api_request(
                logger,
                request_id=request_id,
                user_id=user_id,
                tenant_id=tenant_id,
                endpoint='/documents/upload',
                method='POST',
                response_time_ms=response_time_ms,
                status_code=500,
                error=str(e)
            )
        
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': {
                    'code': 'INTERNAL_ERROR',
                    'message': 'An internal error occurred'
                }
            })
        }
