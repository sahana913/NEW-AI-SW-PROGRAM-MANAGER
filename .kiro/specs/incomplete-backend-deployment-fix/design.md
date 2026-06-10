# Incomplete Backend Deployment Fix - Bugfix Design

## Overview

The AI SW Program Manager backend is incomplete because the CDK infrastructure code only deploys 10 Lambda functions out of 28 service directories in the `src/` folder. This causes widespread 500 errors when the frontend attempts to call missing endpoints. The fix involves programmatically discovering all services with `handler.py` files and deploying Lambda functions for each, along with their corresponding API Gateway routes, IAM permissions, and DynamoDB table access.

The approach is to refactor the `_create_lambda_functions()` method in `api_gateway_stack.py` to use a service discovery pattern that automatically creates Lambda functions for all services, rather than manually defining each one. This ensures that as new services are added to the `src/` directory, they are automatically deployed without requiring manual CDK code changes.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug - when a service directory exists in `src/` with a `handler.py` file but no corresponding Lambda function is deployed in the CDK stack
- **Property (P)**: The desired behavior - all services with `handler.py` files should have deployed Lambda functions with API Gateway routes
- **Preservation**: Existing 10 Lambda functions and 3 deployed functions (Authorizer, Upload URL, VPC Custom) must continue to work without changes
- **Service Directory**: A directory in `src/` containing a `handler.py` file with a `lambda_handler` function
- **API Gateway Stack**: The CDK stack in `infrastructure/stacks/api_gateway_stack.py` that creates Lambda functions and API Gateway routes
- **Lambda Configuration**: Memory size, timeout, and environment variables for each Lambda function
- **Service Discovery**: Programmatic pattern to automatically detect and deploy all services in `src/` directory

## Bug Details

### Bug Condition

The bug manifests when a service directory exists in `src/` with a `handler.py` file containing a `lambda_handler` function, but the CDK infrastructure code in `api_gateway_stack.py` does not create a corresponding Lambda function. This results in API Gateway returning 500 errors when the frontend attempts to call endpoints for that service.

**Formal Specification:**
```
FUNCTION isBugCondition(service)
  INPUT: service of type ServiceDirectory
  OUTPUT: boolean
  
  RETURN service.hasHandlerFile() 
         AND service.hasLambdaHandlerFunction()
         AND NOT service.hasDeployedLambdaFunction()
         AND service.name NOT IN ['shared', 'auth', 'authorizer']
END FUNCTION
```

### Examples

- **health_score service**: Has `src/health_score/handler.py` with `calculate_health_score_handler`, `get_health_score_handler`, and `get_health_score_history_handler` functions, but NO Lambda function deployed → API calls to `/health-score/*` return 500 errors
- **rag_status service**: Has `src/rag_status/handler.py` with `calculate_rag_status_handler`, `get_rag_status_handler`, and `get_rag_status_history_handler` functions, but NO Lambda function deployed → API calls to `/rag-status/*` return 500 errors
- **analysis_trigger service**: Has `src/analysis_trigger/handler.py` with `lambda_handler` function, but NO Lambda function deployed → EventBridge cannot trigger analysis workflows
- **data_validation service**: Has `src/data_validation/handler.py` with `lambda_handler` function, but NO Lambda function deployed → Data validation pipeline is broken
- **data_storage service**: Has `src/data_storage/handler.py` with `lambda_handler` function, but NO Lambda function deployed → Data storage operations fail
- **database_maintenance service**: Has `src/database_maintenance/handler.py` with `lambda_handler` function, but NO Lambda function deployed → Database maintenance tasks cannot run
- **document_processing service**: Has `src/document_processing/handler.py` with `lambda_handler` function, but NO Lambda function deployed → S3 upload events cannot trigger document processing
- **email_distribution service**: Has `src/email_distribution/handler.py` with `lambda_handler` function, but NO Lambda function deployed → Email notifications cannot be sent
- **pdf_export service**: Has directory but NO handler.py file → Should NOT be deployed (not a bug condition)
- **report_scheduling service**: Has `src/report_scheduling/handler.py` with multiple handler functions, but NO Lambda function deployed → Scheduled reports cannot be created or managed
- **security_monitoring service**: Has `src/security_monitoring/handler.py` with `lambda_handler` function, but NO Lambda function deployed → Security violation events cannot be processed

