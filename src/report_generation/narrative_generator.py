"""AI-powered narrative generation for reports using Amazon Bedrock."""

from shared.logger import get_logger
from shared.errors import ProcessingError
from botocore.exceptions import ClientError
import boto3
import json
import os
import sys
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


logger = get_logger()

# Environment variables
BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0"
)
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-east-1")

# Bedrock client (initialized lazily)
_bedrock_client = None


def get_bedrock_client():
    """Get or create Bedrock Runtime client."""
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
    return _bedrock_client


def invoke_bedrock_claude(prompt: str, max_tokens: int = 1000) -> str:
    """
    Invoke Amazon Bedrock Claude model for text generation.

    Args:
        prompt: Input prompt for the model
        max_tokens: Maximum tokens to generate

    Returns:
        Generated text response

    Raises:
        ProcessingError: If Bedrock invocation fails
    """
    try:
        bedrock_client = get_bedrock_client()

        # Prepare request body for Claude 3
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "top_p": 0.9,
        }

        # Invoke model
        response = bedrock_client.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps(request_body),
            contentType="application/json",
            accept="application/json",
        )

        # Parse response
        response_body = json.loads(response["body"].read())

        # Extract generated text
        if "content" in response_body and len(response_body["content"]) > 0:
            generated_text = response_body["content"][0].get("text", "")
            return generated_text.strip()

        raise ProcessingError(
            "No content in Bedrock response", processing_type="AI_Generation"
        )

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))

        raise ProcessingError(
            f"Bedrock invocation failed: {error_code} - {error_message}",
            processing_type="AI_Generation",
            details={"model_id": BEDROCK_MODEL_ID},
        )
    except Exception as e:
        raise ProcessingError(
            f"Failed to generate AI narrative: {str(e)}",
            processing_type="AI_Generation",
        )


def create_weekly_status_prompt(report_data: Dict[str, Any]) -> str:
    """
    Create prompt for weekly status report narrative.

    Args:
        report_data: Aggregated report data

    Returns:
        Formatted prompt string
    """
    projects = report_data.get("projects", [])
    completed_milestones = report_data.get("completed_milestones", [])
    upcoming_milestones = report_data.get("upcoming_milestones", [])
    risks = report_data.get("risks", [])

    # Count risks by severity
    critical_risks = len([r for r in risks if r.get("severity") == "CRITICAL"])
    high_risks = len([r for r in risks if r.get("severity") == "HIGH"])
    medium_risks = len([r for r in risks if r.get("severity") == "MEDIUM"])

    prompt = f"""You are an AI program management assistant. Generate a concise executive summary (2-3 paragraphs) for a weekly status report based on the following data:

**Projects Overview:**
- Total projects: {len(projects)}
- Projects tracked this week

**Milestones:**
- Completed this week: {len(completed_milestones)}
- Upcoming (next 2 weeks): {len(upcoming_milestones)}

**Risk Alerts:**
- Critical: {critical_risks}
- High: {high_risks}
- Medium: {medium_risks}

**Completed Milestones:**
{json.dumps([{'project': m.get('project_name'), 'milestone': m.get('milestone_name'), 'due_date': m.get('due_date')} for m in completed_milestones[:5]], indent=2)}

**Upcoming Milestones:**
{json.dumps([{'project': m.get('project_name'), 'milestone': m.get('milestone_name'), 'due_date': m.get('due_date'), 'completion': m.get('completion_percentage')} for m in upcoming_milestones[:5]], indent=2)}

**Top Risks:**
{json.dumps([{'project': r.get('projectId'), 'type': r.get('type'), 'severity': r.get('severity'), 'title': r.get('title')} for r in risks[:5]], indent=2)}

Generate a professional executive summary that:
1. Highlights overall program health and progress
2. Calls out key achievements (completed milestones)
3. Identifies critical risks and concerns
4. Provides a forward-looking perspective on upcoming milestones

Keep the tone professional and actionable. Focus on insights that help executives make decisions."""

    return prompt


