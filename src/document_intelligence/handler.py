"""
Document intelligence Lambda handler.

Main handler for document intelligence operations including:
- SOW milestone extraction
- SLA clause extraction
- Extraction confirmation workflow

Requirements: 11.1, 11.2, 11.4, 11.5, 11.7, 12.1, 12.2, 12.4, 12.5, 12.7
"""

import json
import os
from datetime import datetime
from typing import Any, Dict

import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from shared.errors import ValidationError, ProcessingError, AppError
from shared.validators import validate_tenant_id, validate_uuid, validate_required_fields
from shared.logger import log_error, log_api_request

from document_intelligence.sow_extraction import extract_milestones_from_sow
from document_intelligence.sla_extraction import extract_sla_clauses_from_contract
from document_intelligence.extraction_confirmation import (
    confirm_extraction,
    get_extractions_for_document
)

# Initialize AWS clients (lazily to avoid issues during testing)
dynamodb = None

def _get_dynamodb_resource():
    global dynamodb
    if dynamodb is None:
        dynamodb = boto3.resource('dynamodb')
    return dynamodb

# Environment variables
DOCUMENTS_TABLE = os.environ.get('DOCUMENTS_TABLE', 'ai-sw-pm-documents')

# Initialize logger
logger = Logger(service="document-intelligence")


def lambda_handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    """
    Handle document intelligence requests.
    
    Supports:
    - POST /documents/{documentId}/extract - Trigger extraction
    - GET /documents/{documentId}/extractions - Get extractions
    - PUT /documents/{documentId}/extractions/{extractionId}/confirm - Confirm extraction
    
    Args:
        event: Lambda event containing request data
        context: Lambda context
        
    Returns:
        API Gateway response
    """
    request_id = context.request_id
    start_time = datetime.utcnow()
    
    try:
        # Extract HTTP method and path
        http_method = event.get('httpMethod', event.get('requestContext', {}).get('http', {}).get('method'))
        path = event.get('path', event.get('rawPath', ''))
        
        # Extract authorization context
        authorizer_context = event.get('requestContext', {}).get('authorizer', {})
        user_id = authorizer_context.get('userId')
        tenant_id = authorizer_context.get('tenantId')
        
        if not user_id or not tenant_id:
            raise ValidationError("Missing authorization context")
        
        # Validate tenant ID
        tenant_id = validate_tenant_id(tenant_id)
        
        # Route request
        if http_method == 'POST' and '/extract' in path:
            response = handle_extract_request(event, user_id, tenant_id)
        elif http_method == 'GET' and '/extractions' in path:
            response = handle_get_extractions_request(event, user_id, tenant_id)
        elif http_method == 'PUT' and '/confirm' in path:
            response = handle_confirm_extraction_request(event, user_id, tenant_id)
        else:
            raise ValidationError(f"Unsupported operation: {http_method} {path}")
        
        # Calculate response time
        response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        # Log API request
        log_api_request(
            logger,
            request_id=request_id,
            user_id=user_id,
            tenant_id=tenant_id,
            endpoint=path,
            method=http_method,
            response_time_ms=response_time_ms,
            status_code=200
        )
        
        return response
        
    except ValidationError as e:
        response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        log_error(logger, e, context={'request_id': request_id})
        
        if 'user_id' in locals() and 'tenant_id' in locals():
            log_api_request(
                logger,
                request_id=request_id,
                user_id=user_id,
                tenant_id=tenant_id,
                endpoint=path if 'path' in locals() else 'unknown',
                method=http_method if 'http_method' in locals() else 'unknown',
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
                endpoint=path if 'path' in locals() else 'unknown',
                method=http_method if 'http_method' in locals() else 'unknown',
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


def handle_extract_request(
    event: Dict[str, Any],
    user_id: str,
    tenant_id: str
) -> Dict[str, Any]:
    """
    Handle document extraction request.
    
    POST /documents/{documentId}/extract
    
    Args:
        event: Lambda event
        user_id: User ID
        tenant_id: Tenant ID
        
    Returns:
        API Gateway response
    """
    # Extract document ID from path
    path_parameters = event.get('pathParameters', {})
    document_id = path_parameters.get('documentId')
    
    if not document_id:
        raise ValidationError("Missing documentId in path", field="documentId")
    
    document_id = validate_uuid(document_id, 'documentId')
    
    # Get document metadata
    db = _get_dynamodb_resource()
    table = db.Table(DOCUMENTS_TABLE)
    response = table.scan(
        FilterExpression='documentId = :doc_id AND tenantId = :tenant_id',
        ExpressionAttributeValues={
            ':doc_id': document_id,
            ':tenant_id': tenant_id
        },
        Limit=1
    )
    
    items = response.get('Items', [])
    if not items:
        raise ValidationError("Document not found", field="documentId")
    
    document = items[0]
    
    # Check if document has been processed
    if document.get('processingStatus') != 'COMPLETED':
        raise ValidationError(
            "Document has not been processed yet. Please wait for text extraction to complete.",
            field="processingStatus"
        )
    
    # Get extracted text
    extracted_text = document.get('extractedText', '')
    if not extracted_text:
        raise ProcessingError(
            "No extracted text available for document",
            processing_type='text_extraction'
        )
    
    # Determine document type and extract accordingly
    document_type = document.get('documentType')
    
    if document_type == 'SOW':
        # Extract milestones from SOW
        extractions = extract_milestones_from_sow(
            document_id=document_id,
            tenant_id=tenant_id,
            extracted_text=extracted_text
        )
        extraction_type = 'MILESTONE'
    elif document_type in ['BRD', 'TECHNICAL_SPEC']:
        # Extract SLA clauses from contract/technical documents
        extractions = extract_sla_clauses_from_contract(
            document_id=document_id,
            tenant_id=tenant_id,
            extracted_text=extracted_text
        )
        extraction_type = 'SLA'
    else:
        raise ValidationError(
            f"Document type {document_type} does not support extraction",
            field="documentType"
        )
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'documentId': document_id,
            'extractionType': extraction_type,
            'extractionCount': len(extractions),
            'message': f'Extracted {len(extractions)} {extraction_type.lower()}(s) from document'
        })
    }


