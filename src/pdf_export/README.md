# PDF Export Service

## Overview

The PDF Export Service converts HTML reports to PDF format with tenant-specific branding and secure storage. It implements Requirements 16.1, 16.3, 16.5, 16.6, and 16.7.

## Features

- **PDF Conversion**: Converts HTML reports to PDF using WeasyPrint
- **Tenant Branding**: Applies custom logos, colors, and company names
- **Secure Storage**: Stores PDFs in S3 with tenant-specific prefixes and encryption
- **Pre-signed URLs**: Generates time-limited download links (default 24 hours)
- **Failure Notifications**: Sends SNS notifications on PDF generation failures
- **Batch Export**: Supports exporting multiple reports in a single operation

## Architecture

```
┌─────────────────┐
│  API Gateway    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────┐
│  PDF Export     │─────▶│  S3 (HTML)   │
│  Lambda         │      └──────────────┘
└────────┬────────┘
         │
         ├─────────────────┐
         │                 │
         ▼                 ▼
┌─────────────────┐  ┌──────────────┐
│  WeasyPrint     │  │  DynamoDB    │
│  (PDF Gen)      │  │  (Tenant     │
└────────┬────────┘  │   Config)    │
         │           └──────────────┘
         ▼
┌─────────────────┐
│  S3 (PDF)       │
│  + Pre-signed   │
│    URL          │
└─────────────────┘
```

## Components

### 1. PDF Generator (`pdf_generator.py`)

Converts HTML to PDF using WeasyPrint with tenant branding.

**Key Functions:**
- `convert_html_to_pdf()`: Main conversion function
- `apply_tenant_branding()`: Applies custom logos and colors
- `validate_pdf_generation()`: Validates generated PDF

**Property Validation:**
- Property 44: PDF Format Conversion
- Property 45: Tenant Branding Application

### 2. PDF Storage (`pdf_storage.py`)

Manages PDF storage in S3 with tenant isolation.

**Key Functions:**
- `store_pdf_in_s3()`: Stores PDF with tenant-specific prefix
- `generate_pdf_download_url()`: Creates pre-signed URLs
- `get_pdf_from_s3()`: Retrieves PDF from S3
- `delete_pdf_from_s3()`: Deletes expired PDFs

**Property Validation:**
- Property 46: Download Link Expiration (24 hours)
- Property 47: PDF Tenant Isolation

### 3. Tenant Configuration (`tenant_config.py`)

Retrieves tenant branding settings from DynamoDB.

**Key Functions:**
- `get_tenant_branding_config()`: Fetches branding settings
- `update_tenant_branding_config()`: Updates branding settings

**Configuration Schema:**
```json
{
  "logo_url": "https://example.com/logo.png",
  "primary_color": "#667eea",
  "secondary_color": "#764ba2",
  "company_name": "Acme Corp"
}
```

### 4. Lambda Handler (`handler.py`)

Main entry point for PDF export operations.

**Endpoints:**
- `POST /reports/{reportId}/export/pdf`: Export single report to PDF
- `POST /reports/export/pdf/batch`: Batch export multiple reports

**Property Validation:**
- Property 44: PDF Format Conversion
- Property 45: Tenant Branding Application
- Property 46: Download Link Expiration
- Property 47: PDF Tenant Isolation
- Property 48: PDF Generation Failure Notification

## API Reference

### Export Report to PDF

**Endpoint:** `POST /reports/{reportId}/export/pdf`

**Path Parameters:**
- `reportId` (required): Report ID to export

**Query Parameters:**
- `expiration` (optional): URL expiration in seconds (default: 86400 = 24 hours, max: 604800 = 7 days)

**Response:**
```json
{
  "reportId": "report-123",
  "format": "PDF",
  "downloadUrl": "https://s3.amazonaws.com/...",
  "expiresAt": "2024-01-02T12:00:00Z",
  "sizeBytes": 524288,
  "status": "COMPLETED"
}
```

**Error Response:**
```json
{
  "error": {
    "code": "PDF_GENERATION_FAILED",
    "message": "Failed to convert HTML to PDF: ...",
    "type": "ProcessingError"
  }
}
```

### Batch Export Reports

**Endpoint:** `POST /reports/export/pdf/batch`

**Request Body:**
```json
{
  "reportIds": ["report-1", "report-2", "report-3"],
  "expiration": 86400
}
```

**Response:**
```json
{
  "totalReports": 3,
  "successfulExports": 2,
  "failedExports": 1,
  "results": {
    "successful": [
      {
        "reportId": "report-1",
        "downloadUrl": "https://...",
        "sizeBytes": 524288
      },
      {
        "reportId": "report-2",
        "downloadUrl": "https://...",
        "sizeBytes": 612352
      }
    ],
    "failed": [
      {
        "reportId": "report-3",
        "error": "HTML report not found"
      }
    ]
  }
}
```

## Tenant Branding

### Configuration

Tenant branding is stored in DynamoDB under the tenant configuration:

```python
{
  'PK': 'TENANT#{tenant_id}',
  'SK': 'CONFIG',
  'branding': {
    'logo_url': 'https://example.com/logo.png',
    'primary_color': '#667eea',
    'secondary_color': '#764ba2',
    'company_name': 'Acme Corp'
  }
}
```

### Branding Application

The PDF generator applies branding by:
1. Replacing default gradient colors with tenant colors
2. Inserting logo image at the top of the report
3. Adding company name to the footer
4. Updating all color references throughout the HTML

### Default Branding

If no tenant branding is configured, the system uses default colors:
- Primary: `#667eea` (purple-blue)
- Secondary: `#764ba2` (purple)
- No logo
- Generic footer text