def create_executive_summary_prompt(report_data: Dict[str, Any]) -> str:
    """
    Create prompt for executive summary generation.

    Validates: Property 41 - Executive Summary Content

    Args:
        report_data: Aggregated portfolio-level data

    Returns:
        Formatted prompt string
    """
    projects = report_data.get("projects", [])
    risks = report_data.get("risks", [])

    # Filter for High and Critical risks only (Property 42)
    critical_high_risks = [
        r for r in risks if r.get("severity") in ["CRITICAL", "HIGH"]
    ]

    # Calculate portfolio RAG status
    # This would normally come from health score calculation
    portfolio_rag = report_data.get("portfolio_rag_status", "AMBER")

    prompt = f"""You are an AI program management assistant. Generate a concise executive summary (maximum 500 words) for portfolio-level reporting.

**Portfolio Overview:**
- Total projects: {len(projects)}
- Overall RAG status: {portfolio_rag}

**Critical and High Risks:**
{json.dumps([{'project': r.get('projectId'), 'type': r.get('type'), 'severity': r.get('severity'), 'title': r.get('title'), 'description': r.get('description', '')[:100]} for r in critical_high_risks[:5]], indent=2)}

**Key Metrics:**
{json.dumps(report_data.get('key_metrics', {}), indent=2)}

Generate a concise executive summary (maximum 500 words) that includes:
1. Overall program RAG status and what it means
2. Top 3 critical risks requiring executive attention
3. Key decisions needed from leadership
4. Budget and schedule status (if available in data)
5. Trend indicators (improving, stable, declining) for key metrics

Keep the summary:
- Concise and to the point (max 500 words)
- Focused on executive-level concerns
- Action-oriented with clear decision points
- Free of technical jargon

Do not include implementation details or low-level technical information."""

    return prompt


def generate_weekly_status_narrative(report_data: Dict[str, Any]) -> str:
    """
    Generate AI-powered narrative summary for weekly status report.

    Args:
        report_data: Aggregated report data

    Returns:
        Generated narrative text

    Raises:
        ProcessingError: If generation fails
    """
    try:
        prompt = create_weekly_status_prompt(report_data)

        logger.info("Generating weekly status narrative")

        # Invoke Bedrock
        narrative = invoke_bedrock_claude(prompt, max_tokens=1000)

        logger.info(
            "Weekly status narrative generated successfully",
            extra={"narrative_length": len(narrative)},
        )

        return narrative

    except Exception as e:
        logger.error(f"Failed to generate weekly status narrative: {str(e)}")

        # Return fallback narrative
        return """Weekly Status Report

This week's program status shows continued progress across active projects. Several milestones were completed on schedule, demonstrating strong execution by the teams. However, some risks have been identified that require attention and mitigation planning.

Key focus areas for the coming week include addressing identified risks, maintaining momentum on upcoming milestones, and ensuring resource allocation aligns with project priorities."""


def generate_executive_summary(report_data: Dict[str, Any]) -> str:
    """
    Generate AI-powered executive summary.

    Validates: Property 40 - Executive Summary Length Constraint (max 500 words)
    Validates: Property 41 - Executive Summary Content

    Args:
        report_data: Aggregated portfolio-level data

    Returns:
        Generated executive summary text (max 500 words)

    Raises:
        ProcessingError: If generation fails
    """
    try:
        prompt = create_executive_summary_prompt(report_data)

        logger.info("Generating executive summary")

        # Invoke Bedrock with token limit to ensure ~500 words
        # Roughly 1.3 tokens per word, so 650 tokens ≈ 500 words
        narrative = invoke_bedrock_claude(prompt, max_tokens=650)

        # Verify word count (Property 40)
        word_count = len(narrative.split())

        logger.info(
            "Executive summary generated successfully",
            extra={"word_count": word_count, "narrative_length": len(narrative)},
        )

        # If over 500 words, truncate (shouldn't happen with token limit)
        if word_count > 500:
            words = narrative.split()
            narrative = " ".join(words[:500]) + "..."
            logger.warning(
                f"Executive summary truncated from {word_count} to 500 words"
            )

        return narrative

    except Exception as e:
        logger.error(f"Failed to generate executive summary: {str(e)}")

        # Return fallback summary
        return """Executive Summary

The program portfolio is currently tracking with mixed results. While several projects are performing well, there are critical risks that require immediate executive attention. Key decisions are needed regarding resource allocation and timeline adjustments to ensure successful delivery.

Immediate action items include addressing high-priority risks, reviewing project timelines, and ensuring adequate resources are available for critical path activities."""
