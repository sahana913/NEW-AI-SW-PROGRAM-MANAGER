# Bugfix Requirements Document

## Introduction

This bugfix addresses critical production readiness issues in the AI SW Program Manager backend that prevent real user data from being processed and stored. The system currently falls back to demo data instead of processing uploaded documents and generating predictions from actual project data. This affects the core value proposition of the application - providing AI-powered insights based on real project documents and metrics.

The bug manifests across multiple subsystems including document upload/processing, data persistence, ML predictions, API configuration, IAM permissions, environment variables, and monitoring. Users can upload documents but they are never processed, predictions are not generated, and the dashboard shows demo data instead of real project insights.

## Bug Analysis

### Current Behavior (Defect)

#### 1. Document Upload and Processing Flow

1.1 WHEN a user uploads a document through the frontend THEN the document is stored in S3 but no S3 event trigger is configured to invoke the document processing Lambda

1.2 WHEN a document is uploaded to S3 THEN the document processing Lambda is never invoked because the S3 event notification is not configured in the storage stack

1.3 WHEN a document is uploaded THEN the document status remains "PENDING_UPLOAD" indefinitely because the processing Lambda never updates it to "UPLOADED"

1.4 WHEN document processing fails THEN no error notification is sent to users because the NOTIFICATION_TOPIC_ARN environment variable is not configured

#### 2. Data Persistence and DynamoDB Configuration

2.1 WHEN the API Gateway stack is deployed THEN the project management DynamoDB tables (PROJECTS, SPRINTS, BACKLOG_ITEMS, MILESTONES, RESOURCES, DEPENDENCIES, HEALTH_SCORES) are not passed as environment variables to Lambda functions

2.2 WHEN Lambda functions attempt to write project data THEN batch write operations fail silently because the data storage handler is not integrated with the infrastructure

2.3 WHEN batch write operations fail due to throttling THEN no retry logic is applied, resulting in data loss

2.4 WHEN the dashboard Lambda queries project data THEN it falls back to demo data because the DynamoDB tables are not accessible

#### 3. Prediction and ML Pipeline

3.1 WHEN predictions are requested THEN the system uses heuristic fallback scoring because SageMaker endpoint environment variables (DELAY_CLASSIFIER_ENDPOINT, DELAY_REGRESSOR_ENDPOINT, WORKLOAD_ENDPOINT) are not configured

3.2 WHEN feature extraction fails during prediction THEN the error is caught silently and neutral features are used, providing no indication to users that predictions are unreliable

3.3 WHEN a document is uploaded THEN no prediction is automatically triggered, requiring manual user action

3.4 WHEN prediction results are generated THEN they are not stored reliably in DynamoDB due to missing table permissions

#### 4. API Gateway Configuration

4.1 WHEN the document upload endpoint is called THEN it fails because the DOCUMENTS_BUCKET environment variable is not set in the Lambda function

4.2 WHEN dashboard endpoints encounter errors THEN they return demo data instead of proper error responses, masking infrastructure issues

4.3 WHEN the prediction history endpoint is queried THEN it uses an inefficient fallback query that scans the entire tenant partition instead of using the ProjectTypeIndex GSI

4.4 WHEN S3 pre-signed URLs are generated for document upload THEN CORS headers are not properly configured, causing browser upload failures

#### 5. Lambda IAM Permissions

5.1 WHEN the document upload Lambda attempts to write to S3 THEN it fails because the S3 bucket ARN is hardcoded instead of using the actual bucket reference

5.2 WHEN the prediction Lambda attempts to read project data THEN it fails because it lacks DynamoDB read permissions for PROJECTS, SPRINTS, BACKLOG_ITEMS, MILESTONES, RESOURCES, DEPENDENCIES tables

5.3 WHEN the dashboard Lambda attempts to read health scores THEN it fails because it lacks read permissions for HEALTH_SCORES, SPRINTS, MILESTONES, RESOURCES tables

5.4 WHEN the document processing Lambda attempts to update document status THEN it fails because it lacks DynamoDB write permissions

5.5 WHEN the report generation Lambda attempts to read project data THEN it fails because it lacks read permissions for project management tables

#### 6. Environment Variable Configuration

6.1 WHEN Lambda functions are deployed THEN SageMaker endpoint names are not configured, causing predictions to use fallback heuristics

6.2 WHEN Lambda functions are deployed THEN the SNS topic ARN for notifications is not configured, preventing error alerts

6.3 WHEN Lambda functions are deployed THEN the cache table name is not configured, preventing caching functionality

