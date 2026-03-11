# Prediction Service

This module provides ML-based prediction capabilities for project delays and workload imbalances using Amazon SageMaker.

## Components

### 1. Training Data Preparation (`training_data_preparation.py`)
- Extracts historical project data from RDS
- Engineers features from sprint velocity, backlog metrics, milestone completion, and dependencies
- Labels data with actual delay outcomes
- Splits data into training, validation, and test sets

**Usage:**
```bash
python src/prediction/prepare_data.py --tenant-id <tenant_id> --output-dir ./training_data
```

### 2. Model Training (`model_training.py`)
- Trains XGBoost binary classifier for delay prediction (delayed/on-time)
- Trains XGBoost regressor for delay days estimation
- Evaluates model performance (precision, recall, F1, RMSE)
- Stores model artifacts in S3

**Usage:**
```bash
python src/prediction/train_model.py \
  --data-dir ./training_data \
  --bucket my-model-bucket \
  --role-arn arn:aws:iam::123456789012:role/SageMakerRole \
  --region us-east-1
```

### 3. Model Deployment (`model_deployment.py`)
- Deploys trained models to SageMaker real-time endpoints
- Configures auto-scaling (min: 1, max: 3 instances)
- Manages endpoint lifecycle (create, update, delete)

**Usage:**
```bash
python src/prediction/deploy_model.py \
  --model-data s3://bucket/path/model.tar.gz \
  --role-arn arn:aws:iam::123456789012:role/SageMakerRole \
  --endpoint-name delay-prediction-endpoint \
  --enable-autoscaling \
  --min-capacity 1 \
  --max-capacity 3
```

### 4. Prediction Lambda Handler (`handler.py`)
- Implements predict_delay endpoint
- Extracts features from current project data
- Invokes SageMaker endpoints for predictions
- Stores predictions in DynamoDB Predictions table
- Generates risk alerts if delay probability > 60%

**API Endpoints:**
- `POST /predictions/delay-probability` - Predict project delay
- `POST /predictions/workload-imbalance` - Predict workload imbalance
- `GET /predictions/history` - Get prediction history

### 5. Workload Prediction (`workload_prediction.py`)
- Trains Random Forest model for workload imbalance prediction
- Identifies overallocated and underallocated team members
- Generates workload rebalancing recommendations

### 6. Model Retraining Workflow (`model_retraining.py`)
- Implements monthly automated model retraining
- Evaluates new model against validation data
- Deploys new model if accuracy improves by 5%
- Maintains model version history in DynamoDB ModelRegistry table

**Triggered by:** EventBridge scheduled rule (monthly)

## Features

### Delay Prediction Features
- `velocity_trend`: Velocity trend over last 4 sprints
- `avg_velocity`: Average velocity
- `velocity_std`: Velocity standard deviation
- `avg_completion_rate`: Average sprint completion rate
- `total_backlog`: Total backlog items
- `open_backlog`: Open backlog items
- `backlog_ratio`: Ratio of open to total backlog
- `avg_backlog_age`: Average age of backlog items
- `total_milestones`: Total milestones
- `completed_milestones`: Completed milestones
- `at_risk_milestones`: At-risk milestones
- `delayed_milestones`: Delayed milestones
- `milestone_completion_rate`: Milestone completion rate
- `avg_milestone_completion`: Average milestone completion percentage
- `total_dependencies`: Total dependencies
- `active_dependencies`: Active dependencies
- `blocking_dependencies`: Blocking dependencies

### Workload Prediction Features
- `team_size`: Number of team members
- `avg_utilization`: Average team utilization
- `max_utilization`: Maximum utilization
- `min_utilization`: Minimum utilization
- `std_utilization`: Utilization standard deviation
- `overallocated_count`: Number of overallocated members
- `underallocated_count`: Number of underallocated members

## DynamoDB Tables

### Predictions Table
```
PK: TENANT#<tenant_id>
SK: PREDICTION#<prediction_id>
Attributes:
  - prediction_id
  - project_id
  - prediction_type (DELAY, WORKLOAD)
  - prediction_value (delay probability or imbalance score)
  - confidence_score
  - factors (array of contributing factors)
  - generated_at
GSI1:
  PK: PROJECT#<project_id>#TYPE#<prediction_type>
  SK: PREDICTION#<generated_at>
```

### ModelRegistry Table
```
PK: MODEL#<model_type>
SK: VERSION#<version_id>
Attributes:
  - version_id
  - model_type (DELAY_CLASSIFIER, DELAY_REGRESSOR, WORKLOAD)
  - model_data (S3 URI)
  - endpoint_name
  - training_job_name
  - metrics (performance metrics)
  - status (DEPLOYED, ARCHIVED)
  - created_at
  - deployed_at
```

## Environment Variables

### Lambda Handler
- `PREDICTIONS_TABLE`: DynamoDB Predictions table name
- `RISKS_TABLE`: DynamoDB Risks table name
- `DELAY_CLASSIFIER_ENDPOINT`: SageMaker endpoint for delay classifier
- `DELAY_REGRESSOR_ENDPOINT`: SageMaker endpoint for delay regressor
- `WORKLOAD_ENDPOINT`: SageMaker endpoint for workload prediction

### Retraining Lambda
- `MODEL_BUCKET`: S3 bucket for model artifacts
- `SAGEMAKER_ROLE_ARN`: IAM role ARN for SageMaker
- `AWS_REGION`: AWS region

## Model Performance Metrics

### Delay Classifier
- **Objective:** Binary classification (delayed/on-time)
- **Algorithm:** XGBoost
- **Metrics:** AUC, Precision, Recall, F1-Score

### Delay Regressor
- **Objective:** Predict delay days
- **Algorithm:** XGBoost
- **Metrics:** RMSE, MAE

### Workload Predictor
- **Objective:** Predict workload imbalance score
- **Algorithm:** Random Forest
- **Metrics:** RMSE, MAE, R²

## Deployment Architecture

```
EventBridge (Data Refresh) → Lambda (Prediction Service)
                                ↓
                          SageMaker Endpoints
                                ↓
                          DynamoDB (Predictions)
                                ↓
                          Risk Alert Generation

EventBridge (Monthly) → Lambda (Retraining)
                          ↓
                    SageMaker Training Jobs
                          ↓
                    Model Evaluation
                          ↓
                    Conditional Deployment
                          ↓
                    DynamoDB (ModelRegistry)
```

## Requirements

See `requirements.txt` for Python dependencies:
- boto3>=1.26.0
- sagemaker>=2.150.0
- pandas>=1.5.0
- numpy>=1.23.0
- psycopg2-binary>=2.9.0

## Testing

Run unit tests:
```bash
pytest tests/test_prediction.py -v
```

## Monitoring

- CloudWatch Logs: All Lambda executions logged
- CloudWatch Metrics: Custom metrics for prediction accuracy
- SageMaker Model Monitor: Track model drift and data quality
- X-Ray: Distributed tracing for prediction requests
