"""
SOW milestone extraction module.

Extracts milestone information from Statement of Work documents using Amazon Bedrock.

Requirements: 11.1, 11.2, 11.4
"""

import json
import os
from typing import Any, Dict, List, Optional
from datetime import datetime

import boto3
from aws_lambda_powertools import Logger

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from shared.errors import ProcessingError
from shared.logger import get_logger
from shared.constants import LOW_CONFIDENCE_THRESHOLD

# Initialize AWS clients (lazily to avoid issues during testing)
bedrock_runtime = None
s3_client = None
dynamodb = None

def _get_bedrock_client():
    global bedrock_runtime
    if bedrock_runtime is None:
        bedrock_runtime = boto3.client('bedrock-runtime', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
    return bedrock_runtime

def _get_s3_client():
    global s3_client
    if s3_client is None:
        s3_client = boto3.client('s3')
    return s3_client

def _get_dynamodb_resource():
    global dynamodb
    if dynamodb is None:
        dynamodb = boto3.resource('dynamodb')
    return dynamodb

# Environment variables
DOCUMENT_EXTRACTIONS_TABLE = os.environ.get('DOCUMENT_EXTRACTIONS_TABLE', 'ai-sw-pm-document-extractions')
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'anthropic.claude-3-sonnet-20240229-v1:0')

# Initialize logger
logger = get_logger()


def extract_milestones_from_sow(
    document_id: str,
    tenant_id: str,
    extracted_text: str
) -> List[Dict[str, Any]]:
    """
    Extract milestones from SOW document using Amazon Bedrock.
    
    Requirements:
    - 11.1: Extract milestone definitions using Document_Intelligence
    - 11.2: Identify milestone names, due dates, and deliverables
    
    Args:
        document_id: Document ID
        tenant_id: Tenant ID
        extracted_text: Extracted text from document
        
    Returns:
        List of extracted milestone dictionaries
        
    Raises:
        ProcessingError: If extraction fails
    """
    try:
        logger.info(f"Extracting milestones from SOW document: {document_id}")
        
        # Construct prompt for Bedrock Claude (Requirement 11.2)
        prompt = _construct_sow_extraction_prompt(extracted_text)
        
        # Call Bedrock API
        response = _call_bedrock_claude(prompt)
        
        # Parse response
        milestones = _parse_milestone_extraction_response(response)
        
        # Store extractions in DynamoDB (Requirement 11.4)
        extraction_ids = _store_milestone_extractions(
            document_id=document_id,
            tenant_id=tenant_id,
            milestones=milestones
        )
        
        logger.info(f"Extracted {len(milestones)} milestones from document {document_id}")
        
        return milestones
        
    except Exception as e:
        logger.error(f"Failed to extract milestones: {str(e)}")
        raise ProcessingError(
            f"Milestone extraction failed: {str(e)}",
            processing_type='sow_extraction'
        )


def _construct_sow_extraction_prompt(extracted_text: str) -> str:
    """
    Construct prompt for SOW milestone extraction.
    
    Args:
        extracted_text: Text extracted from SOW document
        
    Returns:
        Formatted prompt string
    """
    prompt = f"""Extract all milestones from this Statement of Work document.

For each milestone, identify:
- Milestone name (required)
- Due date (required, in ISO 8601 format YYYY-MM-DD if possible)
- Deliverables (list of deliverable items)
- Success criteria (if mentioned)
- Dependencies (if mentioned)

Return the results as a JSON array with the following structure:
[
  {{
    "milestoneName": "string",
    "dueDate": "YYYY-MM-DD or descriptive text if exact date not available",
    "deliverables": ["deliverable1", "deliverable2"],
    "successCriteria": "string or null",
    "dependencies": ["dependency1"] or null,
    "confidence": 0.0-1.0 (your confidence in this extraction)
  }}
]

If no milestones are found, return an empty array [].

Document text:
{extracted_text[:10000]}

Return only the JSON array, no additional text or explanation."""

    return prompt


def _call_bedrock_claude(prompt: str) -> str:
    """
    Call Amazon Bedrock Claude model for text generation.
    
    Args:
        prompt: Prompt text
        
    Returns:
        Model response text
        
    Raises:
        ProcessingError: If API call fails
    """
    try:
        bedrock = _get_bedrock_client()
        
        # Construct request body for Claude
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1,  # Low temperature for more deterministic extraction
            "top_p": 0.9
        }
        
        # Call Bedrock API
        response = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps(request_body),
            contentType='application/json',
            accept='application/json'
        )
        
        # Parse response
        response_body = json.loads(response['body'].read())
        
        # Extract text from Claude response
        if 'content' in response_body and len(response_body['content']) > 0:
            return response_body['content'][0]['text']
        
        raise ProcessingError(
            "Invalid response format from Bedrock",
            processing_type='bedrock_api'
        )
        
    except Exception as e:
        logger.error(f"Bedrock API call failed: {str(e)}")
        raise ProcessingError(
            f"Failed to call Bedrock API: {str(e)}",
            processing_type='bedrock_api'
        )


