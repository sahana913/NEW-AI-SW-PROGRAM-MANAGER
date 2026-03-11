"""Tests for PDF export service."""

import sys
import os
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from pdf_export.pdf_generator import (
    apply_tenant_branding,
    convert_html_to_pdf,
    validate_pdf_generation
)
from pdf_export.pdf_storage import (
    store_pdf_in_s3,
    generate_pdf_download_url,
    get_pdf_from_s3,
    delete_pdf_from_s3
)
from pdf_export.tenant_config import (
    get_tenant_branding_config,
    update_tenant_branding_config
)
from pdf_export.handler import (
    export_report_to_pdf_handler,
    batch_export_reports_handler,
    get_html_from_s3,
    send_failure_notification
)


# Sample HTML content for testing
SAMPLE_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Test Report</title>
    <style>
        body { font-family: Arial; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
        h2 { color: #667eea; border-bottom: 3px solid #667eea; }
        th { background: #667eea; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Weekly Status Report</h1>
    </div>
    <div class="section">
        <h2>Executive Summary</h2>
        <p>This is a test report.</p>
    </div>
</body>
</html>
"""


class TestPDFGenerator:
    """Tests for PDF generation functionality."""
    
    def test_apply_tenant_branding_with_config(self):
        """
        Test applying tenant branding to HTML.
        
        Validates: Property 45 - Tenant Branding Application
        """
        tenant_config = {
            'logo_url': 'https://example.com/logo.png',
            'primary_color': '#ff0000',
            'secondary_color': '#00ff00',
            'company_name': 'Test Corp'
        }
        
        branded_html = apply_tenant_branding(SAMPLE_HTML, tenant_config)
        
        # Verify colors were replaced
        assert '#ff0000' in branded_html
        assert '#00ff00' in branded_html
        assert '#667eea' not in branded_html or branded_html.count('#667eea') < SAMPLE_HTML.count('#667eea')
        
        # Verify logo was added
        assert 'https://example.com/logo.png' in branded_html
        assert 'Test Corp Logo' in branded_html
        
        # Verify company name in footer
        assert 'Test Corp' in branded_html
    
    def test_apply_tenant_branding_without_config(self):
        """Test applying branding with no configuration (uses defaults)."""
        branded_html = apply_tenant_branding(SAMPLE_HTML, None)
        
        # Should return original HTML unchanged
        assert branded_html == SAMPLE_HTML
    
    def test_apply_tenant_branding_partial_config(self):
        """Test applying branding with partial configuration."""
        tenant_config = {
            'primary_color': '#ff0000',
            # No logo, secondary color, or company name
        }
        
        branded_html = apply_tenant_branding(SAMPLE_HTML, tenant_config)
        
        # Verify primary color was replaced
        assert '#ff0000' in branded_html
        
        # Should not crash with missing fields
        assert branded_html is not None
    
    @patch('pdf_export.pdf_generator.WEASYPRINT_AVAILABLE', True)
    @patch('pdf_export.pdf_generator.HTML')
    def test_convert_html_to_pdf_success(self, mock_html_class):
        """
        Test successful HTML to PDF conversion.
        
        Validates: Property 44 - PDF Format Conversion
        """
        # Mock WeasyPrint HTML class
        mock_html_instance = Mock()
        mock_html_instance.write_pdf.return_value = b'%PDF-1.4\n%fake pdf content' + b'\x00' * 2000
        mock_html_class.return_value = mock_html_instance
        
        pdf_bytes = convert_html_to_pdf(SAMPLE_HTML)
        
        # Verify PDF was generated
        assert pdf_bytes is not None
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        
        # Verify HTML class was called
        mock_html_class.assert_called_once()
        mock_html_instance.write_pdf.assert_called_once()
    
    @patch('pdf_export.pdf_generator.WEASYPRINT_AVAILABLE', False)
    def test_convert_html_to_pdf_weasyprint_not_available(self):
        """Test PDF conversion when WeasyPrint is not available."""
        from shared.errors import ProcessingError
        
        with pytest.raises(ProcessingError) as exc_info:
            convert_html_to_pdf(SAMPLE_HTML)
        
        assert "WeasyPrint is not available" in str(exc_info.value)
    
    @patch('pdf_export.pdf_generator.WEASYPRINT_AVAILABLE', True)
    @patch('pdf_export.pdf_generator.HTML')
    def test_convert_html_to_pdf_with_branding(self, mock_html_class):
        """Test PDF conversion with tenant branding applied."""
        mock_html_instance = Mock()
        mock_html_instance.write_pdf.return_value = b'%PDF-1.4\n%fake pdf content' + b'\x00' * 2000
        mock_html_class.return_value = mock_html_instance
        
        tenant_config = {
            'logo_url': 'https://example.com/logo.png',
            'primary_color': '#ff0000',
            'company_name': 'Test Corp'
        }
        
        pdf_bytes = convert_html_to_pdf(SAMPLE_HTML, tenant_config)
        
        # Verify PDF was generated
        assert pdf_bytes is not None
        
        # Verify HTML was modified with branding before conversion
        call_args = mock_html_class.call_args
        html_string = call_args[1]['string']
        assert '#ff0000' in html_string
        assert 'Test Corp' in html_string
    
    def test_validate_pdf_generation_valid(self):
        """Test PDF validation with valid PDF."""
        valid_pdf = b'%PDF-1.4\n%fake pdf content' + b'\x00' * 2000
        
        assert validate_pdf_generation(valid_pdf) is True
    
    def test_validate_pdf_generation_invalid_header(self):
        """Test PDF validation with invalid header."""
        invalid_pdf = b'<html>not a pdf</html>'
        
        assert validate_pdf_generation(invalid_pdf) is False
    
    def test_validate_pdf_generation_too_small(self):
        """Test PDF validation with suspiciously small file."""
        small_pdf = b'%PDF-1.4\n'
        
        assert validate_pdf_generation(small_pdf) is False
    
    def test_validate_pdf_generation_empty(self):
        """Test PDF validation with empty bytes."""
        assert validate_pdf_generation(b'') is False
        assert validate_pdf_generation(None) is False


class TestPDFStorage:
    """Tests for PDF storage functionality."""
    
    @patch('pdf_export.pdf_storage.get_s3')
    def test_store_pdf_in_s3_success(self, mock_get_s3):
        """
        Test storing PDF in S3 with tenant isolation.
        
        Validates: Property 47 - PDF Tenant Isolation
        """
        mock_s3 = Mock()
        mock_get_s3.return_value = mock_s3
        
        tenant_id = 'tenant-123'
        report_id = 'report-456'
        pdf_bytes = b'%PDF-1.4\nfake pdf'
        
        s3_key = store_pdf_in_s3(tenant_id, report_id, pdf_bytes)
        
        # Verify S3 key includes tenant ID for isolation (Property 47)
        assert s3_key == f'{tenant_id}/reports/{report_id}.pdf'
        
        # Verify S3 put_object was called with correct parameters
        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs['Key'] == s3_key
        assert call_kwargs['Body'] == pdf_bytes
        assert call_kwargs['ContentType'] == 'application/pdf'
        assert call_kwargs['ServerSideEncryption'] == 'AES256'
        assert call_kwargs['Metadata']['tenant_id'] == tenant_id
    
    @patch('pdf_export.pdf_storage.get_s3')
    def test_generate_pdf_download_url_success(self, mock_get_s3):
        """
        Test generating pre-signed URL for PDF download.
        
        Validates: Property 46 - Download Link Expiration (24 hours)
        """
        mock_s3 = Mock()
        mock_s3.generate_presigned_url.return_value = 'https://s3.amazonaws.com/signed-url'
        mock_get_s3.return_value = mock_s3
        
        s3_key = 'tenant-123/reports/report-456.pdf'
        expiration = 86400  # 24 hours
        
        url = generate_pdf_download_url(s3_key, expiration)
        
        # Verify URL was generated
        assert url == 'https://s3.amazonaws.com/signed-url'
        
        # Verify expiration is 24 hours (Property 46)
        mock_s3.generate_presigned_url.assert_called_once()
        call_kwargs = mock_s3.generate_presigned_url.call_args[1]
        assert call_kwargs['ExpiresIn'] == 86400
        assert call_kwargs['Params']['ResponseContentType'] == 'application/pdf'
    
    @patch('pdf_export.pdf_storage.get_s3')
    def test_get_pdf_from_s3_success(self, mock_get_s3):
        """Test retrieving PDF from S3."""
        mock_s3 = Mock()
        mock_response = {
            'Body': Mock(read=Mock(return_value=b'%PDF-1.4\nfake pdf'))
        }
        mock_s3.get_object.return_value = mock_response
        mock_get_s3.return_value = mock_s3
        
        tenant_id = 'tenant-123'
        report_id = 'report-456'
        
        pdf_bytes = get_pdf_from_s3(tenant_id, report_id)
        
        # Verify PDF was retrieved
        assert pdf_bytes == b'%PDF-1.4\nfake pdf'
        
        # Verify correct S3 key was used
        mock_s3.get_object.assert_called_once()
        call_kwargs = mock_s3.get_object.call_args[1]
        assert call_kwargs['Key'] == f'{tenant_id}/reports/{report_id}.pdf'
    
    @patch('pdf_export.pdf_storage.get_s3')
    def test_get_pdf_from_s3_not_found(self, mock_get_s3):
        """Test retrieving non-existent PDF from S3."""
        from botocore.exceptions import ClientError
        from shared.errors import DataError
        
        mock_s3 = Mock()
        mock_s3.get_object.side_effect = ClientError(
            {'Error': {'Code': 'NoSuchKey'}},
            'GetObject'
        )
        mock_get_s3.return_value = mock_s3
        
        with pytest.raises(DataError) as exc_info:
            get_pdf_from_s3('tenant-123', 'report-456')
        
        assert 'not found' in str(exc_info.value).lower()
    
    @patch('pdf_export.pdf_storage.get_s3')
    def test_delete_pdf_from_s3_success(self, mock_get_s3):
        """Test deleting PDF from S3."""
        mock_s3 = Mock()
        mock_get_s3.return_value = mock_s3
        
        tenant_id = 'tenant-123'
        report_id = 'report-456'
        
        result = delete_pdf_from_s3(tenant_id, report_id)
        
        # Verify deletion succeeded
        assert result is True
        
        # Verify correct S3 key was used
        mock_s3.delete_object.assert_called_once()
        call_kwargs = mock_s3.delete_object.call_args[1]
        assert call_kwargs['Key'] == f'{tenant_id}/reports/{report_id}.pdf'


class TestTenantConfig:
    """Tests for tenant configuration functionality."""
    
    @patch('pdf_export.tenant_config.get_dynamodb')
    def test_get_tenant_branding_config_success(self, mock_get_dynamodb):
        """Test retrieving tenant branding configuration."""
        mock_table = Mock()
        mock_table.get_item.return_value = {
            'Item': {
                'PK': 'TENANT#tenant-123',
                'SK': 'CONFIG',
                'branding': {
                    'logo_url': 'https://example.com/logo.png',
                    'primary_color': '#ff0000',
                    'secondary_color': '#00ff00',
                    'company_name': 'Test Corp'
                }
            }
        }
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_get_dynamodb.return_value = mock_dynamodb
        
        config = get_tenant_branding_config('tenant-123')
        
        # Verify configuration was retrieved
        assert config is not None
        assert config['logo_url'] == 'https://example.com/logo.png'
        assert config['primary_color'] == '#ff0000'
        assert config['secondary_color'] == '#00ff00'
        assert config['company_name'] == 'Test Corp'
    
    @patch('pdf_export.tenant_config.get_dynamodb')
    def test_get_tenant_branding_config_not_found(self, mock_get_dynamodb):
        """Test retrieving branding config when none exists."""
        mock_table = Mock()
        mock_table.get_item.return_value = {}
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_get_dynamodb.return_value = mock_dynamodb
        
        config = get_tenant_branding_config('tenant-123')
        
        # Should return None for missing config
        assert config is None
    
    @patch('pdf_export.tenant_config.get_dynamodb')
    def test_update_tenant_branding_config_success(self, mock_get_dynamodb):
        """Test updating tenant branding configuration."""
        mock_table = Mock()
        mock_table.update_item.return_value = {
            'Attributes': {
                'branding': {
                    'logo_url': 'https://new-logo.com/logo.png',
                    'primary_color': '#0000ff',
                    'secondary_color': '#00ff00',
                    'company_name': 'New Corp'
                }
            }
        }
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_get_dynamodb.return_value = mock_dynamodb
        
        config = update_tenant_branding_config(
            'tenant-123',
            logo_url='https://new-logo.com/logo.png',
            primary_color='#0000ff',
            company_name='New Corp'
        )
        
        # Verify configuration was updated
        assert config['logo_url'] == 'https://new-logo.com/logo.png'
        assert config['primary_color'] == '#0000ff'
        assert config['company_name'] == 'New Corp'


class TestPDFExportHandler:
    """Tests for PDF export Lambda handler."""
    
    @patch('pdf_export.handler.get_html_from_s3')
    @patch('pdf_export.handler.get_tenant_branding_config')
    @patch('pdf_export.handler.convert_html_to_pdf')
    @patch('pdf_export.handler.validate_pdf_generation')
    @patch('pdf_export.handler.store_pdf_in_s3')
    @patch('pdf_export.handler.generate_pdf_download_url')
    def test_export_report_to_pdf_handler_success(
        self,
        mock_generate_url,
        mock_store_pdf,
        mock_validate,
        mock_convert,
        mock_get_branding,
        mock_get_html
    ):
        """
        Test successful PDF export.
        
        Validates: Property 44, 45, 46, 47 - Complete PDF export workflow
        """
        # Setup mocks
        mock_get_html.return_value = SAMPLE_HTML
        mock_get_branding.return_value = {'primary_color': '#ff0000'}
        mock_convert.return_value = b'%PDF-1.4\nfake pdf' + b'\x00' * 2000
        mock_validate.return_value = True
        mock_store_pdf.return_value = 'tenant-123/reports/report-456.pdf'
        mock_generate_url.return_value = 'https://s3.amazonaws.com/signed-url'
        
        # Create event
        event = {
            'tenant_id': 'tenant-123',
            'pathParameters': {'reportId': 'report-456'},
            'queryStringParameters': {},
            'requestContext': {
                'authorizer': {'userId': 'user-789'}
            }
        }
        
        # Call handler
        response = export_report_to_pdf_handler(event, None)
        
        # Verify response
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['reportId'] == 'report-456'
        assert body['format'] == 'PDF'
        assert body['downloadUrl'] == 'https://s3.amazonaws.com/signed-url'
        assert body['status'] == 'COMPLETED'
        assert 'expiresAt' in body
        assert 'sizeBytes' in body
        
        # Verify all steps were called
        mock_get_html.assert_called_once_with('tenant-123', 'report-456')
        mock_get_branding.assert_called_once_with('tenant-123')
        mock_convert.assert_called_once()
        mock_validate.assert_called_once()
        mock_store_pdf.assert_called_once()
        mock_generate_url.assert_called_once()
    
    @patch('pdf_export.handler.get_html_from_s3')
    @patch('pdf_export.handler.send_failure_notification')
    def test_export_report_to_pdf_handler_html_not_found(
        self,
        mock_send_notification,
        mock_get_html
    ):
        """
        Test PDF export when HTML report not found.
        
        Validates: Property 48 - PDF Generation Failure Notification
        """
        from shared.errors import DataError
        
        # Setup mock to raise error
        mock_get_html.side_effect = DataError("HTML report not found", data_source="S3")
        
        # Create event
        event = {
            'tenant_id': 'tenant-123',
            'pathParameters': {'reportId': 'report-456'},
            'queryStringParameters': {},
            'requestContext': {
                'authorizer': {'userId': 'user-789'}
            }
        }
        
        # Call handler - should raise error
        with pytest.raises(DataError):
            export_report_to_pdf_handler(event, None)
        
        # Verify failure notification was sent (Property 48)
        mock_send_notification.assert_called_once()
        call_args = mock_send_notification.call_args[0]
        assert call_args[0] == 'tenant-123'
        assert call_args[1] == 'user-789'
        assert call_args[2] == 'report-456'
        assert 'not found' in call_args[3].lower()
    
    @patch('pdf_export.handler.get_html_from_s3')
    @patch('pdf_export.handler.get_tenant_branding_config')
    @patch('pdf_export.handler.convert_html_to_pdf')
    @patch('pdf_export.handler.validate_pdf_generation')
    @patch('pdf_export.handler.send_failure_notification')
    def test_export_report_to_pdf_handler_invalid_pdf(
        self,
        mock_send_notification,
        mock_validate,
        mock_convert,
        mock_get_branding,
        mock_get_html
    ):
        """Test PDF export when generated PDF is invalid."""
        # Setup mocks
        mock_get_html.return_value = SAMPLE_HTML
        mock_get_branding.return_value = None
        mock_convert.return_value = b'invalid pdf'
        mock_validate.return_value = False  # PDF validation fails
        
        # Create event
        event = {
            'tenant_id': 'tenant-123',
            'pathParameters': {'reportId': 'report-456'},
            'queryStringParameters': {},
            'requestContext': {
                'authorizer': {'userId': 'user-789'}
            }
        }
        
        # Call handler - should raise error
        from shared.errors import ProcessingError
        with pytest.raises(ProcessingError):
            export_report_to_pdf_handler(event, None)
        
        # Verify failure notification was sent
        mock_send_notification.assert_called_once()
    
    @patch('pdf_export.handler.get_html_from_s3')
    @patch('pdf_export.handler.get_tenant_branding_config')
    @patch('pdf_export.handler.convert_html_to_pdf')
    @patch('pdf_export.handler.validate_pdf_generation')
    @patch('pdf_export.handler.store_pdf_in_s3')
    @patch('pdf_export.handler.generate_pdf_download_url')
    def test_batch_export_reports_handler_success(
        self,
        mock_generate_url,
        mock_store_pdf,
        mock_validate,
        mock_convert,
        mock_get_branding,
        mock_get_html
    ):
        """Test successful batch PDF export."""
        # Setup mocks
        mock_get_html.return_value = SAMPLE_HTML
        mock_get_branding.return_value = None
        mock_convert.return_value = b'%PDF-1.4\nfake pdf' + b'\x00' * 2000
        mock_validate.return_value = True
        mock_store_pdf.side_effect = lambda t, r, p: f'{t}/reports/{r}.pdf'
        mock_generate_url.return_value = 'https://s3.amazonaws.com/signed-url'
        
        # Create event
        event = {
            'tenant_id': 'tenant-123',
            'body': json.dumps({
                'reportIds': ['report-1', 'report-2', 'report-3'],
                'expiration': 86400
            }),
            'requestContext': {
                'authorizer': {'userId': 'user-789'}
            }
        }
        
        # Call handler
        response = batch_export_reports_handler(event, None)
        
        # Verify response
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['totalReports'] == 3
        assert body['successfulExports'] == 3
        assert body['failedExports'] == 0
        assert len(body['results']['successful']) == 3
        assert len(body['results']['failed']) == 0
    
    @patch('pdf_export.handler.get_html_from_s3')
    @patch('pdf_export.handler.get_tenant_branding_config')
    @patch('pdf_export.handler.send_failure_notification')
    def test_batch_export_reports_handler_partial_failure(
        self,
        mock_send_notification,
        mock_get_branding,
        mock_get_html
    ):
        """Test batch PDF export with some failures."""
        from shared.errors import DataError
        
        # Setup mocks - first call succeeds, second fails, third succeeds
        mock_get_html.side_effect = [
            SAMPLE_HTML,
            DataError("Not found", data_source="S3"),
            SAMPLE_HTML
        ]
        mock_get_branding.return_value = None
        
        # Create event
        event = {
            'tenant_id': 'tenant-123',
            'body': json.dumps({
                'reportIds': ['report-1', 'report-2', 'report-3']
            }),
            'requestContext': {
                'authorizer': {'userId': 'user-789'}
            }
        }
        
        # Call handler with additional mocks
        with patch('pdf_export.handler.convert_html_to_pdf') as mock_convert, \
             patch('pdf_export.handler.validate_pdf_generation') as mock_validate, \
             patch('pdf_export.handler.store_pdf_in_s3') as mock_store, \
             patch('pdf_export.handler.generate_pdf_download_url') as mock_url:
            
            mock_convert.return_value = b'%PDF-1.4\nfake' + b'\x00' * 2000
            mock_validate.return_value = True
            mock_store.side_effect = lambda t, r, p: f'{t}/reports/{r}.pdf'
            mock_url.return_value = 'https://s3.amazonaws.com/signed-url'
            
            response = batch_export_reports_handler(event, None)
        
        # Verify response
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['totalReports'] == 3
        assert body['successfulExports'] == 2
        assert body['failedExports'] == 1
        
        # Verify failure notification was sent for failed report
        assert mock_send_notification.call_count == 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