def handle_get_extractions_request(
    event: Dict[str, Any],
    user_id: str,
    tenant_id: str
) -> Dict[str, Any]:
    """
    Handle get extractions request.
    
    GET /documents/{documentId}/extractions
    
    Args:
        event: Lambda event
        user_id: User ID
        tenant_id: Tenant ID
        
    Returns:
        API Gateway response
    """
    # Extract document ID from path
    path_parameters = event.get('pathParameters', {})
    document_id = path_parameters.get('documentId')
    
    if not document_id:
        raise ValidationError("Missing documentId in path", field="documentId")
    
    document_id = validate_uuid(document_id, 'documentId')
    
    # Get query parameters
    query_parameters = event.get('queryStringParameters') or {}
    status_filter = query_parameters.get('status')
    
    # Get extractions
    extractions = get_extractions_for_document(
        document_id=document_id,
        tenant_id=tenant_id,
        status_filter=status_filter
    )
    
    # Format extractions for response
    formatted_extractions = []
    for extraction in extractions:
        formatted_extraction = {
            'extractionId': extraction.get('extractionId'),
            'type': extraction.get('type'),
            'content': json.loads(extraction.get('content', '{}')),
            'confidence': extraction.get('confidence'),
            'requiresReview': extraction.get('requiresReview', False),
            'status': extraction.get('status'),
            'createdAt': extraction.get('createdAt'),
            'confirmedBy': extraction.get('confirmedBy'),
            'confirmedAt': extraction.get('confirmedAt')
        }
        formatted_extractions.append(formatted_extraction)
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'documentId': document_id,
            'extractions': formatted_extractions,
            'totalCount': len(formatted_extractions)
        })
    }


def handle_confirm_extraction_request(
    event: Dict[str, Any],
    user_id: str,
    tenant_id: str
) -> Dict[str, Any]:
    """
    Handle extraction confirmation request.
    
    PUT /documents/{documentId}/extractions/{extractionId}/confirm
    
    Args:
        event: Lambda event
        user_id: User ID
        tenant_id: Tenant ID
        
    Returns:
        API Gateway response
    """
    # Extract IDs from path
    path_parameters = event.get('pathParameters', {})
    document_id = path_parameters.get('documentId')
    extraction_id = path_parameters.get('extractionId')
    
    if not document_id:
        raise ValidationError("Missing documentId in path", field="documentId")
    if not extraction_id:
        raise ValidationError("Missing extractionId in path", field="extractionId")
    
    document_id = validate_uuid(document_id, 'documentId')
    extraction_id = validate_uuid(extraction_id, 'extractionId')
    
    # Parse request body
    body = json.loads(event.get('body', '{}'))
    
    # Validate required fields
    validate_required_fields(body, ['confirmed'])
    
    confirmed = body.get('confirmed')
    corrected_content = body.get('correctedContent')
    
    # Confirm extraction
    updated_extraction = confirm_extraction(
        extraction_id=extraction_id,
        document_id=document_id,
        tenant_id=tenant_id,
        user_id=user_id,
        confirmed=confirmed,
        corrected_content=corrected_content
    )
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'extractionId': extraction_id,
            'status': updated_extraction.get('status'),
            'message': f"Extraction {'confirmed' if confirmed else 'rejected'} successfully"
        })
    }
