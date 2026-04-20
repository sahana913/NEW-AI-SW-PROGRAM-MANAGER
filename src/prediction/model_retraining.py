"""
Model Retraining Workflow

Implements monthly model retraining with performance evaluation and deployment.
"""

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

import boto3

logger = logging.getLogger(__name__)


class ModelRetrainingWorkflow:
    """Manages model retraining workflow"""

    def __init__(self, bucket_name: str, role_arn: str, region: str = "us-east-1"):
        """
        Initialize retraining workflow

        Args:
            bucket_name: S3 bucket for model artifacts
            role_arn: IAM role ARN for SageMaker
            region: AWS region
        """
        self.bucket_name = bucket_name
        self.role_arn = role_arn
        self.region = region
        self.s3_client = boto3.client("s3", region_name=region)
        self.dynamodb = boto3.resource("dynamodb", region_name=region)

        # Model registry table
        self.model_registry_table = self.dynamodb.Table("ModelRegistry")

        logger.info("Initialized model retraining workflow")

    def get_current_model_version(self, model_type: str) -> Optional[Dict[str, Any]]:
        """
        Get current deployed model version

        Args:
            model_type: Model type (DELAY_CLASSIFIER, DELAY_REGRESSOR, WORKLOAD)

        Returns:
            Current model version info or None
        """
        logger.info(f"Getting current model version for: {model_type}")

        try:
            response = self.model_registry_table.query(
                KeyConditionExpression="PK = :pk",
                ExpressionAttributeValues={":pk": f"MODEL#{model_type}"},
                ScanIndexForward=False,
                Limit=1,
            )

            items = response.get("Items", [])
            if items:
                return items[0]

            return None

        except Exception as e:
            logger.error(f"Error getting current model version: {e}")
            return None

    def register_model_version(
        self,
        model_type: str,
        model_data: str,
        endpoint_name: str,
        metrics: Dict[str, float],
        training_job_name: str,
    ) -> str:
        """
        Register new model version in registry

        Args:
            model_type: Model type
            model_data: S3 URI to model artifacts
            endpoint_name: Endpoint name
            metrics: Model performance metrics
            training_job_name: Training job name

        Returns:
            Version ID
        """
        logger.info(f"Registering model version for: {model_type}")

        timestamp = datetime.utcnow().isoformat()
        version_id = f"v{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Convert float metrics to Decimal for DynamoDB
        decimal_metrics = {k: Decimal(str(v)) for k, v in metrics.items()}

        item = {
            "PK": f"MODEL#{model_type}",
            "SK": f"VERSION#{version_id}",
            "version_id": version_id,
            "model_type": model_type,
            "model_data": model_data,
            "endpoint_name": endpoint_name,
            "training_job_name": training_job_name,
            "metrics": decimal_metrics,
            "status": "DEPLOYED",
            "created_at": timestamp,
            "deployed_at": timestamp,
        }

        self.model_registry_table.put_item(Item=item)

        logger.info(f"Registered model version: {version_id}")

        return version_id

    def evaluate_model_improvement(
        self,
        current_metrics: Dict[str, float],
        new_metrics: Dict[str, float],
        model_type: str,
        improvement_threshold: float = 0.05,
    ) -> bool:
        """
        Evaluate if new model is better than current model

        Args:
            current_metrics: Current model metrics
            new_metrics: New model metrics
            model_type: Model type
            improvement_threshold: Minimum improvement threshold (5% by default)

        Returns:
            True if new model should be deployed
        """
        logger.info("Evaluating model improvement")

        if not current_metrics:
            logger.info("No current model - deploying new model")
            return True

        # Determine primary metric based on model type
        if model_type in ["DELAY_CLASSIFIER"]:
            primary_metric = "validation:auc"
            higher_is_better = True
        elif model_type in ["DELAY_REGRESSOR", "WORKLOAD"]:
            primary_metric = "validation:rmse"
            higher_is_better = False
        else:
            logger.warning(f"Unknown model type: {model_type}")
            return False

        current_value = current_metrics.get(primary_metric)
        new_value = new_metrics.get(primary_metric)

        if current_value is None or new_value is None:
            logger.warning(f"Missing metric {primary_metric}")
            return False

        # Convert Decimal to float if needed
        if isinstance(current_value, Decimal):
            current_value = float(current_value)
        if isinstance(new_value, Decimal):
            new_value = float(new_value)

        # Calculate improvement
        if higher_is_better:
            improvement = (new_value - current_value) / current_value
        else:
            improvement = (current_value - new_value) / current_value

        logger.info(
            f"Model improvement: {improvement:.2%} (threshold: {improvement_threshold:.2%})"
        )
        logger.info(
            f"Current {primary_metric}: {current_value}, New {primary_metric}: {new_value}"
        )

        should_deploy = improvement >= improvement_threshold

        if should_deploy:
            logger.info(
                "New model shows sufficient improvement - recommending deployment"
            )
        else:
            logger.info(
                "New model does not show sufficient improvement - keeping current model"
            )

        return should_deploy

    def retrain_delay_models(self, db_connection) -> Dict[str, Any]:
        """
        Retrain delay prediction models

        Args:
            db_connection: Database connection

        Returns:
            Retraining results
        """
        logger.info("Starting delay model retraining")

        from prediction.model_deployment import ModelDeployment
        from prediction.model_training import DelayPredictionModelTrainer
        from prediction.training_data_preparation import TrainingDataPreparation

        # Prepare training data
        prep = TrainingDataPreparation(db_connection)
        data_splits = prep.prepare_training_data()

        if data_splits["train"].empty:
            logger.warning("No training data available")
            return {"status": "SKIPPED", "reason": "No training data"}

        # Train models
        trainer = DelayPredictionModelTrainer(
            bucket_name=self.bucket_name, role_arn=self.role_arn, region=self.region
        )

        training_results = trainer.train_models(
            data_splits["train"], data_splits["val"], data_splits["test"]
        )

        # Get current model versions
        current_classifier = self.get_current_model_version("DELAY_CLASSIFIER")
        current_regressor = self.get_current_model_version("DELAY_REGRESSOR")

        # Evaluate classifier improvement
        classifier_metrics = training_results["metadata"]["classifier"]["metrics"]
        should_deploy_classifier = self.evaluate_model_improvement(
            current_classifier.get("metrics", {}) if current_classifier else {},
            classifier_metrics,
            "DELAY_CLASSIFIER",
        )

        results = {
            "classifier": {
                "trained": True,
                "metrics": classifier_metrics,
                "should_deploy": should_deploy_classifier,
            }
        }

        # Deploy classifier if improved
        if should_deploy_classifier:
            logger.info("Deploying new classifier model")
            deployment = ModelDeployment(region=self.region)

            deployment_info = deployment.deploy_model(
                model_data=training_results["classifier"].model_data,
                role_arn=self.role_arn,
                endpoint_name="delay-classifier-endpoint",
            )

            # Register new version
            self.register_model_version(
                model_type="DELAY_CLASSIFIER",
                model_data=training_results["classifier"].model_data,
                endpoint_name=deployment_info["endpoint_name"],
                metrics=classifier_metrics,
                training_job_name=training_results[
                    "classifier"
                ].latest_training_job.name,
            )

            results["classifier"]["deployed"] = True
            results["classifier"]["endpoint"] = deployment_info["endpoint_name"]

        # Evaluate regressor if available
        if training_results["regressor"]:
            regressor_metrics = training_results["metadata"]["regressor"]["metrics"]
            should_deploy_regressor = self.evaluate_model_improvement(
                current_regressor.get("metrics", {}) if current_regressor else {},
                regressor_metrics,
                "DELAY_REGRESSOR",
            )

            results["regressor"] = {
                "trained": True,
                "metrics": regressor_metrics,
                "should_deploy": should_deploy_regressor,
            }

            if should_deploy_regressor:
                logger.info("Deploying new regressor model")
                deployment = ModelDeployment(region=self.region)

                deployment_info = deployment.deploy_model(
                    model_data=training_results["regressor"].model_data,
                    role_arn=self.role_arn,
                    endpoint_name="delay-regressor-endpoint",
                )

                self.register_model_version(
                    model_type="DELAY_REGRESSOR",
                    model_data=training_results["regressor"].model_data,
                    endpoint_name=deployment_info["endpoint_name"],
                    metrics=regressor_metrics,
                    training_job_name=training_results[
                        "regressor"
                    ].latest_training_job.name,
                )

                results["regressor"]["deployed"] = True
                results["regressor"]["endpoint"] = deployment_info["endpoint_name"]

        logger.info("Delay model retraining complete")

        return results

    def retrain_workload_model(self, db_connection) -> Dict[str, Any]:
        """
        Retrain workload prediction model

        Args:
            db_connection: Database connection

        Returns:
            Retraining results
        """
        logger.info("Starting workload model retraining")

        from prediction.model_deployment import ModelDeployment
        from prediction.workload_prediction import WorkloadPredictionTrainer

        # Prepare training data
        trainer = WorkloadPredictionTrainer(
            bucket_name=self.bucket_name, role_arn=self.role_arn, region=self.region
        )

        train_df, val_df, test_df = trainer.prepare_workload_training_data(
            db_connection
        )

        if train_df.empty:
            logger.warning("No workload training data available")
            return {"status": "SKIPPED", "reason": "No training data"}

        # Train model
        estimator = trainer.train_workload_model(train_df, val_df)

        # Get metrics (simplified - in production, evaluate on test set)
        metrics = {"training_complete": True}

        # Get current model
        current_model = self.get_current_model_version("WORKLOAD")

        # For workload model, always deploy if training succeeds
        # (in production, you'd evaluate metrics properly)
        should_deploy = True

        results = {"trained": True, "metrics": metrics, "should_deploy": should_deploy}

        if should_deploy:
            logger.info("Deploying new workload model")
            deployment = ModelDeployment(region=self.region)

            deployment_info = deployment.deploy_model(
                model_data=estimator.model_data,
                role_arn=self.role_arn,
                endpoint_name="workload-prediction-endpoint",
            )

            self.register_model_version(
                model_type="WORKLOAD",
                model_data=estimator.model_data,
                endpoint_name=deployment_info["endpoint_name"],
                metrics=metrics,
                training_job_name=estimator.latest_training_job.name,
            )

            results["deployed"] = True
            results["endpoint"] = deployment_info["endpoint_name"]

        logger.info("Workload model retraining complete")

        return results


