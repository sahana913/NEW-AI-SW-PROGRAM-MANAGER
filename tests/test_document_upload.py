"""Unit tests for document upload service."""

import json
import os
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

import pytest

# Set environment variables before importing handler
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
os.environ['DOCUMENTS_BUCKET'] = 'test-documents-bucket'
os.environ['DOCUMENTS_TABLE'] = 'test-documents-table'

from src.document_upload.handler import lambda_handler
from src.shared.errors import ValidationError


@pytest.fixture
def mock_context():
    """Create mock Lambda context."""
    context = Mock()
    context.request_id = 'test-request-id'
    return context


@pytest.fixture
def mock_authorizer_context():
    """Create mock authorizer context."""
    return {
        'userId': '550e8400-e29b-41d4-a716-446655440000',
        'tenantId': '660e8400-e29b-41d4-a716-446655440001'
    }


@pytest.fixture
def valid_upload_request():
    """Create valid upload request."""
    return {
        'projectId': '770e8400-e29b-41d4-a716-446655440002',
        'documentType': 'SOW',
        'fileName': 'test-document.pdf',
        'fileSize': 1024000,  # 1MB
        'contentType': 'application/pdf'
    }


@patch('src.document_upload.handler.s3_client')
@patch('src.document_upload.handler.dynamodb')
def test_upload_document_success(mock_dynamodb, mock_s3, mock_context, mock_authorizer_context, valid_upload_request):
    """Test successful document upload."""
    # Setup mocks
    mock_table = MagicMock()
    mock_dynamodb.Table.return_value = mock_table
    mock_s3.generate_presigned_url.return_value = 'https://s3.amazonaws.com/presigned-url'
    
    # Create event
    event = {
        'body': json.dumps(valid_upload_request),
        'requestContext': {
            'authorizer': mock_authorizer_context
        }
    }
    
    # Execute
    response = lambda_handler(event, mock_context)
    
    # Verify response
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert 'documentId' in body
    assert 'uploadUrl' in body
    assert 'expiresIn' in body
    assert body['uploadUrl'] == 'https://s3.amazonaws.com/presigned-url'
    
    # Verify S3 presigned URL generation
    mock_s3.generate_presigned_url.assert_called_once()
    call_args = mock_s3.generate_presigned_url.call_args
    assert call_args[0][0] == 'put_object'
    assert call_args[1]['Params']['Bucket'] == 'test-documents-bucket'
    assert '660e8400-e29b-41d4-a716-446655440001/documents/' in call_args[1]['Params']['Key']
    
    # Verify DynamoDB put
    mock_table.put_item.assert_called_once()
    item = mock_table.put_item.call_args[1]['Item']
    assert item['tenantId'] == '660e8400-e29b-41d4-a716-446655440001'
    assert item['projectId'] == '770e8400-e29b-41d4-a716-446655440002'
    assert item['documentType'] == 'SOW'
    assert item['fileName'] == 'test-document.pdf'
    assert item['status'] == 'PENDING_UPLOAD'


@patch('src.document_upload.handler.s3_client')
@patch('src.document_upload.handler.dynamodb')
def test_upload_document_invalid_format(mock_dynamodb, mock_s3, mock_context, mock_authorizer_context):
    """Test upload with invalid file format."""
    # Create request with invalid format
    request = {
        'projectId': '770e8400-e29b-41d4-a716-446655440002',
        'documentType': 'SOW',
        'fileName': 'test-document.exe',  # Invalid format
        'fileSize': 1024000,
        'contentType': 'application/octet-stream'
    }
    
    event = {
        'body': json.dumps(request),
        'requestContext': {
            'authorizer': mock_authorizer_context
        }
    }
    
    # Execute
    response = lambda_handler(event, mock_context)
    
    # Verify error response
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Invalid file format' in body['error']['message']