**Missing Services (18 total):**
1. health_score
2. rag_status
3. analysis_trigger
4. audit_logging
5. data_validation
6. data_storage
7. database_maintenance
8. document_processing
9. email_distribution
10. report_scheduling
11. security_monitoring
12. auth (has handler but may be internal-only)
13. document_intel (duplicate of document_intelligence?)

**Deployed Services (10 total):**
1. user_management ✓
2. jira_integration ✓
3. azure_devops_integration ✓
4. risk_detection ✓
5. prediction ✓
6. document_upload ✓
7. document_intelligence ✓
8. semantic_search ✓
9. report_generation ✓
10. dashboard ✓

**Special Cases:**
- `authorizer` - Already deployed in AuthStack, not ApiGatewayStack
- `shared` - Library code, not a service
- `data_ingestion` - Empty directory, no handler.py file

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- The 10 existing Lambda functions (user_management, jira_integration, azure_devops, risk_detection, prediction, document_upload, document_intelligence, semantic_search, report_generation, dashboard) must continue to work with the same configuration
- The 3 deployed Lambda functions (Authorizer, Upload URL Lambda, VPC Custom) must continue to work without any changes
- Cognito authentication flow through the Authorizer Lambda must remain unchanged
- API Gateway CORS configuration must remain unchanged
- DynamoDB table permissions for existing Lambda functions must remain unchanged
- CloudWatch alarms for existing Lambda functions must remain unchanged
- Lambda memory, timeout, and environment variable configurations for existing functions must remain unchanged

**Scope:**
All inputs that do NOT involve the 18 missing services should be completely unaffected by this fix. This includes:
- Existing API Gateway routes for deployed services
- Existing Lambda function invocations
- Existing DynamoDB read/write operations
- Existing Cognito authentication
- Existing CloudWatch monitoring and alarms

## Hypothesized Root Cause

Based on the bug description and code analysis, the most likely issues are:

1. **Manual Lambda Function Creation**: The `_create_lambda_functions()` method manually creates each Lambda function with hardcoded configuration, rather than using a service discovery pattern to automatically detect and deploy all services in `src/`

2. **Missing API Gateway Routes**: Even if Lambda functions were created, the corresponding API Gateway routes are not created in the `_create_*_endpoints()` methods (e.g., `_create_health_score_endpoints()`, `_create_rag_status_endpoints()`)

3. **Incomplete Service Inventory**: The developer who wrote the CDK code may not have been aware of all the services in the `src/` directory, or may have intentionally left some services undeployed for testing purposes

4. **Missing DynamoDB Permissions**: Even if Lambda functions were created, they may not have the necessary IAM permissions to read/write to the new project-management DynamoDB tables (projects, sprints, backlog_items, milestones, resources, dependencies, health_scores)

## Correctness Properties

Property 1: Bug Condition - All Services with Handlers Are Deployed

_For any_ service directory in `src/` where a `handler.py` file exists with a `lambda_handler` function (excluding 'shared', 'auth', 'authorizer'), the fixed CDK stack SHALL create a Lambda function with appropriate configuration (memory, timeout, environment variables) and deploy it to AWS.

**Validates: Requirements 2.2, 2.3, 2.4**

Property 2: Preservation - Existing Lambda Functions Unchanged

_For any_ Lambda function that is currently deployed (user_management, jira_integration, azure_devops, risk_detection, prediction, document_upload, document_intelligence, semantic_search, report_generation, dashboard, Authorizer, Upload URL Lambda, VPC Custom), the fixed CDK stack SHALL produce exactly the same Lambda function configuration (memory, timeout, environment variables, IAM permissions) as the original CDK stack, preserving all existing functionality.

**Validates: Requirements 3.1, 3.2, 3.4, 3.5, 3.6, 3.7**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `infrastructure/stacks/api_gateway_stack.py`

**Function**: `_create_lambda_functions()`

**Specific Changes**:

1. **Service Discovery Pattern**: Replace manual Lambda function creation with a service discovery loop that:
   - Scans the `src/` directory for all subdirectories
   - Checks if each subdirectory has a `handler.py` file
   - Verifies that `handler.py` contains a `lambda_handler` function (using regex or AST parsing)
   - Excludes special directories: `shared`, `__pycache__`, `auth` (if internal-only)
   - Creates a Lambda function for each discovered service

2. **Dynamic Lambda Configuration**: Create a mapping of service names to Lambda configurations:
   - Use existing `MEMORY_CONFIG` and `PROVISIONED_CONCURRENCY_CONFIG` from `lambda_optimization_config.py`
   - Add new services to the configuration with appropriate memory/timeout settings
   - Default to 512MB memory and 30-second timeout for services not in the configuration

