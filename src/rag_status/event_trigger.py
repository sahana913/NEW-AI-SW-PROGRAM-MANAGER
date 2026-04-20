"""EventBridge trigger configuration for RAG status calculation."""

from shared.logger import get_logger
import os
import sys

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


logger = get_logger()


def get_event_rule_config() -> dict:
    """
    Get EventBridge rule configuration for RAG status calculation.

    This rule triggers RAG status calculation whenever a health score is updated.

    Returns:
        EventBridge rule configuration
    """
    return {
        "Name": "HealthScoreUpdated-TriggerRagCalculation",
        "Description": "Trigger RAG status calculation when health score is updated",
        "EventPattern": {
            "source": ["ai-sw-pm.health-score"],
            "detail-type": ["HealthScoreCalculated"],
        },
        "State": "ENABLED",
        "Targets": [
            {
                "Id": "RagStatusCalculationLambda",
                "Arn": "${RAG_STATUS_LAMBDA_ARN}",  # To be replaced during deployment
                "RetryPolicy": {"MaximumRetryAttempts": 2, "MaximumEventAge": 3600},
            }
        ],
    }


def get_lambda_permission_config() -> dict:
    """
    Get Lambda permission configuration to allow EventBridge to invoke the function.

    Returns:
        Lambda permission configuration
    """
    return {
        "FunctionName": "${RAG_STATUS_LAMBDA_NAME}",  # To be replaced during deployment
        "StatementId": "AllowEventBridgeInvoke",
        "Action": "lambda:InvokeFunction",
        "Principal": "events.amazonaws.com",
        "SourceArn": "${EVENT_RULE_ARN}",  # To be replaced during deployment
    }
