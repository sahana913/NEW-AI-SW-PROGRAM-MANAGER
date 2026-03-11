"""Unit tests for document processing service."""

import json
import os
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

import pytest

# Set environment variables before importing handler
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
os.environ['DOCUMENTS_TABLE'] = 'test-documents-table'
os.environ['NOTIFICATION_TOPIC_ARN'] = 'arn:aws:sns:us-east-1:123456789012:test-topic'

from src.document_processing.handler import (
    lambda_handler,
    process_document,
    extract_text_from_document,
    handle_processing_failure
)


@pytest.fixture
def mock_context():
    """Create mock Lambda context."""
    context = Mock()
    context.request_id = 'test-request-id'
    return context


@pytest.fixture
def s3_event_record():
    """Create mock S3 event record."""
    return {
        's3': {
            'bucket': {
                'name': 'test-bucket'
            },
            'object': {
                'key': 'tenant-123/documents/doc-456/test.pdf'
            }
        }
    }


@pytest.fixture
def document_metadata():
    """Create mock document metadata."""
    return {
        'documentId': 'doc-456',
        'tenantId': 'tenant-123',
        'projectId': 'project-789',
        'fileName': 'test.pdf',
        'uploadedBy': 'user-123',
        'status': 'PENDING_UPLOAD'
    }


@patch('src.document_processing.handler.s3_client')
@patch('src.document_processing.handler.textract_client')
@patch('src.document_processing.handler.dynamodb')
@patch('src.document_processing.handler.sns_client')
def test_process_document_pdf_success(mock_sns, mock_dynamodb, mock_textract, mock_s3, mock_context, s3_event_record, document_metadata):
    """Test successful PDF document processing."""
    # Setup mocks
    mock_table = MagicMock()
    mock_dynamodb.Table.return_value = mock_table
    mock_table.get_item.return_value = {'Item': document_metadata}
    
    mock_textract.detect_document_text.return_value = {
        'Blocks': [
            {'BlockType': 'LINE', 'Text': 'Line 1'},
            {'BlockType': 'LINE', 'Text': 'Line 2'},
            {'BlockType': 'WORD', 'Text': 'Word'}  # Should be ignored
        ]
    }
    
    # Create event
    event = {
        'Records': [s3_event_record]
    }
    
    # Execute
    response = lambda_handler(event, mock_context)
    
    # Verify response
    assert response['statusCode'] == 200
    
    # Verify Textract was called
    mock_textract.detect_document_text.assert_called_once()
    call_args = mock_textract.detect_document_text.call_args
    assert call_args[1]['Document']['S3Object']['Bucket'] == 'test-bucket'
    assert call_args[1]['Document']['S3Object']['Name'] == 'tenant-123/documents/doc-456/test.pdf'
    
    # Verify DynamoDB updates
    assert mock_table.update_item.call_count == 2  # IN_PROGRESS and COMPLETED
    
    # Verify final update includes extracted text
    final_update = mock_table.update_item.call_args_list[1]
    assert 'extractedText' in final_update[1]['UpdateExpression']
    assert final_update[1]['ExpressionAttributeValues'][':status'] == 'COMPLETED'


@patch('src.document_processing.handler.s3_client')
@patch('src.document_processing.handler.dynamodb')
@patch('src.document_processing.handler.sns_client')
def test_process_document_txt_success(mock_sns, mock_dynamodb, mock_s3, mock_context, document_metadata):
    """Test successful TXT document processing."""
    # Setup mocks
    mock_table = MagicMock()
    mock_dynamodb.Table.return_value = mock_table
    mock_table.get_item.return_value = {'Item': document_metadata}
    
    # Mock S3 get_object for text file
    mock_response = MagicMock()
    mock_response['Body'].read.return_value = b'This is test content'
    mock_s3.get_object.return_value = mock_response
    
    # Create event with TXT file
    event = {
        'Records': [{
            's3': {
                'bucket': {'name': 'test-bucket'},
                'object': {'key': 'tenant-123/documents/doc-456/test.txt'}
            }
        }]
    }
    
    # Execute
    response = lambda_handler(event, mock_context)
    
    # Verify response
    assert response['statusCode'] == 200
    
    # Verify S3 get_object was called
    mock_s3.get_object.assert_called_once()
    
    # Verify DynamoDB updates
    assert mock_table.update_item.call_count == 2


