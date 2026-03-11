"""
Delivery Logger Module

Logs all email delivery attempts to DynamoDB.

Validates: Requirement 17.7
"""

import uuid
from datetime import datetime
from typing import Optional
import boto3

from src.shared.logger import get_logger

logger = get_logger(__name__)


class DeliveryLogger:
    """Logs email delivery attempts to DynamoDB."""
    
    def __init__(self, table_name: str):
        """
        Initialize DeliveryLogger.
        
        Args:
            table_name: DynamoDB table name for email delivery logs
        """
        self.table_name = table_name
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(table_name)
        
        logger.info(
            f"DeliveryLogger initialized with table: {table_name}",
            extra={"table_name": table_name}
        )
    
    def log_attempt(
        self,
        report_id: str,
        recipient: str,
        tenant_id: str,
        attempt: int,
        success: bool,
        error: Optional[str] = None,
        message_id: Optional[str] = None
    ) -> str:
        """
        Log an email delivery attempt.
        
        Validates: Requirement 17.7 - Log all delivery attempts with success/failure status
        
        Args:
            report_id: Report ID
            recipient: Recipient email address
            tenant_id: Tenant ID
            attempt: Attempt number
            success: Whether the attempt was successful
            error: Error message if failed
            message_id: SES message ID if successful
            
        Returns:
            Log entry ID
        """
        log_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        item = {
            'PK': f"TENANT#{tenant_id}",
            'SK': f"LOG#{log_id}",
            'logId': log_id,
            'reportId': report_id,
            'recipient': recipient,
            'tenantId': tenant_id,
            'attempt': attempt,
            'success': success,
            'timestamp': timestamp,
            'status': 'SUCCESS' if success else 'FAILED',
            # GSI for recipient queries
            'GSI1PK': f"RECIPIENT#{recipient}",
            'GSI1SK': f"LOG#{timestamp}"
        }
        
        if message_id:
            item['messageId'] = message_id
        
        if error:
            item['error'] = error
        
        try:
            self.table.put_item(Item=item)
            
            logger.info(
                f"Logged delivery attempt for {recipient}",
                extra={
                    "log_id": log_id,
                    "report_id": report_id,
                    "recipient": recipient,
                    "attempt": attempt,
                    "success": success
                }
            )
            
            return log_id
            
        except Exception as e:
            logger.error(
                f"Failed to log delivery attempt: {str(e)}",
                extra={
                    "report_id": report_id,
                    "recipient": recipient,
                    "error": str(e)
                }
            )
            # Don't raise - logging failure shouldn't stop email delivery
            return log_id
    
    def log_success(
        self,
        report_id: str,
        recipient: str,
        tenant_id: str,
        message_id: str,
        attempt: int
    ) -> str:
        """
        Log a successful email delivery.
        
        Args:
            report_id: Report ID
            recipient: Recipient email address
            tenant_id: Tenant ID
            message_id: SES message ID
            attempt: Attempt number
            
        Returns:
            Log entry ID
        """
        return self.log_attempt(
            report_id=report_id,
            recipient=recipient,
            tenant_id=tenant_id,
            attempt=attempt,
            success=True,
            message_id=message_id
        )
    
    def log_failure(
        self,
        report_id: str,
        recipient: str,
        tenant_id: str,
        attempts: int,
        error: str
    ) -> str:
        """
        Log a final email delivery failure after all retries.
        
        Args:
            report_id: Report ID
            recipient: Recipient email address
            tenant_id: Tenant ID
            attempts: Total number of attempts made
            error: Error message
            
        Returns:
            Log entry ID
        """
        return self.log_attempt(
            report_id=report_id,
            recipient=recipient,
            tenant_id=tenant_id,
            attempt=attempts,
            success=False,
            error=error
        )
    
    def log_skipped(
        self,
        report_id: str,
        recipient: str,
        tenant_id: str,
        reason: str
    ) -> str:
        """
        Log a skipped email delivery (e.g., due to unsubscribe).
        
        Args:
            report_id: Report ID
            recipient: Recipient email address
            tenant_id: Tenant ID
            reason: Reason for skipping
            
        Returns:
            Log entry ID
        """
        log_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        item = {
            'PK': f"TENANT#{tenant_id}",
            'SK': f"LOG#{log_id}",
            'logId': log_id,
            'reportId': report_id,
            'recipient': recipient,
            'tenantId': tenant_id,
            'attempt': 0,
            'success': False,
            'timestamp': timestamp,
            'status': 'SKIPPED',
            'reason': reason,
            # GSI for recipient queries
            'GSI1PK': f"RECIPIENT#{recipient}",
            'GSI1SK': f"LOG#{timestamp}"
        }
        
        try:
            self.table.put_item(Item=item)
            
            logger.info(
                f"Logged skipped delivery for {recipient}",
                extra={
                    "log_id": log_id,
                    "report_id": report_id,
                    "recipient": recipient,
                    "reason": reason
                }
            )
            
            return log_id
            
        except Exception as e:
            logger.error(
                f"Failed to log skipped delivery: {str(e)}",
                extra={
                    "report_id": report_id,
                    "recipient": recipient,
                    "error": str(e)
                }
            )
            return log_id
