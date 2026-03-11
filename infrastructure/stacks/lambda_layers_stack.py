"""Lambda Layers Stack - Shared dependencies for Lambda functions."""

from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
)
from constructs import Construct
import os


class LambdaLayersStack(Stack):
    """
    Stack for Lambda layers containing shared dependencies.
    
    Optimizes cold start times by reducing individual function package sizes.
    Validates: Requirement 23.1, 23.2
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create common dependencies layer
        self.common_layer = lambda_.LayerVersion(
            self,
            "CommonDependenciesLayer",
            layer_version_name="ai-sw-pm-common-dependencies",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../layers/common")
            ),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
            description="Common Python dependencies (boto3, requests, urllib3)",
            removal_policy=None
        )

        # Create data processing layer
        self.data_processing_layer = lambda_.LayerVersion(
            self,
            "DataProcessingLayer",
            layer_version_name="ai-sw-pm-data-processing",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../layers/data_processing")
            ),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
            description="Data processing libraries (pandas, numpy)",
            removal_policy=None
        )

        # Create AI/ML layer
        self.ai_ml_layer = lambda_.LayerVersion(
            self,
            "AIMLLayer",
            layer_version_name="ai-sw-pm-ai-ml",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../layers/ai_ml")
            ),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
            description="AI/ML libraries for Bedrock and SageMaker",
            removal_policy=None
        )

