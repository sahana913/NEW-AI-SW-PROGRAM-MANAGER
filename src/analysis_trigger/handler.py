"""Analysis Trigger Lambda handler - Trigger risk detection and prediction analysis."""

from shared.logger import get_logger
import json
import os
import sys
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))


logger = get_logger()

# AWS clients (initialized lazily)
_lambda_client = None
_eventbridge = None


def get_lambda_client():
    """Get or create Lambda client."""
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client("lambda")
    return _lambda_client


def get_eventbridge_client():
    """Get or create EventBridge client."""
    global _eventbridge
    if _eventbridge is None:
        _eventbridge = boto3.client("events")
    return _eventbridge


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Trigger downstream analysis workflows (risk detection, predictions).

    This function publishes events to EventBridge to trigger:
    - Risk detection analysis
    - Delay probability predictions
    - Workload imbalance predictions

    Args:
        event: Step Functions event with stored project data
        context: Lambda context

    Returns:
        Trigger result with triggered analysis jobs
    """
    try:
        logger.info("Starting analysis trigger")

        # Extract stored projects from event
        stored_projects = event.get("storedProjects", [])

        if not stored_projects:
            logger.warning("No stored projects to analyze")
            return {
                "statusCode": 200,
                "triggered": True,
                "message": "No projects to analyze",
                "triggeredJobs": [],
            }

        triggered_jobs = []
        trigger_errors = []

        eventbridge = get_eventbridge_client()

        # Trigger analysis for each stored project
        for project_info in stored_projects:
            project_id = project_info.get("projectId")
            source = project_info.get("source")

            logger.info(f"Triggering analysis for project {project_id} from {source}")

            try:
                # Publish event to EventBridge for risk detection
                risk_detection_event = {
                    "Source": "ai-sw-pm.ingestion",
                    "DetailType": "ProjectDataUpdated",
                    "Detail": json.dumps(
                        {
                            "projectId": project_id,
                            "source": source,
                            "analysisType": "RISK_DETECTION",
                            "timestamp": project_info.get("storedAt"),
                        }
                    ),
                }

                eventbridge.put_events(Entries=[risk_detection_event])

                logger.info(f"Triggered risk detection for project {project_id}")

                # Publish event for prediction analysis
                prediction_event = {
                    "Source": "ai-sw-pm.ingestion",
                    "DetailType": "ProjectDataUpdated",
                    "Detail": json.dumps(
                        {
                            "projectId": project_id,
                            "source": source,
                            "analysisType": "PREDICTION",
                            "timestamp": project_info.get("storedAt"),
                        }
                    ),
                }

                eventbridge.put_events(Entries=[prediction_event])

                logger.info(f"Triggered prediction analysis for project {project_id}")

                triggered_jobs.append(
                    {
                        "projectId": project_id,
                        "source": source,
                        "analyses": ["RISK_DETECTION", "PREDICTION"],
                    }
                )

            except ClientError as e:
                error_msg = (
                    f"Failed to trigger analysis for project {project_id}: {str(e)}"
                )
                logger.error(error_msg)
                trigger_errors.append(
                    {"projectId": project_id, "source": source, "error": error_msg}
                )
            except Exception as e:
                error_msg = f"Unexpected error triggering analysis for project {project_id}: {str(e)}"
                logger.error(error_msg)
                trigger_errors.append(
                    {"projectId": project_id, "source": source, "error": error_msg}
                )

        # Determine overall trigger status
        if trigger_errors:
            logger.warning(
                f"Analysis trigger completed with {len(trigger_errors)} errors and "
                f"{len(triggered_jobs)} successful triggers"
            )

            # If all triggers failed, return error
            if not triggered_jobs:
                return {"statusCode": 500, "triggered": False, "errors": trigger_errors}

            # Partial success
            return {
                "statusCode": 200,
                "triggered": True,
                "triggeredJobs": triggered_jobs,
                "warnings": trigger_errors,
            }

        logger.info(
            f"Analysis trigger completed successfully for {len(triggered_jobs)} projects"
        )

        return {"statusCode": 200, "triggered": True, "triggeredJobs": triggered_jobs}

    except Exception as e:
        logger.error(f"Unexpected error in analysis trigger: {str(e)}")
        return {
            "statusCode": 500,
            "triggered": False,
            "errors": [{"error": "Internal trigger error", "details": str(e)}],
        }