def lambda_handler(event, context):
    """
    Lambda handler for monthly model retraining

    Triggered by EventBridge scheduled rule
    """
    logger.info("Starting monthly model retraining")

    # Get configuration from environment
    bucket_name = os.environ.get("MODEL_BUCKET")
    role_arn = os.environ.get("SAGEMAKER_ROLE_ARN")
    region = os.environ.get("AWS_REGION", "us-east-1")

    if not bucket_name or not role_arn:
        logger.error("Missing required environment variables")
        return {"statusCode": 500, "body": json.dumps({"error": "Configuration error"})}

    # Initialize workflow
    workflow = ModelRetrainingWorkflow(
        bucket_name=bucket_name, role_arn=role_arn, region=region
    )

    # Get database connection
    from shared.database import get_db_connection

    db_conn = get_db_connection()

    try:
        # Retrain delay models
        delay_results = workflow.retrain_delay_models(db_conn)

        # Retrain workload model
        workload_results = workflow.retrain_workload_model(db_conn)

        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "delay_models": delay_results,
            "workload_model": workload_results,
        }

        logger.info(f"Retraining complete: {results}")

        return {"statusCode": 200, "body": json.dumps(results, default=str)}

    except Exception as e:
        logger.error(f"Error during retraining: {e}", exc_info=True)
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

    finally:
        if db_conn:
            db_conn.close()
