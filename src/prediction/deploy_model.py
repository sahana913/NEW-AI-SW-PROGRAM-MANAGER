"""
Script to deploy trained models to SageMaker endpoints
"""

from src.prediction.model_deployment import ModelDeployment
import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """Main function to deploy models"""
    parser = argparse.ArgumentParser(
        description="Deploy delay prediction models to SageMaker"
    )
    parser.add_argument(
        "--model-data",
        type=str,
        required=True,
        help="S3 URI to model artifacts (e.g., s3://bucket/path/model.tar.gz)",
    )
    parser.add_argument(
        "--role-arn", type=str, required=True, help="IAM role ARN for SageMaker"
    )
    parser.add_argument("--endpoint-name", type=str, help="Optional endpoint name")
    parser.add_argument(
        "--instance-type", type=str, default="ml.m5.large", help="Instance type"
    )
    parser.add_argument(
        "--initial-instance-count", type=int, default=1, help="Initial instance count"
    )
    parser.add_argument(
        "--enable-autoscaling",
        action="store_true",
        default=True,
        help="Enable auto-scaling",
    )
    parser.add_argument(
        "--min-capacity",
        type=int,
        default=1,
        help="Minimum instance count for auto-scaling",
    )
    parser.add_argument(
        "--max-capacity",
        type=int,
        default=3,
        help="Maximum instance count for auto-scaling",
    )
    parser.add_argument("--region", type=str, default="us-east-1", help="AWS region")

    args = parser.parse_args()

    logger.info("Starting model deployment")
    logger.info(f"Model data: {args.model_data}")
    logger.info(f"Role ARN: {args.role_arn}")
    logger.info(f"Region: {args.region}")

    # Initialize deployment
    try:
        deployment = ModelDeployment(region=args.region)
    except Exception as e:
        logger.error(f"Failed to initialize deployment: {e}")
        return 1

    # Deploy model
    try:
        deployment_info = deployment.deploy_model(
            model_data=args.model_data,
            role_arn=args.role_arn,
            endpoint_name=args.endpoint_name,
            instance_type=args.instance_type,
            initial_instance_count=args.initial_instance_count,
            enable_autoscaling=args.enable_autoscaling,
            min_capacity=args.min_capacity,
            max_capacity=args.max_capacity,
        )

        logger.info("Deployment complete!")
        logger.info(f"Endpoint name: {deployment_info['endpoint_name']}")
        logger.info(f"Model name: {deployment_info['model_name']}")
        logger.info(f"Config name: {deployment_info['config_name']}")
        logger.info(f"Auto-scaling enabled: {deployment_info['autoscaling_enabled']}")

        return 0

    except Exception as e:
        logger.error(f"Error during deployment: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