3. **Dynamic API Gateway Routes**: Create API Gateway routes for each service based on naming conventions:
   - `/health-score/*` → health_score Lambda
   - `/rag-status/*` → rag_status Lambda
   - `/analysis-trigger` → analysis_trigger Lambda (EventBridge trigger, not API Gateway)
   - `/data-validation` → data_validation Lambda (EventBridge trigger)
   - `/data-storage` → data_storage Lambda (EventBridge trigger)
   - `/database-maintenance` → database_maintenance Lambda (EventBridge scheduled trigger)
   - `/document-processing` → document_processing Lambda (S3 trigger)
   - `/email-distribution` → email_distribution Lambda (EventBridge trigger)
   - `/report-scheduling/*` → report_scheduling Lambda
   - `/security-monitoring` → security_monitoring Lambda (EventBridge trigger)

4. **DynamoDB Permissions**: Grant all Lambda functions read/write access to new project-management tables:
   - projects_table
   - sprints_table
   - backlog_items_table
   - milestones_table
   - resources_table
   - dependencies_table
   - health_scores_table

5. **Environment Variables**: Ensure all Lambda functions have access to:
   - All DynamoDB table names (existing + new project-management tables)
   - S3 bucket names (documents_bucket, reports_bucket)
   - Cognito User Pool ID
   - Cache table name

6. **Handler Path Correction**: Ensure handler paths use the correct format:
   - For services in `src/`, use: `<service_name>.handler.lambda_handler`
   - Example: `health_score.handler.calculate_health_score_handler` for the calculate endpoint
   - Example: `health_score.handler.get_health_score_handler` for the get endpoint

7. **EventBridge Integration**: For services that are triggered by EventBridge (not API Gateway):
   - Create EventBridge rules in a separate method `_create_eventbridge_triggers()`
   - Connect rules to Lambda functions
   - Examples: analysis_trigger, data_validation, data_storage, security_monitoring

8. **S3 Integration**: For services triggered by S3 events:
   - Create S3 event notifications in the StorageStack
   - Connect S3 events to Lambda functions
   - Example: document_processing Lambda triggered by S3 upload to documents_bucket

### Implementation Strategy

**Phase 1: Service Discovery**
- Implement `_discover_services()` helper method that scans `src/` directory
- Returns list of service names with handler files
- Excludes special directories

**Phase 2: Lambda Function Creation**
- Refactor `_create_lambda_functions()` to loop over discovered services
- Create Lambda function for each service with dynamic configuration
- Maintain backward compatibility for existing 10 services

**Phase 3: API Gateway Routes**
- Create `_create_service_endpoints()` method that dynamically creates routes
- Use naming convention to map service names to URL paths
- Handle special cases (EventBridge triggers, S3 triggers)

**Phase 4: Permissions and Environment Variables**
- Grant DynamoDB permissions to all Lambda functions
- Add environment variables for all tables and buckets
- Ensure IAM policies are correctly applied

**Phase 5: Testing**
- Deploy CDK stack to AWS
- Verify all Lambda functions are created
- Test API Gateway routes for each service
- Verify DynamoDB permissions
- Check CloudWatch logs for errors

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code (missing Lambda functions), then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: 
1. List all deployed Lambda functions in AWS using `aws lambda list-functions`
2. Compare against all service directories in `src/` with `handler.py` files
3. Identify missing Lambda functions
4. Attempt to call API Gateway endpoints for missing services and observe 500 errors
5. Check CloudWatch logs for "Function not found" or similar errors

**Test Cases**:
1. **Health Score Endpoint Test**: Call `GET /health-score/{projectId}` and observe 500 error (will fail on unfixed code)
2. **RAG Status Endpoint Test**: Call `GET /rag-status/{projectId}` and observe 500 error (will fail on unfixed code)
3. **Report Scheduling Endpoint Test**: Call `POST /report-scheduling/schedule` and observe 500 error (will fail on unfixed code)
4. **Dashboard Dependency Test**: Call `GET /dashboard/overview` and observe that health_score data is missing or causes errors (will fail on unfixed code)

**Expected Counterexamples**:
- API Gateway returns 500 errors for missing service endpoints
- CloudWatch logs show "Execution failed due to configuration error: Invalid permissions on Lambda function"
- Frontend displays "Request failed with status code 500" errors
- Possible causes: missing Lambda functions, missing API Gateway routes, missing IAM permissions

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds (services with handler files but no deployed Lambda), the fixed CDK stack produces the expected behavior (deployed Lambda functions with API Gateway routes).