## S3 Storage Structure

PDFs are stored with tenant-specific prefixes for isolation:

```
s3://ai-sw-pm-reports-bucket/
├── tenant-1/
│   └── reports/
│       ├── report-123.html
│       ├── report-123.pdf
│       ├── report-456.html
│       └── report-456.pdf
├── tenant-2/
│   └── reports/
│       ├── report-789.html
│       └── report-789.pdf
```

**Security:**
- Server-side encryption (AES-256)
- Tenant isolation via prefix
- Pre-signed URLs for time-limited access
- Metadata includes tenant_id for validation

## Error Handling

### PDF Generation Failures

When PDF generation fails, the system:
1. Logs detailed error information
2. Sends SNS notification to configured topic
3. Returns error response to client
4. Does NOT store invalid PDF

**Notification Format:**
```json
{
  "type": "PDF_GENERATION_FAILURE",
  "tenant_id": "tenant-123",
  "user_id": "user-456",
  "report_id": "report-789",
  "error_message": "Failed to convert HTML to PDF: ...",
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### Common Errors

1. **HTML Not Found**: Report HTML doesn't exist in S3
   - Status: 404
   - Action: Verify report was generated successfully

2. **WeasyPrint Not Available**: Library not installed
   - Status: 500
   - Action: Install dependencies: `pip install weasyprint`

3. **Invalid PDF Generated**: PDF validation failed
   - Status: 500
   - Action: Check HTML content for rendering issues

4. **S3 Storage Failed**: Cannot store PDF in S3
   - Status: 500
   - Action: Check S3 permissions and bucket configuration

## Dependencies

### WeasyPrint

WeasyPrint requires system-level dependencies:

**Ubuntu/Debian:**
```bash
sudo apt-get install -y \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info
```

**Amazon Linux 2:**
```bash
sudo yum install -y \
    pango \
    cairo \
    gdk-pixbuf2 \
    libffi-devel
```

**Lambda Layer:**
For AWS Lambda, create a custom layer with WeasyPrint and dependencies, or use a pre-built layer.

### Python Packages

Install from `requirements.txt`:
```bash
pip install -r requirements.txt
```

## Testing

### Unit Tests

```bash
# Run all PDF export tests
pytest tests/test_pdf_export.py -v

# Run specific test
pytest tests/test_pdf_export.py::test_convert_html_to_pdf -v
```

### Integration Tests

```bash
# Test with real S3 and DynamoDB
pytest tests/integration/test_pdf_export_integration.py -v
```

### Manual Testing

```bash
# Export a report to PDF
curl -X POST \
  https://api.example.com/reports/report-123/export/pdf \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json"

# Batch export
curl -X POST \
  https://api.example.com/reports/export/pdf/batch \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "reportIds": ["report-1", "report-2"],
    "expiration": 86400
  }'
```

## Performance Considerations

### PDF Generation Time

- Small reports (<10 pages): ~2-3 seconds
- Medium reports (10-50 pages): ~5-10 seconds
- Large reports (>50 pages): ~15-30 seconds

### Lambda Configuration

Recommended settings:
- Memory: 1024 MB (minimum for WeasyPrint)
- Timeout: 60 seconds
- Ephemeral storage: 512 MB (for temporary files)

### Optimization Tips

1. **Cache tenant branding**: Reduce DynamoDB calls
2. **Parallel batch processing**: Use Lambda concurrency
3. **Compress images**: Reduce PDF size
4. **Limit chart resolution**: Balance quality vs. size

## Monitoring

### CloudWatch Metrics

- `PDFGenerationDuration`: Time to generate PDF
- `PDFGenerationErrors`: Count of failed generations
- `PDFSizeBytes`: Size of generated PDFs
- `S3UploadDuration`: Time to upload to S3

### CloudWatch Alarms

- PDF generation error rate > 5%
- Average generation time > 30 seconds
- S3 upload failures

### Logs

All operations are logged with structured JSON:
```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "level": "INFO",
  "message": "PDF export completed successfully",
  "tenant_id": "tenant-123",
  "report_id": "report-456",
  "pdf_size_bytes": 524288,
  "duration_ms": 3245
}
```

## Security

### Tenant Isolation

- S3 keys include tenant ID prefix
- Pre-signed URLs are tenant-specific
- Lambda authorizer validates tenant access

### Encryption

- S3 server-side encryption (AES-256)
- TLS 1.2+ for all API calls
- Encrypted environment variables

### Access Control

- IAM roles with least privilege
- S3 bucket policies restrict access
- Pre-signed URLs expire after 24 hours (configurable)

## Troubleshooting

### WeasyPrint Installation Issues

**Problem:** `OSError: cannot load library 'gobject-2.0-0'`

**Solution:** Install system dependencies:
```bash
sudo apt-get install -y libgobject-2.0-0
```

### PDF Rendering Issues

**Problem:** Charts or images not appearing in PDF

**Solution:** Ensure images are base64-encoded or accessible via HTTPS

### S3 Access Denied

**Problem:** `AccessDenied` when storing PDF

**Solution:** Check Lambda execution role has `s3:PutObject` permission

### Large PDF Timeout

**Problem:** Lambda timeout for large reports

**Solution:** Increase Lambda timeout to 60+ seconds or split into smaller reports

## Future Enhancements

1. **PDF Compression**: Reduce file size with compression
2. **Watermarks**: Add custom watermarks for draft reports
3. **Digital Signatures**: Sign PDFs for authenticity
4. **PDF/A Compliance**: Generate archival-quality PDFs
5. **Custom Templates**: Support multiple report templates
6. **Async Generation**: Queue large PDF jobs for background processing
