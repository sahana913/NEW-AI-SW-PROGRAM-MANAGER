"""
Preferences Checker Module

Checks user email preferences and unsubscribe status.

Validates: Requirement 17.8
"""

import boto3
from typing import Optional
from botocore.exceptions import ClientError

from src.shared.logger import get_logger

logger = get_logger(__name__)


class PreferencesChecker:
    """Checks user email preferences and unsubscribe status."""
    
    def __init__(self, table_name: str):
        """
        Initialize PreferencesChecker.
        
        Args:
            table_name: DynamoDB table name for email preferences
        """
        self.table_name = table_name
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(table_name)
        
        logger.info(
            f"PreferencesChecker initialized with table: {table_name}",
            extra={"table_name": table_name}
        )
    
    def can_send_email(self, recipient: str, tenant_id: str) -> bool:
        """
        Check if email can be sent to recipient.
        
        Validates: Requirement 17.8 - Respect unsubscribe preferences
        
        Args:
            recipient: Recipient email address
            tenant_id: Tenant ID
            
        Returns:
            True if email can be sent, False if user has unsubscribed
        """
        try:
            response = self.table.get_item(
                Key={
                    'PK': f"TENANT#{tenant_id}",
                    'SK': f"EMAIL#{recipient}"
                }
            )
            
            if 'Item' not in response:
                # No preference record means user has not unsubscribed
                logger.debug(
                    f"No preference record for {recipient}, allowing email",
                    extra={"recipient": recipient, "tenant_id": tenant_id}
                )
                return True
            
            item = response['Item']
            unsubscribed = item.get('unsubscribed', False)
            
            if unsubscribed:
                logger.info(
                    f"User {recipient} has unsubscribed, blocking email",
                    extra={
                        "recipient": recipient,
                        "tenant_id": tenant_id,
                        "unsubscribed_at": item.get('unsubscribedAt')
                    }
                )
                return False
            
            logger.debug(
                f"User {recipient} has not unsubscribed, allowing email",
                extra={"recipient": recipient, "tenant_id": tenant_id}
            )
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            
            if error_code == 'ResourceNotFoundException':
                # Table doesn't exist yet - allow email
                logger.warning(
                    f"Email preferences table not found, allowing email",
                    extra={"table_name": self.table_name}
                )
                return True
            
            logger.error(
                f"Error checking email preferences: {str(e)}",
                extra={
                    "recipient": recipient,
                    "tenant_id": tenant_id,
                    "error_code": error_code
                }
            )
            # On error, default to allowing email (fail open)
            return True
        
        except Exception as e:
            logger.error(
                f"Unexpected error checking email preferences: {str(e)}",
                extra={
                    "recipient": recipient,
                    "tenant_id": tenant_id,
                    "error": str(e)
                }
            )
            # On error, default to allowing email (fail open)
            return True
    
    def set_unsubscribe(
        self,
        recipient: str,
        tenant_id: str,
        unsubscribed: bool = True
    ) -> bool:
        """
        Set unsubscribe preference for a recipient.
        
        Args:
            recipient: Recipient email address
            tenant_id: Tenant ID
            unsubscribed: Whether user is unsubscribed (default: True)
            
        Returns:
            True if preference was set successfully
        """
        from datetime import datetime
        
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        item = {
            'PK': f"TENANT#{tenant_id}",
            'SK': f"EMAIL#{recipient}",
            'email': recipient,
            'tenantId': tenant_id,
            'unsubscribed': unsubscribed,
            'updatedAt': timestamp
        }
        
        if unsubscribed:
            item['unsubscribedAt'] = timestamp
        
        try:
            self.table.put_item(Item=item)
            
            logger.info(
                f"Set unsubscribe preference for {recipient}: {unsubscribed}",
                extra={
                    "recipient": recipient,
                    "tenant_id": tenant_id,
                    "unsubscribed": unsubscribed
                }
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to set unsubscribe preference: {str(e)}",
                extra={
                    "recipient": recipient,
                    "tenant_id": tenant_id,
                    "error": str(e)
                }
            )
            return False
    
    def get_preference(
        self,
        recipient: str,
        tenant_id: str
    ) -> Optional[dict]:
        """
        Get email preference for a recipient.
        
        Args:
            recipient: Recipient email address
            tenant_id: Tenant ID
            
        Returns:
            Preference dictionary or None if not found
        """
        try:
            response = self.table.get_item(
                Key={
                    'PK': f"TENANT#{tenant_id}",
                    'SK': f"EMAIL#{recipient}"
                }
            )
            
            if 'Item' in response:
                return response['Item']
            
            return None
            
        except Exception as e:
            logger.error(
                f"Failed to get email preference: {str(e)}",
                extra={
                    "recipient": recipient,
                    "tenant_id": tenant_id,
                    "error": str(e)
                }
            )
            return None
