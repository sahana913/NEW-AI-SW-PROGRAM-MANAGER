"""AI-powered risk explanation generation using Amazon Bedrock."""

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


def create_velocity_decline_prompt(risk: Dict[str, Any]) -> str:
    """
    Create prompt for velocity decline risk explanation.

    Args:
        risk: Risk alert dictionary with metrics

    Returns:
        Formatted prompt string
    """
    metrics = risk.get("metrics", {})

    prompt = f"""You are an AI program management assistant. Analyze the following velocity decline and provide a concise explanation and recommendations.

Project Velocity Decline:
- Current velocity: {metrics.get('current_velocity', 0)} points
- Previous velocity: {metrics.get('previous_velocity', 0)} points
- 4-sprint moving average: {metrics.get('moving_average', 0)} points
- Decline percentage: {metrics.get('decline_percentage', 0):.1f}%
- Historical velocities: {metrics.get('historical_data', [])}

Provide:
1. A brief explanation (2-3 sentences) of why this velocity decline is concerning
2. Three specific, actionable recommendations to address the issue

Keep your response concise and focused on actionable insights."""

    return prompt


def create_backlog_growth_prompt(risk: Dict[str, Any]) -> str:
    """
    Create prompt for backlog growth risk explanation.

    Args:
        risk: Risk alert dictionary with metrics

    Returns:
        Formatted prompt string
    """
    metrics = risk.get("metrics", {})
    items_by_type = metrics.get("items_by_type", {})

    prompt = f"""You are an AI program management assistant. Analyze the following backlog growth and provide a concise explanation and recommendations.

Backlog Growth Analysis:
- Open items: {metrics.get('open_items', 0)}
- Total items: {metrics.get('total_items', 0)}
- Weekly growth rate: {metrics.get('growth_rate', 0):.1f}%
- Team completion rate: {metrics.get('completion_rate', 0):.1f} items/week
- Items by type: {items_by_type.get('bug', 0)} bugs, {items_by_type.get('feature', 0)} features, {items_by_type.get('technical_debt', 0)} tech debt
- Average item age: {metrics.get('average_age', 0):.1f} days

Provide:
1. A brief explanation (2-3 sentences) of why this backlog growth is concerning
2. Three specific, actionable recommendations to address the issue

Keep your response concise and focused on actionable insights."""

    return prompt


def create_milestone_slippage_prompt(risk: Dict[str, Any]) -> str:
    """
    Create prompt for milestone slippage risk explanation.

    Args:
        risk: Risk alert dictionary with metrics

    Returns:
        Formatted prompt string
    """
    metrics = risk.get("metrics", {})

    prompt = f"""You are an AI program management assistant. Analyze the following milestone slippage risk and provide a concise explanation and recommendations.

Milestone Slippage Analysis:
- Milestone: {risk.get('milestone_name', 'Unknown')}
- Completion: {metrics.get('completion_percentage', 0):.1f}%
- Time remaining: {metrics.get('time_remaining_days', 0)} days ({metrics.get('time_remaining_percentage', 0):.1f}% of timeline)
- Estimated delay: {metrics.get('estimated_delay_days', 0)} days
- Due date: {metrics.get('due_date', 'Unknown')}
- Dependent milestones: {len(metrics.get('dependent_milestones', []))}

Provide:
1. A brief explanation (2-3 sentences) of why this milestone is at risk
2. Three specific, actionable recommendations to get back on track

Keep your response concise and focused on actionable insights."""

    return prompt


def invoke_bedrock_claude(prompt: str, max_tokens: int = 500) -> str:
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
            f"Failed to generate AI explanation: {str(e)}",
            processing_type="AI_Generation",
        )


def parse_ai_response(response_text: str) -> Dict[str, Any]:
    """
    Parse AI response into structured format.

    Args:
        response_text: Raw AI-generated text

    Returns:
        Dictionary with explanation and recommendations
    """
    # Simple parsing: split by numbered lists
    lines = response_text.split("\n")

    explanation_lines = []
    recommendations = []

    in_recommendations = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check if this is a recommendation line
        if any(
            line.startswith(f"{i}.") or line.startswith(f"{i})") for i in range(1, 10)
        ):
            in_recommendations = True
            # Extract recommendation text
            rec_text = line.split(".", 1)[-1].split(")", 1)[-1].strip()
            if rec_text:
                recommendations.append(rec_text)
        elif not in_recommendations:
            explanation_lines.append(line)

    explanation = " ".join(explanation_lines).strip()

    # Ensure we have at least some content
    if not explanation:
        explanation = response_text[:200]  # First 200 chars as fallback

    if not recommendations:
        recommendations = [
            "Review project resources and capacity",
            "Identify and remove blockers",
            "Consider adjusting timeline or scope",
        ]

    return {
        "explanation": explanation,
        "recommendations": recommendations[:3],  # Limit to 3 recommendations
    }


def generate_risk_explanation(risk: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate AI-powered explanation and recommendations for a risk.

    Validates: Property 20 - AI-Generated Risk Explanations

    Args:
        risk: Risk alert dictionary

    Returns:
        Dictionary with 'description' and 'recommendations' fields

    Raises:
        ProcessingError: If generation fails
    """
    risk_type = risk.get("type", "")

    try:
        # Create appropriate prompt based on risk type
        if risk_type == "VELOCITY_DECLINE":
            prompt = create_velocity_decline_prompt(risk)
        elif risk_type == "BACKLOG_GROWTH":
            prompt = create_backlog_growth_prompt(risk)
        elif risk_type == "MILESTONE_SLIPPAGE":
            prompt = create_milestone_slippage_prompt(risk)
        else:
            # Generic prompt
            prompt = f"Analyze this project risk and provide recommendations: {json.dumps(risk, indent=2)}"

        logger.info(
            f"Generating AI explanation for risk", extra={"risk_type": risk_type}
        )

        # Invoke Bedrock
        response_text = invoke_bedrock_claude(prompt, max_tokens=500)

        # Parse response
        parsed = parse_ai_response(response_text)

        logger.info(
            f"AI explanation generated successfully",
            extra={
                "risk_type": risk_type,
                "explanation_length": len(parsed["explanation"]),
            },
        )

        return {
            "description": parsed["explanation"],
            "recommendations": parsed["recommendations"],
        }

    except Exception as e:
        logger.error(
            f"Failed to generate AI explanation for risk",
            extra={"risk_type": risk_type, "error": str(e)},
        )

        # Return fallback explanation
        return {
            "description": f"Risk detected: {risk.get('title', 'Unknown risk')}. Manual review recommended.",
            "recommendations": [
                "Review project metrics and identify root causes",
                "Consult with team leads and stakeholders",
                "Develop action plan to address the issue",
            ],
        }


def enrich_risk_with_ai(risk: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich a risk alert with AI-generated explanation and recommendations.

    This is the main entry point for adding AI explanations to risks.

    Args:
        risk: Risk alert dictionary

    Returns:
        Enriched risk dictionary with 'description' and 'recommendations'
    """
    try:
        ai_content = generate_risk_explanation(risk)

        # Add AI-generated content to risk
        risk["description"] = ai_content["description"]
        risk["recommendations"] = ai_content["recommendations"]

        return risk

    except Exception as e:
        logger.error(
            f"Failed to enrich risk with AI",
            extra={"risk_id": risk.get("risk_id"), "error": str(e)},
        )

        # Return risk with basic description
        risk["description"] = f"Risk detected: {risk.get('title', 'Unknown risk')}"
        risk["recommendations"] = ["Review and address this risk"]

        return risk