def _parse_milestone_extraction_response(response_text: str) -> List[Dict[str, Any]]:
    """
    Parse milestone extraction response from Bedrock.
    
    Args:
        response_text: Response text from Bedrock
        
    Returns:
        List of milestone dictionaries
        
    Raises:
        ProcessingError: If parsing fails
    """
    try:
        # Extract JSON from response (handle cases where model adds explanation)
        response_text = response_text.strip()
        
        # Find JSON array in response
        start_idx = response_text.find('[')
        end_idx = response_text.rfind(']') + 1
        
        if start_idx == -1 or end_idx == 0:
            logger.warning("No JSON array found in response")
            return []
        
        json_text = response_text[start_idx:end_idx]
        milestones = json.loads(json_text)
        
        # Validate and normalize milestone data
        normalized_milestones = []
        for milestone in milestones:
            if not isinstance(milestone, dict):
                continue
            
            # Ensure required fields
            if 'milestoneName' not in milestone or 'dueDate' not in milestone:
                logger.warning(f"Skipping milestone with missing required fields: {milestone}")
                continue
            
            # Normalize confidence score
            confidence = float(milestone.get('confidence', 0.5))
            confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
            
            normalized_milestone = {
                'milestoneName': milestone['milestoneName'],
                'dueDate': milestone['dueDate'],
                'deliverables': milestone.get('deliverables', []),
                'successCriteria': milestone.get('successCriteria'),
                'dependencies': milestone.get('dependencies'),
                'confidence': confidence
            }
            
            normalized_milestones.append(normalized_milestone)
        
        return normalized_milestones
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {str(e)}")
        logger.error(f"Response text: {response_text[:500]}")
        raise ProcessingError(
            f"Failed to parse milestone extraction response: {str(e)}",
            processing_type='response_parsing'
        )
    except Exception as e:
        logger.error(f"Failed to process extraction response: {str(e)}")
        raise ProcessingError(
            f"Failed to process extraction response: {str(e)}",
            processing_type='response_parsing'
        )


def _store_milestone_extractions(
    document_id: str,
    tenant_id: str,
    milestones: List[Dict[str, Any]]
) -> List[str]:
    """
    Store milestone extractions in DynamoDB for user confirmation.
    
    Requirement 11.4: Present extractions to user for confirmation
    
    Args:
        document_id: Document ID
        tenant_id: Tenant ID
        milestones: List of extracted milestones
        
    Returns:
        List of extraction IDs
        
    Raises:
        ProcessingError: If storage fails
    """
    try:
        db = _get_dynamodb_resource()
        table = db.Table(DOCUMENT_EXTRACTIONS_TABLE)
        extraction_ids = []
        timestamp = datetime.utcnow().isoformat()
        
        for milestone in milestones:
            # Generate extraction ID
            import uuid
            extraction_id = str(uuid.uuid4())
            
            # Determine if requires review based on confidence (Requirement 11.7)
            requires_review = milestone['confidence'] < LOW_CONFIDENCE_THRESHOLD
            
            # Store extraction
            extraction_item = {
                'PK': f"DOCUMENT#{document_id}",
                'SK': f"EXTRACTION#{extraction_id}",
                'extractionId': extraction_id,
                'documentId': document_id,
                'tenantId': tenant_id,
                'type': 'MILESTONE',
                'content': json.dumps(milestone),
                'confidence': milestone['confidence'],
                'metadata': {
                    'milestoneName': milestone['milestoneName'],
                    'dueDate': milestone['dueDate'],
                    'deliverables': milestone.get('deliverables', [])
                },
                'requiresReview': requires_review,
                'status': 'PENDING_REVIEW',
                'createdAt': timestamp
            }
            
            table.put_item(Item=extraction_item)
            extraction_ids.append(extraction_id)
            
            logger.info(
                f"Stored milestone extraction {extraction_id} "
                f"(confidence: {milestone['confidence']:.2f}, requires_review: {requires_review})"
            )
        
        return extraction_ids
        
    except Exception as e:
        logger.error(f"Failed to store milestone extractions: {str(e)}")
        raise ProcessingError(
            f"Failed to store extractions: {str(e)}",
            processing_type='data_storage'
        )
