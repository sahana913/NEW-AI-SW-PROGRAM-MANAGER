"""
Workload Imbalance Prediction Module

Trains and deploys Random Forest model for workload prediction.
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Tuple

import boto3
import numpy as np
import pandas as pd
import sagemaker
from sagemaker.sklearn.estimator import SKLearn

logger = logging.getLogger(__name__)


class WorkloadPredictionTrainer:
    """Trains workload imbalance prediction models"""

    def __init__(self, bucket_name: str, role_arn: str, region: str = "us-east-1"):
        """
        Initialize workload prediction trainer

        Args:
            bucket_name: S3 bucket for model artifacts
            role_arn: IAM role ARN for SageMaker
            region: AWS region
        """
        self.bucket_name = bucket_name
        self.role_arn = role_arn
        self.region = region
        self.s3_client = boto3.client("s3", region_name=region)
        self.sagemaker_session = sagemaker.Session()

        logger.info(f"Initialized workload trainer with bucket: {bucket_name}")

    def prepare_workload_training_data(
        self, db_connection
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Prepare training data for workload prediction

        Args:
            db_connection: Database connection

        Returns:
            Tuple of (train_df, val_df, test_df)
        """
        logger.info("Preparing workload training data")

        cursor = db_connection.cursor()

        # Get resource allocation data
        query = """
            SELECT
                r.project_id,
                r.user_name,
                r.allocated_hours,
                r.capacity,
                r.utilization_rate,
                r.week_start_date,
                COUNT(DISTINCT r2.resource_id) as team_size
            FROM resources r
            LEFT JOIN resources r2 ON r.project_id = r2.project_id
                AND r.week_start_date = r2.week_start_date
            GROUP BY r.resource_id, r.project_id, r.user_name, r.allocated_hours,
                     r.capacity, r.utilization_rate, r.week_start_date
            ORDER BY r.week_start_date DESC
        """

        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        cursor.close()

        df = pd.DataFrame(rows, columns=columns)

        if df.empty:
            logger.warning("No resource data found")
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        # Convert Decimal to float
        from decimal import Decimal

        for col in ["allocated_hours", "capacity", "utilization_rate"]:
            if col in df.columns:
                df[col] = df[col].apply(
                    lambda x: float(x) if isinstance(x, Decimal) else x
                )

        # Engineer features
        features_list = []

        for project_id in df["project_id"].unique():
            project_data = df[df["project_id"] == project_id]

            for week in project_data["week_start_date"].unique():
                week_data = project_data[project_data["week_start_date"] == week]

                # Calculate workload variance
                utilizations = week_data["utilization_rate"].values
                workload_variance = np.var(utilizations) if len(utilizations) > 1 else 0

                # Calculate imbalance score (0-100, higher = more imbalanced)
                if len(utilizations) > 1:
                    max_util = np.max(utilizations)
                    min_util = np.min(utilizations)
                    imbalance_score = (max_util - min_util) * 100
                else:
                    imbalance_score = 0

                features = {
                    "project_id": str(project_id),
                    "week_start_date": week,
                    "team_size": int(week_data["team_size"].iloc[0]),
                    "avg_utilization": np.mean(utilizations),
                    "max_utilization": np.max(utilizations),
                    "min_utilization": np.min(utilizations),
                    "std_utilization": np.std(utilizations),
                    "workload_variance": workload_variance,
                    "imbalance_score": imbalance_score,
                    "overallocated_count": int(np.sum(utilizations > 100)),
                    "underallocated_count": int(np.sum(utilizations < 50)),
                }

                features_list.append(features)

        features_df = pd.DataFrame(features_list)

        # Split data
        shuffled = features_df.sample(frac=1, random_state=42).reset_index(drop=True)
        n = len(shuffled)
        train_end = int(n * 0.7)
        val_end = train_end + int(n * 0.15)

        train_df = shuffled[:train_end]
        val_df = shuffled[train_end:val_end]
        test_df = shuffled[val_end:]

        logger.info(
            f"Prepared workload data: train={len(train_df)}, val={len(val_df)}, test={len(test_df)}"
        )

        return train_df, val_df, test_df

    def create_training_script(self) -> str:
        """
        Create sklearn training script for SageMaker

        Returns:
            Path to training script
        """
        script_content = """
import argparse
import os
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import joblib
import json

if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    # Hyperparameters
    parser.add_argument('--n-estimators', type=int, default=100)
    parser.add_argument('--max-depth', type=int, default=10)
    parser.add_argument('--min-samples-split', type=int, default=5)
    parser.add_argument('--min-samples-leaf', type=int, default=2)

    # SageMaker parameters
    parser.add_argument('--model-dir', type=str, default=os.environ.get('SM_MODEL_DIR'))
    parser.add_argument('--train', type=str, default=os.environ.get('SM_CHANNEL_TRAIN'))
    parser.add_argument('--validation', type=str, default=os.environ.get('SM_CHANNEL_VALIDATION'))

    args = parser.parse_args()

    # Load training data
    train_df = pd.read_csv(os.path.join(args.train, 'train.csv'))

    # Prepare features and target
    feature_cols = ['team_size', 'avg_utilization', 'max_utilization', 'min_utilization',
                   'std_utilization', 'overallocated_count', 'underallocated_count']

    X_train = train_df[feature_cols]
    y_train = train_df['imbalance_score']

    # Train model
    model = RandomForestRegressor(
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        min_samples_split=args.min_samples_split,
        min_samples_leaf=args.min_samples_leaf,
        random_state=42
    )

    model.fit(X_train, y_train)

    # Evaluate on validation set if available
    if args.validation:
        val_df = pd.read_csv(os.path.join(args.validation, 'validation.csv'))
        X_val = val_df[feature_cols]
        y_val = val_df['imbalance_score']

        y_pred = model.predict(X_val)

        mae = mean_absolute_error(y_val, y_pred)
        rmse = np.sqrt(mean_squared_error(y_val, y_pred))
        r2 = r2_score(y_val, y_pred)

        print(f'Validation MAE: {mae}')
        print(f'Validation RMSE: {rmse}')
        print(f'Validation R2: {r2}')

    # Save model
    joblib.dump(model, os.path.join(args.model_dir, 'model.joblib'))

    # Save feature names
    with open(os.path.join(args.model_dir, 'feature_names.json'), 'w') as f:
        json.dump(feature_cols, f)
"""

        script_path = "/tmp/train_workload.py"
        with open(script_path, "w") as f:
            f.write(script_content)

        return script_path

    def train_workload_model(
        self, train_df: pd.DataFrame, val_df: pd.DataFrame
    ) -> sagemaker.estimator.Estimator:
        """
        Train Random Forest model for workload prediction

        Args:
            train_df: Training DataFrame
            val_df: Validation DataFrame

        Returns:
            Trained estimator
        """
        logger.info("Training workload imbalance model")

        # Upload training data
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        # Save training data
        train_path = f"/tmp/train_workload.csv"
        train_df.to_csv(train_path, index=False)

        train_s3_key = f"training-data/workload/{timestamp}/train.csv"
        self.s3_client.upload_file(train_path, self.bucket_name, train_s3_key)
        train_s3_uri = f"s3://{self.bucket_name}/{train_s3_key}"

        # Save validation data
        val_path = f"/tmp/val_workload.csv"
        val_df.to_csv(val_path, index=False)

        val_s3_key = f"training-data/workload/{timestamp}/validation.csv"
        self.s3_client.upload_file(val_path, self.bucket_name, val_s3_key)
        val_s3_uri = f"s3://{self.bucket_name}/{val_s3_key}"

        # Create training script
        script_path = self.create_training_script()

        # Create SKLearn estimator
        sklearn_estimator = SKLearn(
            entry_point=script_path,
            role=self.role_arn,
            instance_type="ml.m5.xlarge",
            instance_count=1,
            framework_version="1.0-1",
            py_version="py3",
            output_path=f"s3://{self.bucket_name}/models/workload-prediction/{timestamp}",
            sagemaker_session=self.sagemaker_session,
            hyperparameters={
                "n-estimators": 100,
                "max-depth": 10,
                "min-samples-split": 5,
                "min-samples-leaf": 2,
            },
        )

        # Train model
        logger.info("Starting training job...")
        sklearn_estimator.fit(
            {"train": train_s3_uri, "validation": val_s3_uri}, wait=True
        )

        logger.info("Workload model training complete")

        # Clean up
        os.remove(train_path)
        os.remove(val_path)
        os.remove(script_path)

        return sklearn_estimator


