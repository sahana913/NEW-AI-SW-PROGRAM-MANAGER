"""
Script to train delay prediction models using SageMaker
"""

import os
import sys
import logging
import argparse
import pandas as pd
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.prediction.model_training import DelayPredictionModelTrainer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main function to train models"""
    parser = argparse.ArgumentParser(description='Train delay prediction models')
    parser.add_argument('--data-dir', type=str, required=True,
                       help='Directory containing training data (train.csv, val.csv, test.csv)')
    parser.add_argument('--bucket', type=str, required=True,
                       help='S3 bucket for model artifacts')
    parser.add_argument('--role-arn', type=str,
                       help='IAM role ARN for SageMaker')
    parser.add_argument('--region', type=str, default='us-east-1',
                       help='AWS region')
    
    args = parser.parse_args()
    
    logger.info("Starting model training")
    logger.info(f"Data directory: {args.data_dir}")
    logger.info(f"S3 bucket: {args.bucket}")
    logger.info(f"Region: {args.region}")
    
    # Load training data
    data_path = Path(args.data_dir)
    
    try:
        train_df = pd.read_csv(data_path / 'train.csv')
        val_df = pd.read_csv(data_path / 'validation.csv')
        test_df = pd.read_csv(data_path / 'test.csv')
        
        logger.info(f"Loaded training data: train={len(train_df)}, val={len(val_df)}, test={len(test_df)}")
        
    except Exception as e:
        logger.error(f"Failed to load training data: {e}")
        return 1
    
    # Initialize trainer
    try:
        trainer = DelayPredictionModelTrainer(
            bucket_name=args.bucket,
            role_arn=args.role_arn,
            region=args.region
        )
    except Exception as e:
        logger.error(f"Failed to initialize trainer: {e}")
        return 1
    
    # Train models
    try:
        results = trainer.train_models(train_df, val_df, test_df)
        
        logger.info("Training complete!")
        logger.info(f"Classifier model: {results['classifier'].model_data}")
        if results['regressor']:
            logger.info(f"Regressor model: {results['regressor'].model_data}")
        logger.info(f"Metadata: {results['metadata']}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Error during training: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