**Pseudocode:**
```
FOR ALL service WHERE isBugCondition(service) DO
  result := deployService(service)
  ASSERT lambdaFunctionExists(service.name)
  ASSERT apiGatewayRouteExists(service.name)
  ASSERT iamPermissionsGranted(service.name)
END FOR
```

**Test Plan**:
1. Deploy fixed CDK stack to AWS
2. List all Lambda functions and verify 18+ new functions are created
3. Test API Gateway routes for each new service
4. Verify DynamoDB permissions by invoking Lambda functions
5. Check CloudWatch logs for successful invocations

**Test Cases**:
1. **Health Score Lambda Deployed**: Verify `ai-sw-pm-health-score` Lambda exists in AWS
2. **Health Score API Route**: Call `GET /health-score/{projectId}` and receive 200 or 404 (not 500)
3. **RAG Status Lambda Deployed**: Verify `ai-sw-pm-rag-status` Lambda exists in AWS
4. **RAG Status API Route**: Call `GET /rag-status/{projectId}` and receive 200 or 404 (not 500)
5. **Report Scheduling Lambda Deployed**: Verify `ai-sw-pm-report-scheduling` Lambda exists in AWS
6. **Report Scheduling API Route**: Call `POST /report-scheduling/schedule` and receive 200 or 400 (not 500)
7. **DynamoDB Permissions**: Invoke health_score Lambda and verify it can read from health_scores_table
8. **EventBridge Integration**: Verify analysis_trigger Lambda is connected to EventBridge rule
9. **S3 Integration**: Verify document_processing Lambda is triggered by S3 upload events

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold (existing deployed Lambda functions), the fixed CDK stack produces the same result as the original CDK stack.

**Pseudocode:**
```
FOR ALL service WHERE NOT isBugCondition(service) DO
  ASSERT deployedLambdaConfig_original(service) = deployedLambdaConfig_fixed(service)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all existing services

**Test Plan**: 
1. Before deploying the fix, capture the configuration of all 10 existing Lambda functions (memory, timeout, environment variables, IAM policies)
2. Deploy the fixed CDK stack
3. Compare the configuration of the 10 existing Lambda functions to the captured baseline
4. Verify that no configuration has changed

**Test Cases**:
1. **User Management Lambda Preservation**: Verify `ai-sw-pm-user-management` Lambda has the same memory, timeout, and environment variables after fix
2. **Dashboard Lambda Preservation**: Verify `ai-sw-pm-dashboard` Lambda has the same configuration after fix
3. **Risk Detection Lambda Preservation**: Verify `ai-sw-pm-risk-detection` Lambda has the same configuration after fix
4. **Prediction Lambda Preservation**: Verify `ai-sw-pm-prediction` Lambda has the same configuration after fix
5. **API Gateway Routes Preservation**: Verify existing routes (`/users`, `/risks`, `/predictions`, `/dashboard`) continue to work
6. **Cognito Authentication Preservation**: Verify Authorizer Lambda continues to authenticate requests correctly
7. **DynamoDB Permissions Preservation**: Verify existing Lambda functions can still read/write to existing tables (users, integrations, risks, predictions, reports, documents)
8. **CloudWatch Alarms Preservation**: Verify existing alarms for throttles, errors, and latency are still configured

### Unit Tests

- Test service discovery logic to ensure it correctly identifies services with handler files
- Test Lambda configuration mapping to ensure correct memory/timeout settings
- Test API Gateway route creation for each service type (API Gateway, EventBridge, S3)
- Test IAM permission grants for DynamoDB tables
- Test environment variable injection for all Lambda functions

### Property-Based Tests

- Generate random service directories with handler files and verify Lambda functions are created
- Generate random Lambda configurations and verify they are correctly applied
- Generate random API Gateway routes and verify they are correctly created
- Test that all services with handler files have deployed Lambda functions across many scenarios

### Integration Tests

- Deploy full CDK stack to AWS test environment
- Test all API Gateway endpoints for new services
- Test EventBridge triggers for analysis_trigger, data_validation, security_monitoring
- Test S3 triggers for document_processing
- Test DynamoDB read/write operations from all Lambda functions
- Test end-to-end frontend → API Gateway → Lambda → DynamoDB flow for new services
- Verify CloudWatch logs show successful invocations for all services
