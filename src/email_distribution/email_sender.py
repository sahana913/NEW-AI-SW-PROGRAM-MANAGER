"""
Email Sender Module

Handles sending emails via Amazon SES with PDF attachments and inline summaries.

Validates: Requirements 17.3, 17.4
"""

import os
import boto3
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError

from src.shared.logger import get_logger

logger = get_logger(__name__)


class EmailSender:
    """Handles email sending via Amazon SES."""
    
    def __init__(self, sender_email: str, region: str = None):
        """
        Initialize EmailSender.
        
        Args:
            sender_email: Sender email address (must be verified in SES)
            region: AWS region (defaults to environment variable or us-east-1)
        """
        self.sender_email = sender_email
        self.region = region or os.environ.get('AWS_REGION', 'us-east-1')
        self.ses_client = boto3.client('ses', region_name=self.region)
        self.s3_client = boto3.client('s3')
        
        logger.info(
            f"EmailSender initialized with sender: {sender_email}",
            extra={"sender_email": sender_email, "region": self.region}
        )
    
    def send_report_email(
        self,
        recipient: str,
        report_details: Dict[str, Any],
        tenant_id: str
    ) -> str:
        """
        Send report email with PDF attachment and inline summary.
        
        Validates: Requirement 17.4 - Include PDF attachment and inline summary
        
        Args:
            recipient: Recipient email address
            report_details: Report details including S3 key and metadata
            tenant_id: Tenant ID
            
        Returns:
            SES message ID
            
        Raises:
            ClientError: If SES send fails
        """
        report_id = report_details['report_id']
        report_type = report_details.get('report_type', 'Report')
        
        logger.info(
            f"Preparing email for {recipient}",
            extra={
                "recipient": recipient,
                "report_id": report_id,
                "report_type": report_type
            }
        )
        
        # Create MIME message
        msg = MIMEMultipart('mixed')
        msg['Subject'] = self._generate_subject(report_type, report_details)
        msg['From'] = self.sender_email
        msg['To'] = recipient
        
        # Create message body with inline summary (Requirement 17.4)
        body_part = MIMEMultipart('alternative')
        
        # Plain text version
        text_body = self._generate_text_body(report_details, tenant_id)
        body_part.attach(MIMEText(text_body, 'plain'))
        
        # HTML version
        html_body = self._generate_html_body(report_details, tenant_id)
        body_part.attach(MIMEText(html_body, 'html'))
        
        msg.attach(body_part)
        
        # Attach PDF from S3 (Requirement 17.4)
        if report_details.get('s3_key'):
            pdf_attachment = self._get_pdf_from_s3(
                s3_key=report_details['s3_key'],
                report_type=report_type
            )
            if pdf_attachment:
                msg.attach(pdf_attachment)
        
        # Send email via SES (Requirement 17.3)
        try:
            response = self.ses_client.send_raw_email(
                Source=self.sender_email,
                Destinations=[recipient],
                RawMessage={'Data': msg.as_string()}
            )
            
            message_id = response['MessageId']
            
            logger.info(
                f"Email sent successfully to {recipient}",
                extra={
                    "recipient": recipient,
                    "message_id": message_id,
                    "report_id": report_id
                }
            )
            
            return message_id
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            logger.error(
                f"SES send failed: {error_code} - {error_message}",
                extra={
                    "recipient": recipient,
                    "report_id": report_id,
                    "error_code": error_code
                }
            )
            
            raise
    
    def _generate_subject(
        self,
        report_type: str,
        report_details: Dict[str, Any]
    ) -> str:
        """Generate email subject line."""
        if report_type == 'WEEKLY_STATUS':
            return f"Weekly Status Report - {report_details.get('generated_at', '')}"
        elif report_type == 'EXECUTIVE_SUMMARY':
            return f"Executive Summary - {report_details.get('generated_at', '')}"
        else:
            return f"Program Report - {report_details.get('generated_at', '')}"
    
    def _generate_text_body(
        self,
        report_details: Dict[str, Any],
        tenant_id: str
    ) -> str:
        """
        Generate plain text email body with inline summary.
        
        Validates: Requirement 17.4 - Inline summary in email body
        """
        report_type = report_details.get('report_type', 'Report')
        generated_at = report_details.get('generated_at', 'N/A')
        
        body = f"""
AI SW Program Manager - {report_type}

Generated: {generated_at}

This is your automated program management report. Please find the detailed PDF report attached.

Report Summary:
- Report Type: {report_type}
- Generated: {generated_at}
- Projects Included: {len(report_details.get('project_ids', []))}

The attached PDF contains comprehensive details including:
- Project health scores and RAG status
- Risk alerts and recommendations
- Key metrics and trends
- Milestone progress
- Predictions and insights

---

To unsubscribe from these reports, please contact your administrator.

This is an automated message from AI SW Program Manager.
"""
        return body.strip()
    
    def _generate_html_body(
        self,
        report_details: Dict[str, Any],
        tenant_id: str
    ) -> str:
        """
        Generate HTML email body with inline summary.
        
        Validates: Requirement 17.4 - Inline summary in email body
        """
        report_type = report_details.get('report_type', 'Report')
        generated_at = report_details.get('generated_at', 'N/A')
        project_count = len(report_details.get('project_ids', []))
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
        }}
        .header {{
            background-color: #0066cc;
            color: white;
            padding: 20px;
            text-align: center;
        }}
        .content {{
            padding: 20px;
        }}
        .summary-box {{
            background-color: #f5f5f5;
            border-left: 4px solid #0066cc;
            padding: 15px;
            margin: 20px 0;
        }}
        .footer {{
            background-color: #f5f5f5;
            padding: 15px;
            text-align: center;
            font-size: 12px;
            color: #666;
        }}
        ul {{
            list-style-type: none;
            padding-left: 0;
        }}
        li {{
            padding: 5px 0;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>AI SW Program Manager</h1>
        <h2>{report_type}</h2>
    </div>
    
    <div class="content">
        <p>Generated: <strong>{generated_at}</strong></p>
        
        <p>This is your automated program management report. Please find the detailed PDF report attached.</p>
        
        <div class="summary-box">
            <h3>Report Summary</h3>
            <ul>
                <li><strong>Report Type:</strong> {report_type}</li>
                <li><strong>Generated:</strong> {generated_at}</li>
                <li><strong>Projects Included:</strong> {project_count}</li>
            </ul>
        </div>
        
        <h3>What's Included</h3>
        <p>The attached PDF contains comprehensive details including:</p>
        <ul>
            <li>✓ Project health scores and RAG status</li>
            <li>✓ Risk alerts and recommendations</li>
            <li>✓ Key metrics and trends</li>
            <li>✓ Milestone progress</li>
            <li>✓ Predictions and insights</li>
        </ul>
    </div>
    
    <div class="footer">
        <p>To unsubscribe from these reports, please contact your administrator.</p>
        <p>This is an automated message from AI SW Program Manager.</p>
    </div>
</body>
</html>
"""
        return html.strip()
    
    def _get_pdf_from_s3(
        self,
        s3_key: str,
        report_type: str
    ) -> Optional[MIMEApplication]:
        """
        Retrieve PDF from S3 and create MIME attachment.
        
        Args:
            s3_key: S3 object key
            report_type: Report type for filename
            
        Returns:
            MIME attachment or None if retrieval fails
        """
        try:
            # Parse S3 key to get bucket and key
            # Expected format: s3://bucket-name/path/to/file or just path/to/file
            if s3_key.startswith('s3://'):
                parts = s3_key.replace('s3://', '').split('/', 1)
                bucket = parts[0]
                key = parts[1] if len(parts) > 1 else ''
            else:
                # Use default bucket from environment
                bucket = os.environ.get('REPORTS_BUCKET', 'ai-sw-pm-reports')
                key = s3_key
            
            logger.info(
                f"Retrieving PDF from S3: {bucket}/{key}",
                extra={"bucket": bucket, "key": key}
            )
            
            # Download PDF from S3
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            pdf_data = response['Body'].read()
            
            # Create MIME attachment
            attachment = MIMEApplication(pdf_data, _subtype='pdf')
            attachment.add_header(
                'Content-Disposition',
                'attachment',
                filename=f"{report_type.replace('_', '-').lower()}.pdf"
            )
            
            logger.info(
                f"PDF attachment created successfully",
                extra={"size_bytes": len(pdf_data)}
            )
            
            return attachment
            
        except Exception as e:
            logger.error(
                f"Failed to retrieve PDF from S3: {str(e)}",
                extra={"s3_key": s3_key, "error": str(e)}
            )
            return None
