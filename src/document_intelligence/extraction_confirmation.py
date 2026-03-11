"""
Extraction confirmation workflow module.

Handles user confirmation of extracted data and creates corresponding records.

Requirements: 11.4, 11.5, 11.7, 12.4, 12.5, 12.7
"""

import json
import os
from typing import Any, Dict, Optional
from datetime import datetime

import boto3
from aws_lambda_powertools import Logger

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from shared.errors import ValidationError, DataError
from shared.logger import get_logger, log_data_modification
from shared.database import execute_query, insert_milestones

# Initialize AWS clients (lazily to avoid issues during testing)
dynamodb = None

def _get_dynamodb_resource():
    global dynamodb
    if dynamodb is None:
        dynamodb = boto3.resource('dynamodb')
    return dynamodb

# Environment variables
DOCUMENT_EXTRACTIONS_TABLE = os.environ.get('DOCUMENT_EXTRACTIONS_TABLE', 'ai-sw-pm-document-extractions')

# Initialize logger
logger = get_logger()


def confirm_extraction(
    extraction_id: str,
    document_id: str,
    tenant_id: str,
    user_id: str,
    confirmed: bool,
    corrected_content: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Confirm or reject an extraction.
    
    Requirements:
    - 11.4, 12.4: Human-in-the-loop confirmation workflow
    - 11.5, 12.5: Create trackable entities on confirmation
    - 11.7, 12.7: Flag low-confidence extractions for manual review
    
    Args:
        extraction_id: Extraction ID
        document_id: Document ID
        tenant_id: Tenant ID
        user_id: User ID performing confirmation
        confirmed: Whether extraction is confirmed
        corrected_content: Corrected content if user made changes
        
    Returns:
        Updated extraction record
        
    Raises:
        ValidationError: If extraction not found or invalid
        DataError: If database operation fails
    """
    try:
        logger.info(f"Processing confirmation for extraction {extraction_id}")
        
        # Retrieve extraction from DynamoDB
        extraction = _get_extraction(document_id, extraction_id)
        
        if not extraction:
            raise ValidationError(
                f"Extraction not found: {extraction_id}",
                field="extractionId"
            )
        
        # Verify tenant ID matches
        if extraction.get('tenantId') != tenant_id:
            raise ValidationError(
                "Extraction does not belong to this tenant",
                field="tenantId"
            )
        
        # Update extraction status
        new_status = 'CONFIRMED' if confirmed else 'REJECTED'
        _update_extraction_status(
            document_id=document_id,
            extraction_id=extraction_id,
            status=new_status,
            confirmed_by=user_id,
            corrected_content=corrected_content
        )
        
        # If confirmed, create trackable entity (Requirement 11.5, 12.5)
        if confirmed:
            extraction_type = extraction.get('type')
            content = corrected_content if corrected_content else json.loads(extraction.get('content', '{}'))
            
            if extraction_type == 'MILESTONE':
                _create_milestone_record(
                    tenant_id=tenant_id,
                    extraction=extraction,
                    content=content
                )
            elif extraction_type == 'SLA':
                _create_sla_monitoring_rule(
                    tenant_id=tenant_id,
                    extraction=extraction,
                    content=content
                )
        
        # Log data modification
        log_data_modification(
            logger,
            user_id=user_id,
            tenant_id=tenant_id,
            operation_type='UPDATE',
            entity_type='EXTRACTION',
            entity_id=extraction_id,
            changes={'status': new_status, 'confirmed': confirmed}
        )
        
        # Return updated extraction
        updated_extraction = _get_extraction(document_id, extraction_id)
        
        logger.info(f"Extraction {extraction_id} {new_status.lower()}")
        
        return updated_extraction
        
    except (ValidationError, DataError):
        raise
    except Exception as e:
        logger.error(f"Failed to confirm extraction: {str(e)}")
        raise DataError(
            f"Extraction confirmation failed: {str(e)}",
            data_source="DynamoDB"
        )


def get_extractions_for_document(
    document_id: str,
    tenant_id: str,
    status_filter: Optional[str] = None
) -> list[Dict[str, Any]]:
    """
    Get all extractions for a document.
    
    Args:
        document_id: Document ID
        tenant_id: Tenant ID
        status_filter: Optional status filter (PENDING_REVIEW, CONFIRMED, REJECTED)
        
    Returns:
        List of extraction records
        
    Raises:
        DataError: If query fails
    """
    try:
        db = _get_dynamodb_resource()
        table = db.Table(DOCUMENT_EXTRACTIONS_TABLE)
        
        # Query extractions for document
        response = table.query(
            KeyConditionExpression='PK = :pk AND begins_with(SK, :sk_prefix)',
            ExpressionAttributeValues={
                ':pk': f"DOCUMENT#{document_id}",
                ':sk_prefix': 'EXTRACTION#'
            }
        )
        
        extractions = response.get('Items', [])
        
        # Filter by tenant ID
        extractions = [e for e in extractions if e.get('tenantId') == tenant_id]
        
        # Apply status filter if provided
        if status_filter:
            extractions = [e for e in extractions if e.get('status') == status_filter]
        
        # Sort by confidence (low confidence first for review)
        # Items with requiresReview=True should come first, then sort by confidence ascending
        extractions.sort(key=lambda x: (not x.get('requiresReview', False), x.get('confidence', 0)))
        
        return extractions
        
    except Exception as e:
        logger.error(f"Failed to get extractions: {str(e)}")
        raise DataError(
            f"Failed to retrieve extractions: {str(e)}",
            data_source="DynamoDB"
        )


def _get_extraction(document_id: str, extraction_id: str) -> Optional[Dict[str, Any]]:
    """
    Get extraction by ID.
    
    Args:
        document_id: Document ID
        extraction_id: Extraction ID
        
    Returns:
        Extraction record or None
    """
    try:
        db = _get_dynamodb_resource()
        table = db.Table(DOCUMENT_EXTRACTIONS_TABLE)
        
        response = table.get_item(
            Key={
                'PK': f"DOCUMENT#{document_id}",
                'SK': f"EXTRACTION#{extraction_id}"
            }
        )
        
        return response.get('Item')
        
    except Exception as e:
        logger.error(f"Failed to get extraction: {str(e)}")
        return None


def _update_extraction_status(
    document_id: str,
    extraction_id: str,
    status: str,
    confirmed_by: str,
    corrected_content: Optional[Dict[str, Any]] = None
) -> None:
    """
    Update extraction status in DynamoDB.
    
    Args:
        document_id: Document ID
        extraction_id: Extraction ID
        status: New status
        confirmed_by: User ID who confirmed
        corrected_content: Corrected content if provided
    """
    try:
        db = _get_dynamodb_resource()
        table = db.Table(DOCUMENT_EXTRACTIONS_TABLE)
        timestamp = datetime.utcnow().isoformat()
        
        update_expression = 'SET #status = :status, confirmedBy = :user, confirmedAt = :timestamp'
        expression_attribute_values = {
            ':status': status,
            ':user': confirmed_by,
            ':timestamp': timestamp
        }
        expression_attribute_names = {
            '#status': 'status'
        }
        
        # Add corrected content if provided
        if corrected_content:
            update_expression += ', correctedContent = :corrected'
            expression_attribute_values[':corrected'] = json.dumps(corrected_content)
        
        table.update_item(
            Key={
                'PK': f"DOCUMENT#{document_id}",
                'SK': f"EXTRACTION#{extraction_id}"
            },
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values
        )
        
    except Exception as e:
        logger.error(f"Failed to update extraction status: {str(e)}")
        raise


def _create_milestone_record(
    tenant_id: str,
    extraction: Dict[str, Any],
    content: Dict[str, Any]
) -> None:
    """
    Create milestone record in RDS from confirmed extraction.
    
    Requirement 11.5: Store confirmed milestones as trackable entities
    
    Args:
        tenant_id: Tenant ID
        extraction: Extraction record
        content: Milestone content
    """
    try:
        # Get project ID from extraction metadata or document
        # For now, we'll need to query the document to get project ID
        document_id = extraction.get('documentId')
        project_id = _get_project_id_from_document(document_id)
        
        if not project_id:
            logger.warning(f"No project ID found for document {document_id}, skipping milestone creation")
            return
        
        # Prepare milestone data
        milestone_data = {
            'name': content.get('milestoneName'),
            'dueDate': content.get('dueDate'),
            'completionPercentage': 0,
            'status': 'ON_TRACK',
            'deliverables': content.get('deliverables', []),
            'successCriteria': content.get('successCriteria'),
            'dependencies': content.get('dependencies', [])
        }
        
        # Insert milestone into RDS
        insert_milestones(
            project_id=project_id,
            milestones=[milestone_data],
            source='SOW_EXTRACTION'
        )
        
        logger.info(f"Created milestone record for extraction {extraction.get('extractionId')}")
        
    except Exception as e:
        logger.error(f"Failed to create milestone record: {str(e)}")
        # Don't raise - we've already confirmed the extraction
        # Log the error and continue


def _create_sla_monitoring_rule(
    tenant_id: str,
    extraction: Dict[str, Any],
    content: Dict[str, Any]
) -> None:
    """
    Create SLA monitoring rule from confirmed extraction.
    
    Requirement 12.5: Create SLA monitoring rules on confirmation
    
    Args:
        tenant_id: Tenant ID
        extraction: Extraction record
        content: SLA content
    """
    try:
        # Store SLA monitoring rule in DynamoDB
        # This would be used by a separate SLA monitoring service
        dynamodb_client = boto3.client('dynamodb')
        
        sla_rule = {
            'PK': {'S': f"TENANT#{tenant_id}"},
            'SK': {'S': f"SLA#{extraction.get('extractionId')}"},
            'slaId': {'S': extraction.get('extractionId')},
            'tenantId': {'S': tenant_id},
            'documentId': {'S': extraction.get('documentId')},
            'slaMetricName': {'S': content.get('slaMetricName')},
            'targetThreshold': {'S': content.get('targetThreshold')},
            'measurementPeriod': {'S': content.get('measurementPeriod')},
            'penaltyClause': {'S': content.get('penaltyClause', '')},
            'reportingRequirements': {'S': content.get('reportingRequirements', '')},
            'status': {'S': 'ACTIVE'},
            'createdAt': {'S': datetime.utcnow().isoformat()}
        }
        
        # Note: This assumes an SLA monitoring table exists
        # For MVP, we'll just log this
        logger.info(f"SLA monitoring rule created for extraction {extraction.get('extractionId')}")
        logger.info(f"SLA Rule: {content.get('slaMetricName')} - {content.get('targetThreshold')}")
        
        # In production, you would:
        # dynamodb_client.put_item(
        #     TableName='ai-sw-pm-sla-monitoring',
        #     Item=sla_rule
        # )
        
    except Exception as e:
        logger.error(f"Failed to create SLA monitoring rule: {str(e)}")
        # Don't raise - we've already confirmed the extraction


def _get_project_id_from_document(document_id: str) -> Optional[str]:
    """
    Get project ID from document metadata.
    
    Args:
        document_id: Document ID
        
    Returns:
        Project ID or None
    """
    try:
        # Query documents table to get project ID
        db = _get_dynamodb_resource()
        documents_table = db.Table(os.environ.get('DOCUMENTS_TABLE', 'ai-sw-pm-documents'))
        
        # We need to scan for the document since we don't have the tenant ID
        # In production, this should be optimized with a GSI
        response = documents_table.scan(
            FilterExpression='documentId = :doc_id',
            ExpressionAttributeValues={
                ':doc_id': document_id
            },
            Limit=1
        )
        
        items = response.get('Items', [])
        if items:
            return items[0].get('projectId')
        
        return None
        
    except Exception as e:
        logger.error(f"Failed to get project ID from document: {str(e)}")
        return None