@patch('src.document_processing.handler.s3_client')
@patch('src.document_processing.handler.textract_client')
@patch('src.document_processing.handler.dynamodb')
@patch('src.document_processing.handler.sns_client')
def test_process_document_failure_notification(mock_sns, mock_dynamodb, mock_textract, mock_s3, mock_context, s3_event_record, document_metadata):
    """Test that processing failure sends user notification."""
    # Setup mocks
    mock_table = MagicMock()
    mock_dynamodb.Table.return_value = mock_table
    mock_table.get_item.return_value = {'Item': document_metadata}
    
    # Make Textract fail
    mock_textract.detect_document_text.side_effect = Exception('Textract error')
    
    # Create event
    event = {
        'Records': [s3_event_record]
    }
    
    # Execute (should raise exception)
    with pytest.raises(Exception):
        lambda_handler(event, mock_context)
    
    # Verify status updated to FAILED
    failed_update_calls = [
        call for call in mock_table.update_item.call_args_list
        if ':status' in call[1].get('ExpressionAttributeValues', {})
        and call[1]['ExpressionAttributeValues'][':status'] == 'FAILED'
    ]
    assert len(failed_update_calls) > 0
    
    # Verify SNS notification sent
    mock_sns.publish.assert_called_once()
    call_args = mock_sns.publish.call_args
    assert call_args[1]['TopicArn'] == 'arn:aws:sns:us-east-1:123456789012:test-topic'
    
    # Verify notification message
    message = json.loads(call_args[1]['Message'])
    assert message['type'] == 'DOCUMENT_PROCESSING_FAILED'
    assert message['documentId'] == 'doc-456'
    assert message['userId'] == 'user-123'


@patch('src.document_processing.handler.s3_client')
@patch('src.document_processing.handler.dynamodb')
def test_extract_text_from_txt_file(mock_dynamodb, mock_s3):
    """Test text extraction from TXT file."""
    # Mock S3 response
    mock_response = MagicMock()
    mock_response['Body'].read.return_value = b'Test content from TXT file'
    mock_s3.get_object.return_value = mock_response
    
    # Execute
    text = extract_text_from_document('test-bucket', 'path/to/file.txt')
    
    # Verify
    assert text == 'Test content from TXT file'
    mock_s3.get_object.assert_called_once_with(Bucket='test-bucket', Key='path/to/file.txt')


@patch('src.document_processing.handler.textract_client')
def test_extract_text_from_pdf_file(mock_textract):
    """Test text extraction from PDF file."""
    # Mock Textract response
    mock_textract.detect_document_text.return_value = {
        'Blocks': [
            {'BlockType': 'LINE', 'Text': 'First line'},
            {'BlockType': 'LINE', 'Text': 'Second line'},
            {'BlockType': 'LINE', 'Text': 'Third line'}
        ]
    }
    
    # Execute
    text = extract_text_from_document('test-bucket', 'path/to/file.pdf')
    
    # Verify
    assert text == 'First line\nSecond line\nThird line'
    mock_textract.detect_document_text.assert_called_once()


@patch('src.document_processing.handler.dynamodb')
def test_process_document_invalid_key_format(mock_dynamodb, mock_context):
    """Test processing with invalid S3 key format."""
    # Create event with invalid key format
    event = {
        'Records': [{
            's3': {
                'bucket': {'name': 'test-bucket'},
                'object': {'key': 'invalid/key/format'}  # Missing 'documents' segment
            }
        }]
    }
    
    # Execute (should not raise exception, just log warning)
    response = lambda_handler(event, mock_context)
    
    # Verify response
    assert response['statusCode'] == 200
    
    # Verify no DynamoDB calls were made
    mock_dynamodb.Table.assert_not_called()


@patch('src.document_processing.handler.dynamodb')
@patch('src.document_processing.handler.sns_client')
def test_handle_processing_failure_updates_status(mock_sns, mock_dynamodb):
    """Test that processing failure updates document status."""
    # Setup mocks
    mock_table = MagicMock()
    mock_dynamodb.Table.return_value = mock_table
    
    document_metadata = {
        'documentId': 'doc-123',
        'uploadedBy': 'user-456',
        'fileName': 'test.pdf'
    }
    
    error = Exception('Test error')
    
    # Execute
    handle_processing_failure(
        tenant_id='tenant-789',
        document_id='doc-123',
        document_metadata=document_metadata,
        error=error,
        request_id='request-123'
    )
    
    # Verify status update
    mock_table.update_item.assert_called_once()
    call_args = mock_table.update_item.call_args
    assert call_args[1]['ExpressionAttributeValues'][':status'] == 'FAILED'
    assert 'Test error' in call_args[1]['ExpressionAttributeValues'][':error']


@patch('src.document_processing.handler.s3_client')
@patch('src.document_processing.handler.dynamodb')
def test_extract_text_unsupported_format(mock_dynamodb, mock_s3):
    """Test text extraction with unsupported file format."""
    from src.shared.errors import ProcessingError
    
    # Execute with unsupported format - should raise ProcessingError
    with pytest.raises(ProcessingError):
        extract_text_from_document('test-bucket', 'path/to/file.exe')