6.4 WHEN Lambda functions are deployed THEN table name environment variables are inconsistent (some use _TABLE_NAME suffix, others don't)

#### 7. CloudWatch Monitoring and Alerting

7.1 WHEN data persistence operations fail THEN no CloudWatch alarm is triggered because error metrics are not configured

7.2 WHEN prediction generation fails THEN no alert is sent because prediction failure metrics are not monitored

7.3 WHEN dashboard data becomes stale THEN no monitoring detects the issue because data freshness metrics are not tracked

#### 8. Frontend-Backend Integration

8.1 WHEN a document upload completes THEN the frontend does not automatically refresh predictions, requiring manual user action

8.2 WHEN the frontend makes prediction requests THEN it uses a hardcoded project ID instead of the active project context

8.3 WHEN the frontend receives a 401 error THEN it immediately signs out the user without attempting token refresh

8.4 WHEN the frontend attempts to render prediction charts THEN it crashes if mock data definitions are missing instead of showing an empty state

### Expected Behavior (Correct)

#### 1. Document Upload and Processing Flow

2.1 WHEN a user uploads a document through the frontend THEN an S3 event notification SHALL trigger the document processing Lambda automatically

2.2 WHEN a document is uploaded to S3 THEN the S3 bucket SHALL have an event notification configured to invoke the document processing Lambda with the object key

2.3 WHEN the document processing Lambda is invoked THEN it SHALL update the document status from "PENDING_UPLOAD" to "UPLOADED" in DynamoDB

2.4 WHEN document processing fails THEN the system SHALL send an SNS notification to the configured NOTIFICATION_TOPIC_ARN with error details

#### 2. Data Persistence and DynamoDB Configuration

2.5 WHEN the API Gateway stack is deployed THEN all project management DynamoDB table names SHALL be passed as environment variables to Lambda functions

2.6 WHEN Lambda functions write project data THEN the data storage handler SHALL successfully write to DynamoDB tables with proper error handling

2.7 WHEN batch write operations encounter throttling THEN the system SHALL retry with exponential backoff up to 5 times before failing

2.8 WHEN the dashboard Lambda queries project data THEN it SHALL return real data from DynamoDB tables instead of falling back to demo data

#### 3. Prediction and ML Pipeline

2.9 WHEN predictions are requested THEN the system SHALL use configured SageMaker endpoints if available, falling back to heuristics only when endpoints are not configured

2.10 WHEN feature extraction fails during prediction THEN the system SHALL log a warning and return an error response indicating predictions are unavailable

2.11 WHEN a document upload completes successfully THEN the system SHALL automatically trigger a prediction generation for the associated project

2.12 WHEN prediction results are generated THEN they SHALL be stored in the Predictions DynamoDB table with proper permissions

#### 4. API Gateway Configuration

2.13 WHEN the document upload endpoint is called THEN it SHALL have access to the DOCUMENTS_BUCKET environment variable pointing to the actual S3 bucket

2.14 WHEN dashboard endpoints encounter errors THEN they SHALL return proper HTTP error responses (500, 503) instead of demo data

2.15 WHEN the prediction history endpoint is queried THEN it SHALL use the ProjectTypeIndex GSI for efficient queries

2.16 WHEN S3 pre-signed URLs are generated THEN the S3 bucket SHALL have CORS configuration allowing PUT and GET methods from the frontend origin

#### 5. Lambda IAM Permissions

2.17 WHEN the document upload Lambda is deployed THEN it SHALL have S3 PutObject and GetObject permissions for the actual documents bucket

2.18 WHEN the prediction Lambda is deployed THEN it SHALL have DynamoDB read permissions for all project management tables

2.19 WHEN the dashboard Lambda is deployed THEN it SHALL have DynamoDB read permissions for HEALTH_SCORES, SPRINTS, MILESTONES, RESOURCES, DEPENDENCIES tables

2.20 WHEN the document processing Lambda is deployed THEN it SHALL have DynamoDB write permissions for the Documents table

2.21 WHEN the report generation Lambda is deployed THEN it SHALL have DynamoDB read permissions for all project management tables

#### 6. Environment Variable Configuration

2.22 WHEN Lambda functions are deployed THEN SageMaker endpoint environment variables SHALL be configured if endpoints exist, or left empty with graceful fallback

2.23 WHEN Lambda functions are deployed THEN the SNS topic ARN SHALL be configured for error notifications

2.24 WHEN Lambda functions are deployed THEN the cache table name SHALL be configured consistently across all functions

2.25 WHEN Lambda functions are deployed THEN all table name environment variables SHALL use consistent naming (with _TABLE_NAME suffix)

#### 7. CloudWatch Monitoring and Alerting

2.26 WHEN data persistence operations fail THEN a CloudWatch alarm SHALL trigger and send an SNS notification

2.27 WHEN prediction generation fails THEN a CloudWatch alarm SHALL trigger with details about the failure

2.28 WHEN dashboard data has not been updated in 24 hours THEN a CloudWatch alarm SHALL trigger indicating stale data

#### 8. Frontend-Backend Integration

2.29 WHEN a document upload completes successfully THEN the frontend SHALL automatically trigger a prediction refresh for the project

2.30 WHEN the frontend makes prediction requests THEN it SHALL use the currently active project ID from application state

2.31 WHEN the frontend receives a 401 error THEN it SHALL attempt token refresh once before signing out the user

2.32 WHEN the frontend renders prediction charts with no data THEN it SHALL display an empty state message instead of crashing

### Unchanged Behavior (Regression Prevention)

#### 3. Authentication and Authorization

3.1 WHEN users authenticate with Cognito THEN the system SHALL CONTINUE TO validate JWT tokens using the Lambda authorizer

3.2 WHEN API requests are made THEN the system SHALL CONTINUE TO enforce tenant isolation through the authorizer context

3.3 WHEN unauthorized requests are made THEN the system SHALL CONTINUE TO return 401/403 responses with proper CORS headers

#### 4. Existing Document Upload Flow

3.4 WHEN users upload documents through the pre-signed URL flow THEN the system SHALL CONTINUE TO generate pre-signed URLs with 15-minute expiration

3.5 WHEN documents are uploaded THEN the system SHALL CONTINUE TO validate file format (PDF, DOCX, TXT) and size (max 50MB)

3.6 WHEN document metadata is stored THEN the system SHALL CONTINUE TO use tenant-specific S3 key prefixes for isolation

#### 5. Existing Prediction Logic

3.7 WHEN predictions use heuristic fallback THEN the system SHALL CONTINUE TO calculate scores based on velocity trend, backlog ratio, delayed milestones, and blocking dependencies

3.8 WHEN prediction confidence is calculated THEN the system SHALL CONTINUE TO base it on feature completeness

3.9 WHEN high-probability delay predictions are generated THEN the system SHALL CONTINUE TO create risk alerts in the Risks table

#### 6. Dashboard Data Aggregation

3.10 WHEN dashboard overview is requested THEN the system SHALL CONTINUE TO aggregate project summaries, portfolio health, recent risks, and upcoming milestones

3.11 WHEN RAG status is determined THEN the system SHALL CONTINUE TO use thresholds: GREEN (≥80), AMBER (60-79), RED (<60)

3.12 WHEN health score trends are calculated THEN the system SHALL CONTINUE TO compare the last 3 health scores with ±5 point threshold

#### 7. API Gateway Rate Limiting

3.13 WHEN API requests exceed rate limits THEN the system SHALL CONTINUE TO throttle requests at 1000 req/s with 2000 burst capacity

3.14 WHEN usage plan quotas are exceeded THEN the system SHALL CONTINUE TO reject requests with 429 status

#### 8. Lambda Function Configuration

3.15 WHEN Lambda functions are deployed THEN the system SHALL CONTINUE TO use optimized memory configurations from MEMORY_CONFIG

3.16 WHEN Lambda functions execute THEN the system SHALL CONTINUE TO have X-Ray tracing enabled

3.17 WHEN Lambda functions are invoked THEN the system SHALL CONTINUE TO use the common, data_processing, and ai_ml Lambda layers

#### 9. Error Handling and Logging

3.18 WHEN errors occur in Lambda functions THEN the system SHALL CONTINUE TO log errors with structured logging using the shared logger

3.19 WHEN validation errors occur THEN the system SHALL CONTINUE TO return 400 responses with error details

3.20 WHEN internal errors occur THEN the system SHALL CONTINUE TO return 500 responses without exposing internal details

#### 10. DynamoDB Data Model

3.21 WHEN project data is stored THEN the system SHALL CONTINUE TO use the single-table design with PK/SK pattern

3.22 WHEN queries are performed THEN the system SHALL CONTINUE TO use GSI indexes for efficient access patterns

3.23 WHEN numeric values are stored THEN the system SHALL CONTINUE TO convert floats to Decimal for DynamoDB compatibility
