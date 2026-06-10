# Production Readiness Backend Fix - Bugfix Design

## Overview

This bugfix addresses critical production readiness issues preventing the AI SW Program Manager backend from processing real user data. The system currently falls back to demo data instead of processing uploaded documents, generating predictions from actual project metrics, and storing data in DynamoDB tables. This affects the core value proposition - providing AI-powered insights based on real project documents and metrics.

The bug manifests when users upload documents through the frontend. Documents are stored in S3 but never processed because no S3 event notification triggers the document processing Lambda. Predictions use heuristic fallback scoring because SageMaker endpoint environment variables are not configured. The dashboard shows demo data because Lambda functions lack DynamoDB table permissions and environment variables.

The fix requires infrastructure changes across 8 categories: S3 event notifications, DynamoDB table environment variables, IAM permissions, SageMaker endpoint configuration, CloudWatch alarms, frontend auto-refresh, and error handling improvements.

## Glossary

- **Bug_Condition (C)**: The system is in a buggy state when documents are uploaded but not processed, predictions use fallback heuristics instead of ML models, and dashboards show demo data instead of real project data
- **Property (P)**: The desired behavior where uploaded documents trigger automatic processing, predictions use configured SageMaker endpoints, and dashboards display real data from DynamoDB
- **Preservation**: Existing authentication, rate limiting, error handling, and data model patterns that must remain unchanged
- **S3 Event Notification**: AWS S3 feature that triggers Lambda functions when objects are created/modified in a bucket
- **SageMaker Endpoint**: AWS SageMaker inference endpoint for ML model predictions (delay classifier, delay regressor, workload predictor)
- **DynamoDB Single-Table Design**: Data model pattern using PK/SK with GSI indexes for efficient access patterns
- **Lambda Authorizer**: Custom API Gateway authorizer that validates JWT tokens and enforces tenant isolation
- **Pre-signed URL**: Time-limited S3 URL allowing direct browser uploads without exposing AWS credentials
- **Heuristic Fallback**: Simple rule-based scoring used when ML infrastructure is unavailable
- **Demo Data**: Hardcoded sample data returned when real data cannot be retrieved from DynamoDB

## Bug Details

### Bug Condition

The bug manifests when the backend infrastructure is deployed but critical configuration is missing. Documents are uploaded to S3 but the document processing Lambda is never invoked because no S3 event notification is configured. Predictions use heuristic fallback scoring because SageMaker endpoint environment variables (DELAY_CLASSIFIER_ENDPOINT, DELAY_REGRESSOR_ENDPOINT, WORKLOAD_ENDPOINT) are not set. The dashboard returns demo data because Lambda functions lack environment variables for project management DynamoDB tables (PROJECTS_TABLE_NAME, SPRINTS_TABLE_NAME, BACKLOG_ITEMS_TABLE_NAME, MILESTONES_TABLE_NAME, RESOURCES_TABLE_NAME, DEPENDENCIES_TABLE_NAME, HEALTH_SCORES_TABLE_NAME) and lack IAM permissions to read from these tables.

**Formal Specification:**
```
FUNCTION isBugCondition(system_state)
  INPUT: system_state containing {
    s3_event_notification_configured: boolean,
    sagemaker_endpoints_configured: boolean,
    dynamodb_table_env_vars_configured: boolean,
    lambda_iam_permissions_granted: boolean,
    document_uploaded: boolean
  }
  OUTPUT: boolean
  
  RETURN (system_state.document_uploaded == TRUE)
         AND (system_state.s3_event_notification_configured == FALSE
              OR system_state.sagemaker_endpoints_configured == FALSE
              OR system_state.dynamodb_table_env_vars_configured == FALSE
              OR system_state.lambda_iam_permissions_granted == FALSE)
END FUNCTION
```

### Examples

- **Document Upload Without Processing**: User uploads "Mobile-Banking-App-SOW.pdf" through frontend → Document stored at `s3://documents-bucket/tenant-123/documents/doc-456/Mobile-Banking-App-SOW.pdf` → Document status remains "PENDING_UPLOAD" indefinitely → No text extraction occurs → No predictions generated
  
- **Prediction Using Fallback Heuristics**: User requests delay prediction for project "proj-001" → Prediction Lambda extracts features from DynamoDB → SageMaker endpoint environment variable is empty → System logs warning "Delay prediction endpoint unavailable; using heuristic prediction" → Returns prediction with confidence score based on feature completeness instead of ML model confidence
  
