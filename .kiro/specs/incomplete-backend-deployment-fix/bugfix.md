# Bugfix Requirements Document

## Introduction

The AI SW Program Manager frontend is experiencing widespread 500 errors because the backend Lambda functions are not fully deployed to AWS. Investigation reveals that only 3 Lambda functions are currently deployed (Authorizer, Upload URL Lambda, and VPC Custom function), while the frontend expects approximately 20 endpoints for various services including dashboard, risks, predictions, health scores, documents, reports, and semantic search.

The root cause is that the CDK infrastructure code in `infrastructure/stacks/api_gateway_stack.py` only creates and deploys 10 Lambda functions, leaving 18+ service directories in the `src/` folder without corresponding Lambda deployments. This results in API Gateway returning 500 errors for all missing endpoints.

**Impact**: The application is effectively non-functional for end users, as all major features (dashboard, risk detection, predictions, document management, reports) are unavailable.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the frontend makes API calls to `/dashboard/overview`, `/risks`, `/predictions`, `/health-score`, `/documents`, `/reports`, or `/semantic-search` endpoints THEN the system returns "Request failed with status code 500" errors

1.2 WHEN the CDK infrastructure is deployed THEN the system only creates Lambda functions for 10 services (user_management, jira_integration, azure_devops, risk_detection, prediction, document_upload, document_intelligence, semantic_search, report_generation, dashboard)

1.3 WHEN the CDK infrastructure is deployed THEN the system does NOT create Lambda functions for 18+ services that have handler.py files in the src/ directory (health_score, data_ingestion, data_validation, rag_status, analysis_trigger, audit_logging, data_storage, database_maintenance, document_processing, email_distribution, pdf_export, report_scheduling, security_monitoring, etc.)

1.4 WHEN API Gateway receives requests for endpoints backed by missing Lambda functions THEN the system returns 500 errors instead of routing to the appropriate Lambda handler

1.5 WHEN the frontend attempts to load dashboard data THEN the system fails because the dashboard Lambda cannot retrieve data from missing health_score and other dependent services

### Expected Behavior (Correct)

2.1 WHEN the frontend makes API calls to any backend endpoint THEN the system SHALL route the request to the appropriate deployed Lambda function and return a valid response (200, 400, 404, etc., but not 500 due to missing infrastructure)

2.2 WHEN the CDK infrastructure is deployed THEN the system SHALL create Lambda functions for ALL services in the src/ directory that have handler.py files with lambda_handler functions

2.3 WHEN the CDK infrastructure is deployed THEN the system SHALL create API Gateway routes for all required endpoints: `/dashboard/*`, `/risks/*`, `/predictions/*`, `/health-score/*`, `/documents/*`, `/reports/*`, `/semantic-search/*`, `/data-ingestion/*`, `/rag-status/*`, and any other service-specific endpoints

2.4 WHEN API Gateway receives requests for any configured endpoint THEN the system SHALL route to the corresponding Lambda function without returning 500 errors due to missing infrastructure

2.5 WHEN the dashboard Lambda needs data from dependent services (health_score, rag_status, etc.) THEN the system SHALL successfully invoke those Lambda functions or query their DynamoDB tables

2.6 WHEN the CDK infrastructure is deployed THEN the system SHALL grant appropriate DynamoDB table permissions to all Lambda functions that need to read/write project management data (projects, sprints, backlog_items, milestones, resources, dependencies, health_scores)

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the 3 existing Lambda functions (Authorizer, Upload URL Lambda, VPC Custom function) are deployed THEN the system SHALL CONTINUE TO function correctly without any changes to their configuration or behavior

3.2 WHEN the frontend uses Cognito authentication THEN the system SHALL CONTINUE TO authenticate users through the existing Authorizer Lambda without any changes to the authentication flow

3.3 WHEN the frontend has fallback logic to use demo data THEN the system SHALL CONTINUE TO fall back to demo data when backend services are unavailable (for graceful degradation)

3.4 WHEN API Gateway CORS configuration is applied THEN the system SHALL CONTINUE TO allow cross-origin requests with the same headers and methods as currently configured

3.5 WHEN Lambda functions access DynamoDB tables that are already deployed (users, integrations, risks, predictions, reports, documents) THEN the system SHALL CONTINUE TO read/write data to these tables without any schema or permission changes

3.6 WHEN the existing 10 Lambda functions are invoked THEN the system SHALL CONTINUE TO execute with the same memory, timeout, and environment variable configurations

3.7 WHEN CloudWatch alarms are configured for existing Lambda functions THEN the system SHALL CONTINUE TO monitor and alert on the same metrics (throttles, errors, latency)