@patch('src.document_upload.handler.s3_client')
@patch('src.document_upload.handler.dynamodb')
def test_upload_document_file_too_large(mock_dynamodb, mock_s3, mock_context, mock_authorizer_context):
    """Test upload with file size exceeding limit."""
    # Create request with file too large
    request = {
        'projectId': '770e8400-e29b-41d4-a716-446655440002',
        'documentType': 'SOW',
        'fileName': 'test-document.pdf',
        'fileSize': 60 * 1024 * 1024,  # 60MB (exceeds 50MB limit)
        'contentType': 'application/pdf'
    }
    
    event = {
        'body': json.dumps(request),
        'requestContext': {
            'authorizer': mock_authorizer_context
        }
    }
    
    # Execute
    response = lambda_handler(event, mock_context)
    
    # Verify error response
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'exceeds maximum' in body['error']['message']


@patch('src.document_upload.handler.s3_client')
@patch('src.document_upload.handler.dynamodb')
def test_upload_document_invalid_document_type(mock_dynamodb, mock_s3, mock_context, mock_authorizer_context):
    """Test upload with invalid document type."""
    # Create request with invalid document type
    request = {
        'projectId': '770e8400-e29b-41d4-a716-446655440002',
        'documentType': 'INVALID_TYPE',
        'fileName': 'test-document.pdf',
        'fileSize': 1024000,
        'contentType': 'application/pdf'
    }
    
    event = {
        'body': json.dumps(request),
        'requestContext': {
            'authorizer': mock_authorizer_context
        }
    }
    
    # Execute
    response = lambda_handler(event, mock_context)
    
    # Verify error response
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Invalid document type' in body['error']['message']


@patch('src.document_upload.handler.s3_client')
@patch('src.document_upload.handler.dynamodb')
def test_upload_document_missing_authorization(mock_dynamodb, mock_s3, mock_context):
    """Test upload without authorization context."""
    request = {
        'projectId': 'project-789',
        'documentType': 'SOW',
        'fileName': 'test-document.pdf',
        'fileSize': 1024000,
        'contentType': 'application/pdf'
    }
    
    event = {
        'body': json.dumps(request),
        'requestContext': {}
    }
    
    # Execute
    response = lambda_handler(event, mock_context)
    
    # Verify error response
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body


@patch('src.document_upload.handler.s3_client')
@patch('src.document_upload.handler.dynamodb')
def test_upload_document_tenant_specific_prefix(mock_dynamodb, mock_s3, mock_context, mock_authorizer_context, valid_upload_request):
    """Test that documents are stored with tenant-specific S3 prefix."""
    # Setup mocks
    mock_table = MagicMock()
    mock_dynamodb.Table.return_value = mock_table
    mock_s3.generate_presigned_url.return_value = 'https://s3.amazonaws.com/presigned-url'
    
    # Create event
    event = {
        'body': json.dumps(valid_upload_request),
        'requestContext': {
            'authorizer': mock_authorizer_context
        }
    }
    
    # Execute
    response = lambda_handler(event, mock_context)
    
    # Verify tenant-specific prefix in S3 key
    call_args = mock_s3.generate_presigned_url.call_args
    s3_key = call_args[1]['Params']['Key']
    assert s3_key.startswith('660e8400-e29b-41d4-a716-446655440001/documents/')
    
    # Verify metadata includes tenant ID
    item = mock_table.put_item.call_args[1]['Item']
    assert item['tenantId'] == '660e8400-e29b-41d4-a716-446655440001'
    assert item['PK'] == 'TENANT#660e8400-e29b-41d4-a716-446655440001'


@patch('src.document_upload.handler.s3_client')
@patch('src.document_upload.handler.dynamodb')
def test_upload_document_missing_required_fields(mock_dynamodb, mock_s3, mock_context, mock_authorizer_context):
    """Test upload with missing required fields."""
    # Create request missing required fields
    request = {
        'projectId': '770e8400-e29b-41d4-a716-446655440002',
        # Missing documentType, fileName, fileSize, contentType
    }
    
    event = {
        'body': json.dumps(request),
        'requestContext': {
            'authorizer': mock_authorizer_context
        }
    }
    
    # Execute
    response = lambda_handler(event, mock_context)
    
    # Verify error response
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'error' in body
    assert 'Missing required fields' in body['error']['message']