- **Dashboard Showing Demo Data**: User navigates to dashboard → Dashboard Lambda queries project summaries → DynamoDB query fails with "Table not found" error → Exception caught silently → Returns hardcoded demo data: `[{"project_id": "proj-001", "project_name": "AI SW Program Manager", "source": "DEMO", "healthScore": 85}]`
  
- **Missing IAM Permissions**: Document processing Lambda invoked manually → Attempts to update document status in DynamoDB → Receives "AccessDeniedException: User is not authorized to perform: dynamodb:UpdateItem" → Processing fails → No error notification sent to user because NOTIFICATION_TOPIC_ARN is not configured

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Authentication flow using Cognito JWT tokens validated by Lambda authorizer must continue to work
- Tenant isolation enforced through authorizer context (tenantId) must remain unchanged
- API Gateway rate limiting (1000 req/s, 2000 burst) and usage quotas (1M req/month) must continue to apply
- Pre-signed URL generation for document uploads with 15-minute expiration must work as before
- DynamoDB single-table design with PK/SK pattern and GSI indexes must remain unchanged
- Error responses (400 for validation, 401/403 for auth, 500 for internal errors) must maintain current format
- Lambda function memory configurations from MEMORY_CONFIG must continue to be used
- X-Ray tracing enabled on all Lambda functions and API Gateway must remain active
- Structured logging using shared logger with log_api_request, log_data_modification, log_error must continue
- CORS headers allowing frontend origin access must remain configured

**Scope:**
All inputs and operations that do NOT involve document processing, prediction generation, or dashboard data retrieval should be completely unaffected by this fix. This includes:
- User authentication and authorization flows
- User management operations (create, list, update role)
- Integration configuration (Jira, Azure DevOps)
- Report generation and retrieval
- Semantic search functionality
- Risk detection and dismissal
- API Gateway request validation and throttling

## Hypothesized Root Cause

Based on the bug description and code analysis, the root causes are:

1. **Missing S3 Event Notification Configuration**: The `StorageStack` creates the documents bucket but does not configure an S3 event notification to trigger the document processing Lambda when objects are created. The `storage_stack.py` file shows no `add_event_notification` call on `self.documents_bucket`.

2. **Missing Environment Variables in API Gateway Stack**: The `ApiGatewayStack._create_lambda_functions()` method sets `common_env` with table names for core tables (USERS, INTEGRATIONS, RISKS, PREDICTIONS, REPORTS, DOCUMENTS) but conditionally adds project management table names only if the table references are not None. The `app.py` file passes these table references, but the environment variable names may be inconsistent or missing.

3. **Hardcoded IAM Policy ARNs**: The `ApiGatewayStack._grant_service_permissions()` method uses hardcoded S3 bucket ARN patterns like `"arn:aws:s3:::ai-sw-pm-documents-*/*"` instead of referencing the actual bucket ARN from `self.documents_bucket.bucket_arn`. This causes permission failures when the actual bucket name differs.

4. **Missing SageMaker Endpoint Configuration**: The `prediction/handler.py` file reads environment variables `DELAY_CLASSIFIER_ENDPOINT`, `DELAY_REGRESSOR_ENDPOINT`, and `WORKLOAD_ENDPOINT` but these are never set in the Lambda function environment. The `ApiGatewayStack` does not configure these variables.

5. **Silent Error Handling with Demo Data Fallback**: The `dashboard/dashboard_aggregator.py` file catches exceptions when querying DynamoDB and returns hardcoded demo data instead of propagating errors. This masks infrastructure issues and prevents proper error monitoring.

6. **Missing CloudWatch Alarms for Data Operations**: The `ApiGatewayStack._create_alarms()` method creates alarms for API 5XX errors, latency, and Lambda throttles, but does not create alarms for data persistence failures, prediction generation failures, or stale dashboard data.

7. **Frontend Hardcoded Project ID**: The `DocumentUpload.tsx` component uses `DEFAULT_PROJECT_ID = '770e8400-e29b-41d4-a716-446655440002'` instead of reading from application state. The `PredictionCharts.tsx` component does not automatically refresh when documents are uploaded.

8. **Missing Document Processing Trigger**: Even if S3 event notification is configured, the document processing Lambda may not be properly integrated with the storage stack. The `app.py` file does not pass the document processing Lambda reference to the storage stack.

## Correctness Properties

Property 1: Bug Condition - Document Upload Triggers Processing and Predictions