class WorkloadPredictionService:
    """Service for workload imbalance predictions"""

    def __init__(self, endpoint_name: str):
        """
        Initialize workload prediction service

        Args:
            endpoint_name: SageMaker endpoint name
        """
        self.endpoint_name = endpoint_name
        self.sagemaker_runtime = boto3.client("sagemaker-runtime")

    def predict_workload_imbalance(
        self, project_id: str, db_connection
    ) -> Dict[str, Any]:
        """
        Predict workload imbalance for a project

        Args:
            project_id: Project ID
            db_connection: Database connection

        Returns:
            Prediction result with recommendations
        """
        logger.info(f"Predicting workload imbalance for project: {project_id}")

        cursor = db_connection.cursor()

        # Get current resource allocation
        cursor.execute(
            """
            SELECT
                user_name,
                allocated_hours,
                capacity,
                utilization_rate
            FROM resources
            WHERE project_id = %s
            AND week_start_date = (
                SELECT MAX(week_start_date)
                FROM resources
                WHERE project_id = %s
            )
        """,
            (project_id, project_id),
        )

        resources = cursor.fetchall()
        cursor.close()

        if not resources:
            logger.warning(f"No resource data found for project: {project_id}")
            return {
                "project_id": project_id,
                "imbalance_score": 0,
                "confidence_score": 0,
                "message": "No resource data available",
            }

        # Calculate features
        from decimal import Decimal

        utilizations = [
            float(r[3]) if isinstance(r[3], Decimal) else r[3] for r in resources
        ]

        team_size = len(resources)
        avg_utilization = np.mean(utilizations)
        max_utilization = np.max(utilizations)
        min_utilization = np.min(utilizations)
        std_utilization = np.std(utilizations)
        overallocated_count = int(np.sum(np.array(utilizations) > 100))
        underallocated_count = int(np.sum(np.array(utilizations) < 50))

        features = {
            "team_size": team_size,
            "avg_utilization": avg_utilization,
            "max_utilization": max_utilization,
            "min_utilization": min_utilization,
            "std_utilization": std_utilization,
            "overallocated_count": overallocated_count,
            "underallocated_count": underallocated_count,
        }

        # Invoke endpoint
        feature_values = [str(features[k]) for k in sorted(features.keys())]
        payload = ",".join(feature_values)

        try:
            response = self.sagemaker_runtime.invoke_endpoint(
                EndpointName=self.endpoint_name, ContentType="text/csv", Body=payload
            )

            imbalance_score = float(response["Body"].read().decode())

        except Exception as e:
            logger.error(f"Error invoking endpoint: {e}")
            # Fallback to simple calculation
            imbalance_score = (max_utilization - min_utilization) * 100

        # Identify overallocated and underallocated resources
        overallocated = []
        underallocated = []

        for resource in resources:
            user_name = resource[0]
            utilization = (
                float(resource[3]) if isinstance(resource[3], Decimal) else resource[3]
            )

            if utilization > 100:
                overallocated.append(
                    {
                        "user_name": user_name,
                        "predicted_utilization": utilization,
                        "current_utilization": utilization,
                        "variance": utilization - avg_utilization,
                    }
                )
            elif utilization < 50:
                underallocated.append(
                    {
                        "user_name": user_name,
                        "predicted_utilization": utilization,
                        "current_utilization": utilization,
                        "variance": utilization - avg_utilization,
                    }
                )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            overallocated, underallocated, imbalance_score
        )

        # Calculate confidence
        confidence_score = min(
            0.95, team_size / 10
        )  # Higher confidence with more team members

        result = {
            "project_id": project_id,
            "imbalance_score": round(imbalance_score, 2),
            "confidence_score": round(confidence_score, 2),
            "overallocated_resources": overallocated,
            "underallocated_resources": underallocated,
            "recommendations": recommendations,
            "generated_at": datetime.utcnow().isoformat(),
        }

        logger.info(f"Workload prediction complete: imbalance_score={imbalance_score}")

        return result

    def _generate_recommendations(
        self,
        overallocated: List[Dict],
        underallocated: List[Dict],
        imbalance_score: float,
    ) -> List[str]:
        """Generate workload rebalancing recommendations"""
        recommendations = []

        if imbalance_score > 40:
            recommendations.append(
                "High workload imbalance detected - immediate rebalancing recommended"
            )

        if overallocated:
            recommendations.append(
                f"Redistribute work from {len(overallocated)} overallocated team member(s)"
            )

        if underallocated:
            recommendations.append(
                f"Assign additional work to {len(underallocated)} underallocated team member(s)"
            )

        if overallocated and underallocated:
            recommendations.append(
                "Consider moving tasks from overallocated to underallocated team members"
            )

        if not recommendations:
            recommendations.append("Workload is well balanced - no action needed")

        return recommendations
