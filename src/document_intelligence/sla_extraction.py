"""
SLA clause extraction module.

Extracts SLA clauses from contract documents using Amazon Bedrock.

Requirements: 12.1, 12.2, 12.4
"""

from shared.logger import get_logger
from shared.errors import ProcessingError
from shared.constants import LOW_CONFIDENCE_THRESHOLD
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

import boto3

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))


# Initialize AWS clients (lazily to avoid issues during testing)
bedrock_runtime = None
s3_client = None
dynamodb = None


def _get_bedrock_client():
    global bedrock_runtime
    if bedrock_runtime is None:
        bedrock_runtime = boto3.client(
            "bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1")
        )
    return bedrock_runtime


def _get_s3_client():
    global s3_client
    if s3_client is None:
        s3_client = boto3.client("s3")
    return s3_client


def _get_dynamodb_resource():
    global dynamodb
    if dynamodb is None:
        dynamodb = boto3.resource("dynamodb")
    return dynamodb


# Environment variables
DOCUMENT_EXTRACTIONS_TABLE = os.environ.get(
    "DOCUMENT_EXTRACTIONS_TABLE", "ai-sw-pm-document-extractions"
)
BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0"
)

# Initialize logger
logger = get_logger()


def extract_sla_clauses_from_contract(
    document_id: str, tenant_id: str, extracted_text: str
) -> List[Dict[str, Any]]:
    """
    Extract SLA clauses from contract document using Amazon Bedrock.

    Requirements:
    - 12.1: Extract SLA definitions using Document_Intelligence
    - 12.2: Identify SLA metrics, thresholds, and penalty clauses

    Args:
        document_id: Document ID
        tenant_id: Tenant ID
        extracted_text: Extracted text from document

    Returns:
        List of extracted SLA clause dictionaries

    Raises:
        ProcessingError: If extraction fails
    """
    try:
        logger.info(f"Extracting SLA clauses from contract document: {document_id}")

        # Construct prompt for Bedrock Claude (Requirement 12.2)
        prompt = _construct_sla_extraction_prompt(extracted_text)

        # Call Bedrock API
        response = _call_bedrock_claude(prompt)

        # Parse response
        sla_clauses = _parse_sla_extraction_response(response)

        # Store extractions in DynamoDB (Requirement 12.4)
        extraction_ids = _store_sla_extractions(
            document_id=document_id, tenant_id=tenant_id, sla_clauses=sla_clauses
        )

        logger.info(
            f"Extracted {len(sla_clauses)} SLA clauses from document {document_id}"
        )

        return sla_clauses

    except Exception as e:
        logger.error(f"Failed to extract SLA clauses: {str(e)}")
        raise ProcessingError(
            f"SLA extraction failed: {str(e)}", processing_type="sla_extraction"
        )