_For any_ document upload where a user uploads a valid document (PDF, DOCX, TXT) through the frontend, the fixed system SHALL automatically trigger document processing via S3 event notification, extract text using Textract, update document status to "UPLOADED" in DynamoDB, generate predictions using configured SageMaker endpoints (or heuristic fallback with clear indication), and display real project data in the dashboard.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 2.13, 2.14, 2.15, 2.16, 2.17, 2.18, 2.19, 2.20, 2.21, 2.22, 2.23, 2.24, 2.25, 2.26, 2.27, 2.28, 2.29, 2.30, 2.31, 2.32**

Property 2: Preservation - Existing Functionality Unchanged

_For any_ operation that does NOT involve document processing, prediction generation, or dashboard data retrieval (authentication, user management, integration configuration, report generation, semantic search, risk detection), the fixed system SHALL produce exactly the same behavior as the original system, preserving authentication flows, tenant isolation, rate limiting, error handling, data model patterns, and logging.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14, 3.15, 3.16, 3.17, 3.18, 3.19, 3.20, 3.21, 3.22, 3.23**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct, the following changes are required:

**File**: `infrastructure/stacks/storage_stack.py`

**Function**: `StorageStack.__init__`

**Specific Changes**:
1. **Add S3 Event Notification**: After creating `self.documents_bucket`, add an S3 event notification to trigger the document processing Lambda when objects are created with prefix `{tenant_id}/documents/`
   - Import `aws_s3_notifications` from `aws_cdk`
   - Add parameter `document_processing_function` to `__init__` method
   - Call `self.documents_bucket.add_event_notification(s3.EventType.OBJECT_CREATED, s3_notifications.LambdaDestination(document_processing_function), s3.NotificationKeyFilter(prefix="", suffix=""))`
   - Grant the document processing Lambda permission to be invoked by S3

2. **Pass Document Processing Lambda Reference**: The storage stack needs a reference to the document processing Lambda to configure the S3 event notification
   - Add `document_processing_function: lambda_.IFunction` parameter to `__init__`
   - Store as `self.document_processing_function = document_processing_function`

**File**: `infrastructure/app.py`

**Function**: `main` (module-level code)

**Specific Changes**:
1. **Create API Gateway Stack Before Storage Stack**: The storage stack needs the document processing Lambda from the API Gateway stack
   - Move `api_gateway_stack` creation before `storage_stack` creation
   - This creates a circular dependency that must be resolved

2. **Alternative: Create Document Processing Lambda in Separate Stack**: To avoid circular dependency, create a dedicated Lambda stack for document processing
   - Create `LambdaStack` that creates all Lambda functions
   - Pass Lambda references to both `StorageStack` (for S3 event notification) and `ApiGatewayStack` (for API Gateway integration)
   - Update dependencies: `storage_stack.add_dependency(lambda_stack)`, `api_gateway_stack.add_dependency(lambda_stack)`

3. **Pass All DynamoDB Tables to API Gateway Stack**: Ensure all project management tables are passed
   - Verify `projects_table`, `sprints_table`, `backlog_items_table`, `milestones_table`, `resources_table`, `dependencies_table`, `health_scores_table` are all passed
   - Already implemented in current `app.py`

**File**: `infrastructure/stacks/api_gateway_stack.py`

**Function**: `ApiGatewayStack._create_lambda_functions`

**Specific Changes**:
1. **Add SageMaker Endpoint Environment Variables**: Add SageMaker endpoint names to `common_env` dictionary
   - `common_env["DELAY_CLASSIFIER_ENDPOINT"] = os.environ.get("DELAY_CLASSIFIER_ENDPOINT", "")`
   - `common_env["DELAY_REGRESSOR_ENDPOINT"] = os.environ.get("DELAY_REGRESSOR_ENDPOINT", "")`
   - `common_env["WORKLOAD_ENDPOINT"] = os.environ.get("WORKLOAD_ENDPOINT", "")`
   - These will be empty strings if not configured, allowing graceful fallback

2. **Add SNS Topic ARN for Notifications**: Add notification topic ARN to `common_env`
   - `common_env["NOTIFICATION_TOPIC_ARN"] = self.alarm_topic.topic_arn if self.alarm_topic else ""`
   - Grant SNS publish permissions to document processing Lambda

3. **Ensure Consistent Table Name Environment Variables**: Verify all table names use `_TABLE_NAME` suffix
   - Already implemented for core tables
   - Project management tables conditionally added with correct suffix

**File**: `infrastructure/stacks/api_gateway_stack.py`

