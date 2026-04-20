"""Tenant configuration retrieval for branding."""

from shared.logger import get_logger
from shared.errors import DataError
from botocore.exceptions import ClientError
import boto3
import os
import sys
from typing import Any, Dict, Optional

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


logger = get_logger()

# AWS clients (initialized lazily)
_dynamodb = None

# Environment variables
TENANTS_TABLE = os.environ.get("TENANTS_TABLE", "ai-sw-pm-tenants")


def get_dynamodb():
    """Get or create DynamoDB resource."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb


def get_tenant_branding_config(tenant_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve tenant branding configuration from DynamoDB.

    Args:
        tenant_id: Tenant ID

    Returns:
        Tenant branding configuration or None if not found
        {
            'logo_url': 'https://...',
            'primary_color': '#667eea',
            'secondary_color': '#764ba2',
            'company_name': 'Acme Corp'
        }
    """
    try:
        dynamodb = get_dynamodb()
        tenants_table = dynamodb.Table(TENANTS_TABLE)

        logger.info(
            "Retrieving tenant branding configuration", extra={"tenant_id": tenant_id}
        )

        # Query tenant configuration
        response = tenants_table.get_item(
            Key={"PK": f"TENANT#{tenant_id}", "SK": "CONFIG"}
        )

        item = response.get("Item")

        if not item:
            logger.info(
                "No tenant branding configuration found, using defaults",
                extra={"tenant_id": tenant_id},
            )
            return None

        # Extract branding settings
        branding = item.get("branding", {})

        config = {
            "logo_url": branding.get("logo_url", ""),
            "primary_color": branding.get("primary_color", "#667eea"),
            "secondary_color": branding.get("secondary_color", "#764ba2"),
            "company_name": branding.get("company_name", ""),
        }

        logger.info(
            "Tenant branding configuration retrieved",
            extra={
                "tenant_id": tenant_id,
                "has_logo": bool(config["logo_url"]),
                "has_company_name": bool(config["company_name"]),
            },
        )

        return config

    except ClientError as e:
        logger.error(
            "Failed to retrieve tenant branding configuration",
            extra={"tenant_id": tenant_id, "error": str(e)},
        )
        # Return None to use defaults
        return None
    except Exception as e:
        logger.error(
            "Unexpected error retrieving tenant branding",
            extra={"tenant_id": tenant_id, "error": str(e)},
        )
        return None


def update_tenant_branding_config(
    tenant_id: str,
    logo_url: Optional[str] = None,
    primary_color: Optional[str] = None,
    secondary_color: Optional[str] = None,
    company_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Update tenant branding configuration.

    Args:
        tenant_id: Tenant ID
        logo_url: Optional logo URL
        primary_color: Optional primary color hex code
        secondary_color: Optional secondary color hex code
        company_name: Optional company name

    Returns:
        Updated branding configuration

    Raises:
        DataError: If update fails
    """
    try:
        dynamodb = get_dynamodb()
        tenants_table = dynamodb.Table(TENANTS_TABLE)

        logger.info(
            "Updating tenant branding configuration", extra={"tenant_id": tenant_id}
        )

        # Build update expression
        update_parts = []
        expression_values = {}

        if logo_url is not None:
            update_parts.append("branding.logo_url = :logo_url")
            expression_values[":logo_url"] = logo_url

        if primary_color is not None:
            update_parts.append("branding.primary_color = :primary_color")
            expression_values[":primary_color"] = primary_color

        if secondary_color is not None:
            update_parts.append("branding.secondary_color = :secondary_color")
            expression_values[":secondary_color"] = secondary_color

        if company_name is not None:
            update_parts.append("branding.company_name = :company_name")
            expression_values[":company_name"] = company_name

        if not update_parts:
            logger.warning("No branding fields to update")
            return get_tenant_branding_config(tenant_id) or {}

        update_expression = "SET " + ", ".join(update_parts)

        # Update tenant configuration
        response = tenants_table.update_item(
            Key={"PK": f"TENANT#{tenant_id}", "SK": "CONFIG"},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values,
            ReturnValues="ALL_NEW",
        )

        updated_item = response.get("Attributes", {})
        branding = updated_item.get("branding", {})

        logger.info(
            "Tenant branding configuration updated successfully",
            extra={"tenant_id": tenant_id},
        )

        return {
            "logo_url": branding.get("logo_url", ""),
            "primary_color": branding.get("primary_color", "#667eea"),
            "secondary_color": branding.get("secondary_color", "#764ba2"),
            "company_name": branding.get("company_name", ""),
        }

    except ClientError as e:
        logger.error(
            "Failed to update tenant branding configuration",
            extra={"tenant_id": tenant_id, "error": str(e)},
        )
        raise DataError(
            f"Failed to update tenant branding: {str(e)}", data_source="DynamoDB"
        )