def _construct_sla_extraction_prompt(extracted_text: str) -> str:
    """
    Construct prompt for SLA clause extraction.

    Args:
        extracted_text: Text extracted from contract document

    Returns:
        Formatted prompt string
    """
    prompt = f"""Extract all SLA (Service Level Agreement) clauses from this contract document.

For each SLA clause, identify:
- SLA metric name (required, e.g., "System Uptime", "Response Time", "Resolution Time")
- Target threshold (required, e.g., "99.9%", "< 2 seconds", "within 24 hours")
- Measurement period (required, e.g., "monthly", "per incident", "quarterly")
- Penalty clause (if mentioned, describe the penalty for not meeting the SLA)
- Reporting requirements (if mentioned)

Return the results as a JSON array with the following structure:
[
  {{
    "slaMetricName": "string",
    "targetThreshold": "string",
    "measurementPeriod": "string",
    "penaltyClause": "string or null",
    "reportingRequirements": "string or null",
    "confidence": 0.0-1.0 (your confidence in this extraction)
  }}
]

If no SLA clauses are found, return an empty array [].

Contract text:
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
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,  # Low temperature for more deterministic extraction
            "top_p": 0.9,
        }

        # Call Bedrock API
        response = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps(request_body),
            contentType="application/json",
            accept="application/json",
        )

        # Parse response
        response_body = json.loads(response["body"].read())

        # Extract text from Claude response
        if "content" in response_body and len(response_body["content"]) > 0:
            return response_body["content"][0]["text"]

        raise ProcessingError(
            "Invalid response format from Bedrock", processing_type="bedrock_api"
        )

    except Exception as e:
        logger.error(f"Bedrock API call failed: {str(e)}")
        raise ProcessingError(
            f"Failed to call Bedrock API: {str(e)}", processing_type="bedrock_api"
        )


def _parse_sla_extraction_response(response_text: str) -> List[Dict[str, Any]]:
    """
    Parse SLA extraction response from Bedrock.

    Args:
        response_text: Response text from Bedrock

    Returns:
        List of SLA clause dictionaries

    Raises:
        ProcessingError: If parsing fails
    """
    try:
        # Extract JSON from response (handle cases where model adds explanation)
        response_text = response_text.strip()

        # Find JSON array in response
        start_idx = response_text.find("[")
        end_idx = response_text.rfind("]") + 1

        if start_idx == -1 or end_idx == 0:
            logger.warning("No JSON array found in response")
            return []

        json_text = response_text[start_idx:end_idx]
        sla_clauses = json.loads(json_text)

        # Validate and normalize SLA data
        normalized_clauses = []
        for clause in sla_clauses:
            if not isinstance(clause, dict):
                continue

            # Ensure required fields
            required_fields = ["slaMetricName", "targetThreshold", "measurementPeriod"]
            if not all(field in clause for field in required_fields):
                logger.warning(
                    f"Skipping SLA clause with missing required fields: {clause}"
                )
                continue

            # Normalize confidence score
            confidence = float(clause.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]

            normalized_clause = {
                "slaMetricName": clause["slaMetricName"],
                "targetThreshold": clause["targetThreshold"],
                "measurementPeriod": clause["measurementPeriod"],
                "penaltyClause": clause.get("penaltyClause"),
                "reportingRequirements": clause.get("reportingRequirements"),
                "confidence": confidence,
            }

            normalized_clauses.append(normalized_clause)

        return normalized_clauses

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {str(e)}")
        logger.error(f"Response text: {response_text[:500]}")
        raise ProcessingError(
            f"Failed to parse SLA extraction response: {str(e)}",
            processing_type="response_parsing",
        )
    except Exception as e:
        logger.error(f"Failed to process extraction response: {str(e)}")
        raise ProcessingError(
            f"Failed to process extraction response: {str(e)}",
            processing_type="response_parsing",
        )


def _store_sla_extractions(
    document_id: str, tenant_id: str, sla_clauses: List[Dict[str, Any]]
) -> List[str]:
    """
    Store SLA extractions in DynamoDB for user confirmation.

    Requirement 12.4: Present extractions to user for confirmation

    Args:
        document_id: Document ID
        tenant_id: Tenant ID
        sla_clauses: List of extracted SLA clauses

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

        for clause in sla_clauses:
            # Generate extraction ID
            import uuid

            extraction_id = str(uuid.uuid4())

            # Determine if requires review based on confidence (Requirement 12.7)
            requires_review = clause["confidence"] < LOW_CONFIDENCE_THRESHOLD

            # Store extraction
            extraction_item = {
                "PK": f"DOCUMENT#{document_id}",
                "SK": f"EXTRACTION#{extraction_id}",
                "extractionId": extraction_id,
                "documentId": document_id,
                "tenantId": tenant_id,
                "type": "SLA",
                "content": json.dumps(clause),
                "confidence": clause["confidence"],
                "metadata": {
                    "slaMetricName": clause["slaMetricName"],
                    "targetThreshold": clause["targetThreshold"],
                    "measurementPeriod": clause["measurementPeriod"],
                    "penaltyClause": clause.get("penaltyClause"),
                },
                "requiresReview": requires_review,
                "status": "PENDING_REVIEW",
                "createdAt": timestamp,
            }

            table.put_item(Item=extraction_item)
            extraction_ids.append(extraction_id)

            logger.info(
                f"Stored SLA extraction {extraction_id} "
                f"(confidence: {clause['confidence']:.2f}, requires_review: {requires_review})"
            )

        return extraction_ids

    except Exception as e:
        logger.error(f"Failed to store SLA extractions: {str(e)}")
        raise ProcessingError(
            f"Failed to store extractions: {str(e)}", processing_type="data_storage"
        )