**Function**: `ApiGatewayStack._grant_service_permissions`

**Specific Changes**:
1. **Fix Hardcoded S3 Bucket ARNs**: Replace hardcoded ARN patterns with actual bucket references
   - Document upload service: Change `"arn:aws:s3:::ai-sw-pm-documents-*/*"` to `f"{self.documents_bucket.bucket_arn}/*"`
   - Document processing service: Change `"arn:aws:s3:::ai-sw-pm-documents-*/*"` to `f"{self.documents_bucket.bucket_arn}/*"`
   - PDF export service: Change `"arn:aws:s3:::ai-sw-pm-reports-*/*"` to `f"{self.reports_bucket.bucket_arn}/*"`

2. **Grant Document Processing Lambda DynamoDB Write Permissions**: Add to document_processing service permissions
   - `self.documents_table.grant_write_data(lambda_function)`

3. **Grant Prediction Lambda DynamoDB Read Permissions**: Add to prediction service permissions
   - Grant read permissions for all project management tables: `projects_table`, `sprints_table`, `backlog_items_table`, `milestones_table`, `resources_table`, `dependencies_table`

4. **Grant Dashboard Lambda DynamoDB Read Permissions**: Add to dashboard service permissions
   - Grant read permissions for `health_scores_table`, `sprints_table`, `milestones_table`, `resources_table`, `dependencies_table`

5. **Grant Document Processing Lambda SNS Publish Permissions**: Add to document_processing service permissions
   - `lambda_function.add_to_role_policy(iam.PolicyStatement(actions=["sns:Publish"], resources=[self.alarm_topic.topic_arn]))`

**File**: `infrastructure/stacks/api_gateway_stack.py`

**Function**: `ApiGatewayStack._create_alarms`

**Specific Changes**:
1. **Add Data Persistence Failure Alarm**: Create CloudWatch alarm for DynamoDB write failures
   - Monitor `Errors` metric for document processing Lambda
   - Threshold: 1 error in 5 minutes
   - Action: Send SNS notification to `self.alarm_topic`

2. **Add Prediction Generation Failure Alarm**: Create CloudWatch alarm for prediction failures
   - Monitor `Errors` metric for prediction Lambda
   - Threshold: 5 errors in 15 minutes
   - Action: Send SNS notification to `self.alarm_topic`

3. **Add Dashboard Data Staleness Alarm**: Create CloudWatch alarm for stale dashboard data
   - Monitor custom metric `DashboardDataAge` (requires Lambda to publish metric)
   - Threshold: Data age > 24 hours
   - Action: Send SNS notification to `self.alarm_topic`

**File**: `src/dashboard/dashboard_aggregator.py`

**Function**: `get_project_summaries`

**Specific Changes**:
1. **Remove Demo Data Fallback**: Replace demo data fallback with proper error handling
   - Remove the `except Exception as e:` block that returns hardcoded demo data
   - Let exceptions propagate to the Lambda handler
   - Lambda handler should return 503 Service Unavailable with error message

2. **Add Logging for Database Unavailability**: Log errors with context before propagating
   - `logger.error(f"Failed to get project summaries: {str(e)}", extra={"tenant_id": tenant_id})`
   - Raise exception to trigger CloudWatch alarm

**File**: `src/dashboard/handler.py`

**Function**: `lambda_handler`

**Specific Changes**:
1. **Return Proper Error Responses**: When dashboard data is unavailable, return 503 instead of demo data
   - Catch exceptions from `dashboard_aggregator.get_dashboard_overview()`
   - Return `{"statusCode": 503, "body": json.dumps({"error": {"code": "SERVICE_UNAVAILABLE", "message": "Dashboard data temporarily unavailable"}})}`
   - This allows frontend to display proper error message instead of misleading demo data

**File**: `frontend/src/components/Documents/DocumentUpload.tsx`

**Function**: `uploadFile`

**Specific Changes**:
1. **Trigger Prediction Refresh After Upload**: Call `onUploadComplete` callback to notify parent component
   - Already implemented: `if (result.documentId && props.onUploadComplete) { props.onUploadComplete(DEFAULT_PROJECT_ID, result.documentId); }`
   - Parent component (Dashboard) should trigger prediction refresh

2. **Remove Hardcoded Project ID**: Use project ID from props or application state
   - Change `DEFAULT_PROJECT_ID` to `props.projectId || DEFAULT_PROJECT_ID`
   - Add `projectId?: string` to `DocumentUploadProps` interface

