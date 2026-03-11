"""
Model Training Module

Trains delay prediction models using SageMaker with XGBoost algorithm.
"""

import logging
import boto3
import sagemaker
from sagemaker import get_execution_role
from sagemaker.estimator import Estimator
from sagemaker.inputs import TrainingInput
import pandas as pd
import json
from typing import Dict, Any, Optional
from datetime import datetime
import os

logger = logging.getLogger(__name__)


class DelayPredictionModelTrainer:
    """Trains delay prediction models using SageMaker"""
    
    def __init__(self, 
                 bucket_name: str,
                 role_arn: Optional[str] = None,
                 region: str = 'us-east-1'):
        """
        Initialize model trainer
        
        Args:
            bucket_name: S3 bucket for model artifacts
            role_arn: IAM role ARN for SageMaker (optional, will use execution role if not provided)
            region: AWS region
        """
        self.bucket_name = bucket_name
        self.region = region
        self.s3_client = boto3.client('s3', region_name=region)
        self.sagemaker_session = sagemaker.Session()
        
        # Get execution role
        if role_arn:
            self.role = role_arn
        else:
            try:
                self.role = get_execution_role()
            except Exception as e:
                logger.warning(f"Could not get execution role: {e}. Using environment variable.")
                self.role = os.environ.get('SAGEMAKER_ROLE_ARN', '')
        
        logger.info(f"Initialized model trainer with bucket: {bucket_name}, region: {region}")
    
    def upload_training_data_to_s3(self, 
                                   train_df: pd.DataFrame,
                                   val_df: pd.DataFrame,
                                   test_df: pd.DataFrame,
                                   prefix: str = 'training-data') -> Dict[str, str]:
        """
        Upload training data to S3
        
        Args:
            train_df: Training DataFrame
            val_df: Validation DataFrame
            test_df: Test DataFrame
            prefix: S3 prefix for data
            
        Returns:
            Dictionary with S3 URIs for each dataset
        """
        logger.info("Uploading training data to S3")
        
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        s3_prefix = f"{prefix}/{timestamp}"
        
        s3_uris = {}
        
        for name, df in [('train', train_df), ('validation', val_df), ('test', test_df)]:
            if df.empty:
                logger.warning(f"Skipping empty {name} dataset")
                continue
            
            # Prepare data for XGBoost (label first, then features)
            # XGBoost expects CSV with no header, label in first column
            feature_cols = [col for col in df.columns if col not in ['project_id', 'tenant_id', 'is_delayed', 'delay_days']]
            
            # For binary classification
            xgboost_df = df[['is_delayed'] + feature_cols].copy()
            
            # Save to local temp file
            local_file = f'/tmp/{name}.csv'
            xgboost_df.to_csv(local_file, header=False, index=False)
            
            # Upload to S3
            s3_key = f"{s3_prefix}/{name}.csv"
            self.s3_client.upload_file(local_file, self.bucket_name, s3_key)
            
            s3_uri = f"s3://{self.bucket_name}/{s3_key}"
            s3_uris[name] = s3_uri
            
            logger.info(f"Uploaded {name} data to {s3_uri}")
            
            # Clean up temp file
            os.remove(local_file)
        
        return s3_uris
    
    def train_binary_classifier(self,
                                train_s3_uri: str,
                                val_s3_uri: str,
                                output_path: str,
                                hyperparameters: Optional[Dict[str, Any]] = None) -> Estimator:
        """
        Train binary classifier for delay prediction
        
        Args:
            train_s3_uri: S3 URI for training data
            val_s3_uri: S3 URI for validation data
            output_path: S3 path for model artifacts
            hyperparameters: Optional hyperparameters for XGBoost
            
        Returns:
            Trained estimator
        """
        logger.info("Training binary classifier for delay prediction")
        
        # Get XGBoost container
        container = sagemaker.image_uris.retrieve(
            framework='xgboost',
            region=self.region,
            version='1.5-1'
        )
        
        # Default hyperparameters
        default_hyperparameters = {
            'objective': 'binary:logistic',
            'eval_metric': 'auc',
            'num_round': 100,
            'max_depth': 5,
            'eta': 0.2,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'min_child_weight': 3,
            'early_stopping_rounds': 10
        }
        
        if hyperparameters:
            default_hyperparameters.update(hyperparameters)
        
        # Create estimator
        estimator = Estimator(
            image_uri=container,
            role=self.role,
            instance_count=1,
            instance_type='ml.m5.xlarge',
            output_path=output_path,
            sagemaker_session=self.sagemaker_session,
            hyperparameters=default_hyperparameters
        )
        
        # Set up training inputs
        train_input = TrainingInput(train_s3_uri, content_type='text/csv')
        val_input = TrainingInput(val_s3_uri, content_type='text/csv')
        
        # Train model
        logger.info("Starting training job...")
        estimator.fit({'train': train_input, 'validation': val_input}, wait=True)
        
        logger.info("Training complete")
        
        return estimator
    
    def train_regressor(self,
                       train_s3_uri: str,
                       val_s3_uri: str,
                       output_path: str,
                       train_df: pd.DataFrame,
                       hyperparameters: Optional[Dict[str, Any]] = None) -> Estimator:
        """
        Train regressor for delay days prediction
        
        Args:
            train_s3_uri: S3 URI for training data
            val_s3_uri: S3 URI for validation data
            output_path: S3 path for model artifacts
            train_df: Training DataFrame (to prepare regression data)
            hyperparameters: Optional hyperparameters for XGBoost
            
        Returns:
            Trained estimator
        """
        logger.info("Training regressor for delay days prediction")
        
        # Prepare regression data (only delayed projects)
        delayed_df = train_df[train_df['is_delayed'] == 1].copy()
        
        if len(delayed_df) < 10:
            logger.warning("Insufficient delayed projects for regression training")
            return None
        
        # Upload regression training data
        feature_cols = [col for col in delayed_df.columns if col not in ['project_id', 'tenant_id', 'is_delayed', 'delay_days']]
        regression_df = delayed_df[['delay_days'] + feature_cols].copy()
        
        # Save and upload
        local_file = '/tmp/train_regression.csv'
        regression_df.to_csv(local_file, header=False, index=False)
        
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        s3_key = f"training-data/{timestamp}/train_regression.csv"
        self.s3_client.upload_file(local_file, self.bucket_name, s3_key)
        regression_train_uri = f"s3://{self.bucket_name}/{s3_key}"
        
        os.remove(local_file)
        
        # Get XGBoost container
        container = sagemaker.image_uris.retrieve(
            framework='xgboost',
            region=self.region,
            version='1.5-1'
        )
        
        # Default hyperparameters for regression
        default_hyperparameters = {
            'objective': 'reg:squarederror',
            'eval_metric': 'rmse',
            'num_round': 100,
            'max_depth': 5,
            'eta': 0.2,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'min_child_weight': 3
        }
        
        if hyperparameters:
            default_hyperparameters.update(hyperparameters)
        
        # Create estimator
        estimator = Estimator(
            image_uri=container,
            role=self.role,
            instance_count=1,
            instance_type='ml.m5.xlarge',
            output_path=output_path,
            sagemaker_session=self.sagemaker_session,
            hyperparameters=default_hyperparameters
        )
        
        # Train model
        train_input = TrainingInput(regression_train_uri, content_type='text/csv')
        
        logger.info("Starting regression training job...")
        estimator.fit({'train': train_input}, wait=True)
        
        logger.info("Regression training complete")
        
        return estimator
    
    def evaluate_model(self, 
                      estimator: Estimator,
                      test_s3_uri: str,
                      test_df: pd.DataFrame,
                      model_type: str = 'classifier') -> Dict[str, float]:
        """
        Evaluate model performance
        
        Args:
            estimator: Trained estimator
            test_s3_uri: S3 URI for test data
            test_df: Test DataFrame
            model_type: 'classifier' or 'regressor'
            
        Returns:
            Dictionary with evaluation metrics
        """
        logger.info(f"Evaluating {model_type} model")
        
        # For simplicity, we'll use the training metrics from SageMaker
        # In production, you'd deploy the model and run predictions on test set
        
        training_job_name = estimator.latest_training_job.name
        sm_client = boto3.client('sagemaker', region_name=self.region)
        
        try:
            job_description = sm_client.describe_training_job(TrainingJobName=training_job_name)
            final_metrics = job_description.get('FinalMetricDataList', [])
            
            metrics = {}
            for metric in final_metrics:
                metrics[metric['MetricName']] = metric['Value']
            
            logger.info(f"Model metrics: {metrics}")
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error retrieving metrics: {e}")
            return {}
    
    def save_model_metadata(self,
                           classifier_estimator: Estimator,
                           regressor_estimator: Optional[Estimator],
                           classifier_metrics: Dict[str, float],
                           regressor_metrics: Dict[str, float],
                           output_path: str):
        """
        Save model metadata
        
        Args:
            classifier_estimator: Trained classifier
            regressor_estimator: Trained regressor (optional)
            classifier_metrics: Classifier metrics
            regressor_metrics: Regressor metrics
            output_path: S3 path for metadata
        """
        logger.info("Saving model metadata")
        
        metadata = {
            'timestamp': datetime.now().isoformat(),
            'classifier': {
                'training_job_name': classifier_estimator.latest_training_job.name,
                'model_data': classifier_estimator.model_data,
                'metrics': classifier_metrics
            }
        }
        
        if regressor_estimator:
            metadata['regressor'] = {
                'training_job_name': regressor_estimator.latest_training_job.name,
                'model_data': regressor_estimator.model_data,
                'metrics': regressor_metrics
            }
        
        # Save metadata to S3
        metadata_key = f"{output_path.replace(f's3://{self.bucket_name}/', '')}/metadata.json"
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=metadata_key,
            Body=json.dumps(metadata, indent=2)
        )
        
        logger.info(f"Saved model metadata to s3://{self.bucket_name}/{metadata_key}")
        
        return metadata
    
    def train_models(self,
                    train_df: pd.DataFrame,
                    val_df: pd.DataFrame,
                    test_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Complete training pipeline for both classifier and regressor
        
        Args:
            train_df: Training DataFrame
            val_df: Validation DataFrame
            test_df: Test DataFrame
            
        Returns:
            Dictionary with trained models and metadata
        """
        logger.info("Starting complete model training pipeline")
        
        # Upload data to S3
        s3_uris = self.upload_training_data_to_s3(train_df, val_df, test_df)
        
        # Define output path
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        output_path = f"s3://{self.bucket_name}/models/delay-prediction/{timestamp}"
        
        # Train binary classifier
        classifier = self.train_binary_classifier(
            s3_uris['train'],
            s3_uris['validation'],
            f"{output_path}/classifier"
        )
        
        classifier_metrics = self.evaluate_model(
            classifier,
            s3_uris.get('test', ''),
            test_df,
            'classifier'
        )
        
        # Train regressor
        regressor = self.train_regressor(
            s3_uris['train'],
            s3_uris.get('validation', ''),
            f"{output_path}/regressor",
            train_df
        )
        
        regressor_metrics = {}
        if regressor:
            regressor_metrics = self.evaluate_model(
                regressor,
                s3_uris.get('test', ''),
                test_df,
                'regressor'
            )
        
        # Save metadata
        metadata = self.save_model_metadata(
            classifier,
            regressor,
            classifier_metrics,
            regressor_metrics,
            output_path
        )
        
        logger.info("Model training pipeline complete")
        
        return {
            'classifier': classifier,
            'regressor': regressor,
            'metadata': metadata,
            'output_path': output_path
        }