**File**: `frontend/src/components/Dashboard/Dashboard.tsx`

**Function**: `Dashboard` component

**Specific Changes**:
1. **Add Auto-Refresh on Document Upload**: Increment `refreshKey` state when document upload completes
   - Add `const [refreshKey, setRefreshKey] = useState(0)` state
   - Pass `onUploadComplete={() => setRefreshKey(prev => prev + 1)}` to `DocumentUpload` component
   - Pass `refreshKey={refreshKey}` to `PredictionCharts` component
   - `PredictionCharts` already has `useEffect` dependency on `props.refreshKey`

**File**: `frontend/src/components/Dashboard/PredictionCharts.tsx`

**Function**: `loadPredictions`

**Specific Changes**:
1. **Remove Mock Data Fallback**: Display empty state instead of mock data when API fails
   - Already implemented: Sets `EMPTY_DELAY_DATA`, `EMPTY_WORKLOAD_DATA`, `EMPTY_CONFIDENCE_DATA` on error
   - Sets `errorMessage` to display user-friendly message

2. **Use Project ID from Props**: Remove hardcoded project ID
   - Already implemented: Uses `props.projectId || ''`
   - Skips API call when no project ID available

**File**: `frontend/src/services/api.ts`

**Function**: Response interceptor

**Specific Changes**:
1. **Attempt Token Refresh Before Sign Out**: On 401 error, try refreshing token once
   - Already implemented: Checks `(error.config as any)?._retried` flag
   - Calls `fetchAuthSession({ forceRefresh: true })` to refresh token
   - Retries original request with new token
   - Signs out only if refresh fails

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Deploy the current (unfixed) infrastructure to a test AWS account. Upload a test document through the frontend. Observe that the document is stored in S3 but the document processing Lambda is never invoked. Check CloudWatch Logs for the document processing Lambda - there should be no log entries. Query the Documents DynamoDB table - the document status should remain "PENDING_UPLOAD". Request a prediction for a project - observe that the prediction uses heuristic fallback scoring and logs "Delay prediction endpoint unavailable; using heuristic prediction". Navigate to the dashboard - observe that it returns demo data with `"source": "DEMO"`.

**Test Cases**:
1. **Document Upload Without S3 Event Notification**: Upload "test-document.pdf" through frontend → Check S3 bucket for object → Check CloudWatch Logs for document processing Lambda (will show no invocations) → Query Documents table for document status (will show "PENDING_UPLOAD") → **Expected**: Document processing Lambda never invoked, status remains "PENDING_UPLOAD"

2. **Prediction Without SageMaker Endpoints**: Request delay prediction for project "proj-001" → Check CloudWatch Logs for prediction Lambda → Search for log message "Delay prediction endpoint unavailable; using heuristic prediction" → Check prediction response for confidence score calculation → **Expected**: Prediction uses heuristic fallback, confidence based on feature completeness

3. **Dashboard Without DynamoDB Permissions**: Navigate to dashboard → Check CloudWatch Logs for dashboard Lambda → Search for log message "Failed to get project summaries" → Check API response for demo data with `"source": "DEMO"` → **Expected**: Dashboard returns hardcoded demo data instead of real project data

4. **Document Processing Without IAM Permissions**: Manually invoke document processing Lambda with test S3 event → Check CloudWatch Logs for "AccessDeniedException" → Check Documents table for document status (will remain "PENDING_UPLOAD") → **Expected**: Lambda fails with permission error, document status not updated

**Expected Counterexamples**:
- Document processing Lambda never invoked when documents uploaded to S3
- Predictions use heuristic fallback scoring instead of SageMaker endpoints
- Dashboard returns demo data instead of querying DynamoDB
- Lambda functions fail with "AccessDeniedException" when attempting DynamoDB operations
- Possible causes: Missing S3 event notification, missing environment variables, missing IAM permissions, hardcoded bucket ARNs

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL system_state WHERE isBugCondition(system_state) DO
  // Deploy fixed infrastructure
  deploy_fixed_infrastructure()
  
  // Upload document
  document_id := upload_document("test-document.pdf", project_id="proj-001")
  
  // Wait for processing
  WAIT 30 seconds
  
  // Verify document processed
  document_status := query_document_status(document_id)
  ASSERT document_status == "UPLOADED"
  
  // Verify text extracted
  extracted_text := query_extracted_text(document_id)
  ASSERT extracted_text IS NOT NULL AND LENGTH(extracted_text) > 0
  
  // Request prediction
  prediction := request_delay_prediction(project_id="proj-001")
  
  // Verify prediction uses SageMaker or clear fallback indication
  IF sagemaker_endpoints_configured THEN
    ASSERT prediction.used_ml_model == TRUE
  ELSE
    ASSERT prediction.used_heuristic_fallback == TRUE
    ASSERT prediction.warning_message CONTAINS "ML endpoints not configured"
  END IF
  
  // Verify dashboard shows real data
  dashboard_data := request_dashboard_overview()
  ASSERT dashboard_data.projects[0].source != "DEMO"
  ASSERT dashboard_data.projects[0].project_id == "proj-001"
  
  // Verify CloudWatch alarms configured
  alarms := list_cloudwatch_alarms()
  ASSERT alarms CONTAINS "ai-sw-pm-document-processing-errors"
  ASSERT alarms CONTAINS "ai-sw-pm-prediction-errors"
  ASSERT alarms CONTAINS "ai-sw-pm-dashboard-data-staleness"
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL operation WHERE NOT involves_document_processing_or_predictions(operation) DO
  // Execute operation on unfixed system
  result_unfixed := execute_operation_unfixed(operation)
  
  // Execute operation on fixed system
  result_fixed := execute_operation_fixed(operation)
  
  // Verify results are identical
  ASSERT result_unfixed == result_fixed
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Deploy both unfixed and fixed infrastructure to separate test AWS accounts. For each preserved operation (authentication, user management, integration configuration, report generation, semantic search, risk detection), execute the operation on both systems and compare responses. Verify that authentication flows, tenant isolation, rate limiting, error responses, and logging are identical.

**Test Cases**:
1. **Authentication Flow Preservation**: Authenticate user with Cognito → Verify JWT token format identical → Make authenticated API request → Verify authorizer context (userId, tenantId) identical → Verify 401 response for invalid token identical

2. **User Management Preservation**: Create user → Verify response format identical → List users → Verify response format identical → Update user role → Verify response format identical

3. **Rate Limiting Preservation**: Make 1001 requests per second → Verify 429 throttle response identical → Verify throttle response headers identical

4. **Error Response Preservation**: Make request with invalid body → Verify 400 validation error format identical → Make request without auth token → Verify 401 error format identical → Trigger internal error → Verify 500 error format identical (without exposing internal details)

5. **DynamoDB Data Model Preservation**: Create project → Verify PK/SK pattern identical → Query using GSI → Verify query response format identical → Store numeric value → Verify Decimal conversion identical

### Unit Tests

- Test S3 event notification configuration: Verify `documents_bucket.add_event_notification` called with correct parameters
- Test environment variable configuration: Verify all Lambda functions have required environment variables set
- Test IAM permission grants: Verify Lambda execution roles have correct DynamoDB and S3 permissions
- Test CloudWatch alarm creation: Verify alarms created with correct metrics, thresholds, and SNS actions
- Test document processing Lambda: Mock S3 event, verify Textract called, verify DynamoDB update, verify SNS notification on failure
- Test prediction Lambda: Mock DynamoDB queries, verify SageMaker endpoint invoked (or heuristic fallback), verify prediction stored
- Test dashboard Lambda: Mock DynamoDB queries, verify real data returned (not demo data), verify 503 error on failure

### Property-Based Tests

- Generate random document uploads with varying file sizes, formats, and tenant IDs → Verify all documents processed successfully
- Generate random project data in DynamoDB → Verify predictions generated for all projects
- Generate random dashboard requests with varying tenant IDs and project filters → Verify real data returned (not demo data)
- Generate random API requests across all endpoints → Verify authentication, rate limiting, and error handling preserved

### Integration Tests

- Deploy full infrastructure to test AWS account → Upload document → Wait for processing → Verify document status "UPLOADED" → Request prediction → Verify prediction uses SageMaker or clear fallback → Navigate to dashboard → Verify real data displayed
- Test document upload failure handling: Upload invalid file format → Verify 400 error → Upload file exceeding size limit → Verify 400 error
- Test prediction failure handling: Request prediction for non-existent project → Verify 404 error → Trigger SageMaker endpoint failure → Verify heuristic fallback with warning
- Test dashboard failure handling: Delete DynamoDB table → Request dashboard → Verify 503 error (not demo data)
- Test CloudWatch alarm triggering: Trigger document processing failure → Verify alarm fires → Verify SNS notification sent
- Test frontend auto-refresh: Upload document → Verify prediction charts refresh automatically → Verify dashboard updates with new data
