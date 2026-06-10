# Implementation Plan

## Overview

This implementation plan follows the exploratory bugfix workflow:
1. **Explore** - Write tests BEFORE fix to understand the bug (Bug Condition)
2. **Preserve** - Write tests for non-buggy behavior (Preservation Requirements)
3. **Implement** - Apply the fix with understanding (Expected Behavior)
4. **Validate** - Verify fix works and doesn't break anything

## Task List

- [x] 1. Write bug condition exploration test (BEFORE implementing fix)
  - **Property 1: Bug Condition** - Missing Lambda Deployments for Services with Handlers
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: For each service directory in `src/` with a `handler.py` file (excluding 'shared', 'authorizer', 'auth'), verify that a corresponding Lambda function exists in AWS
  - Test implementation details from Bug Condition in design:
    - Scan `src/` directory for all subdirectories with `handler.py` files
    - Exclude special directories: 'shared', '__pycache__', 'authorizer', 'auth', 'data_ingestion' (empty)
    - For each service, check if Lambda function `ai-sw-pm-{service-name}` exists in AWS (using boto3 or CDK synth output)
    - Expected missing services: health_score, rag_status, analysis_trigger, audit_logging, data_validation, data_storage, database_maintenance, document_processing, email_distribution, report_scheduling, security_monitoring, pdf_export, document_intel
  - The test assertions should match the Expected Behavior Properties from design:
    - Assert that Lambda function exists for each service with handler.py
    - Assert that API Gateway route exists for each service (where applicable)
    - Assert that DynamoDB permissions are granted to each Lambda function
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
  - Document counterexamples found to understand root cause:
    - List all missing Lambda functions
    - List all missing API Gateway routes
    - Identify services that should have EventBridge triggers vs API Gateway routes
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.2, 1.3, 2.2, 2.3_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Existing Lambda Functions and Routes Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code for existing deployed Lambda functions:
    - Capture configuration of 10 existing Lambda functions: user_management, jira_integration, azure_devops, risk_detection, prediction, document_upload, document_intelligence, semantic_search, report_generation, dashboard
    - Capture configuration of 3 special Lambda functions: Authorizer, Upload URL Lambda, VPC Custom
    - Record memory size, timeout, environment variables, IAM permissions for each
    - Record API Gateway routes for each service
  - Write property-based tests capturing observed behavior patterns from Preservation Requirements:
    - For all existing Lambda functions, assert configuration remains unchanged after fix
    - For all existing API Gateway routes, assert routes remain unchanged after fix
    - For all existing DynamoDB permissions, assert permissions remain unchanged after fix
    - For Cognito authentication flow, assert Authorizer Lambda continues to work
  - Property-based testing generates many test cases for stronger guarantees
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.4, 3.5, 3.6, 3.7_

- [x] 3. Fix for incomplete backend deployment

  - [x] 3.1 Implement service discovery pattern in `api_gateway_stack.py`
    - Create `_discover_services()` helper method that:
      - Scans `src/` directory for all subdirectories
      - Checks if each subdirectory has a `handler.py` file
      - Verifies that `handler.py` contains a `lambda_handler` function (using regex or AST parsing)
      - Excludes special directories: 'shared', '__pycache__', 'authorizer', 'auth', 'data_ingestion'
      - Returns list of service names with handler files
    - _Bug_Condition: isBugCondition(service) where service.hasHandlerFile() AND service.hasLambdaHandlerFunction() AND NOT service.hasDeployedLambdaFunction() AND service.name NOT IN ['shared', 'auth', 'authorizer']_
    - _Expected_Behavior: All services with handler.py files SHALL have deployed Lambda functions with appropriate configuration_
    - _Preservation: Existing 10 Lambda functions and 3 deployed functions must continue to work without changes_
    - _Requirements: 2.2, 2.3, 3.1, 3.2_

  - [x] 3.2 Refactor `_create_lambda_functions()` to use service discovery
    - Replace manual Lambda function creation with loop over discovered services
    - For each discovered service:
      - Get Lambda configuration from `_get_lambda_config()` (memory, timeout)
      - Create Lambda function with naming convention: `ai-sw-pm-{service-name}`
      - Use handler path: `{service_name}.handler.lambda_handler`
      - Add common environment variables (DynamoDB tables, S3 buckets, Cognito)
      - Apply appropriate Lambda layers using `_get_lambda_layers()`
      - Enable X-Ray tracing
    - Maintain backward compatibility for existing 10 services (same configuration)
    - Add new services to `MEMORY_CONFIG` in `lambda_optimization_config.py` with appropriate settings:
      - health_score: 512MB, 30s (standard workload)
      - rag_status: 512MB, 30s (standard workload)
      - analysis_trigger: 512MB, 30s (EventBridge trigger)
      - audit_logging: 256MB, 15s (lightweight logging)
      - data_validation: 512MB, 30s (EventBridge trigger)
      - data_storage: 512MB, 30s (EventBridge trigger)
      - database_maintenance: 512MB, 60s (scheduled maintenance)
      - document_processing: 1024MB, 60s (S3 trigger, heavy processing)
      - email_distribution: 256MB, 30s (EventBridge trigger)
      - report_scheduling: 512MB, 30s (API Gateway + EventBridge)
      - security_monitoring: 512MB, 30s (EventBridge trigger)
      - pdf_export: 1024MB, 60s (heavy processing)
    - _Bug_Condition: Services with handler.py files but no deployed Lambda functions_
    - _Expected_Behavior: Lambda functions created for all discovered services with appropriate configuration_
    - _Preservation: Existing Lambda function configurations remain unchanged_
    - _Requirements: 2.2, 2.4, 3.6_

  - [x] 3.3 Grant DynamoDB permissions to all Lambda functions
    - Extend existing DynamoDB permission grants to include new Lambda functions
    - Grant read/write access to new project-management tables:
      - projects_table
      - sprints_table
      - backlog_items_table
      - milestones_table
      - resources_table
      - dependencies_table
      - health_scores_table
    - Grant access to cache table (CacheTable) for all Lambda functions
    - Ensure GSI access is granted: `{table.table_arn}/index/*`
    - _Bug_Condition: Missing DynamoDB permissions for new Lambda functions_
    - _Expected_Behavior: All Lambda functions have read/write access to required DynamoDB tables_
    - _Preservation: Existing DynamoDB permissions remain unchanged_
    - _Requirements: 2.6, 3.5_

  - [x] 3.4 Create dynamic API Gateway routes for new services
    - Create `_create_service_endpoints()` method that dynamically creates routes for discovered services
    - Use naming convention to map service names to URL paths:
      - health_score → `/health-score/*`
      - rag_status → `/rag-status/*`
      - report_scheduling → `/report-scheduling/*`
      - pdf_export → `/pdf-export/*`
    - For each service, create appropriate API Gateway resources and methods:
      - GET, POST, PUT, DELETE as needed based on handler functions
      - Apply Lambda authorizer to all routes
      - Add request validators where appropriate
    - Handle special cases:
      - Services with EventBridge triggers (analysis_trigger, data_validation, data_storage, security_monitoring, database_maintenance, email_distribution) do NOT need API Gateway routes
      - Services with S3 triggers (document_processing) do NOT need API Gateway routes
    - Call `_create_service_endpoints()` from `__init__()` after `_create_lambda_functions()`
    - _Bug_Condition: Missing API Gateway routes for services with handler.py files_
    - _Expected_Behavior: API Gateway routes created for all services that need them_
    - _Preservation: Existing API Gateway routes remain unchanged_
    - _Requirements: 2.3, 2.4, 3.4_

  - [x] 3.5 Create EventBridge integration for event-driven services
    - Create `_create_eventbridge_triggers()` method for services triggered by EventBridge
    - Create EventBridge rules for:
      - analysis_trigger: Scheduled rule for periodic analysis
      - data_validation: Event-driven rule for data validation events
      - data_storage: Event-driven rule for data storage events
      - security_monitoring: Event-driven rule for security violation events
      - database_maintenance: Scheduled rule for maintenance tasks
      - email_distribution: Event-driven rule for email notification events
    - Connect EventBridge rules to corresponding Lambda functions
    - Grant EventBridge permissions to invoke Lambda functions
    - Call `_create_eventbridge_triggers()` from `__init__()` after `_create_lambda_functions()`
    - _Bug_Condition: Missing EventBridge triggers for event-driven services_
    - _Expected_Behavior: EventBridge rules created and connected to Lambda functions_
    - _Preservation: No existing EventBridge rules to preserve (new functionality)_
    - _Requirements: 2.2, 2.4_

  - [x] 3.6 Create S3 integration for document processing service
    - In StorageStack (or create new method in ApiGatewayStack), create S3 event notification
    - Connect S3 upload events from documents_bucket to document_processing Lambda
    - Grant S3 permissions to invoke document_processing Lambda
    - Grant document_processing Lambda read/write access to documents_bucket
    - _Bug_Condition: Missing S3 trigger for document_processing service_
    - _Expected_Behavior: S3 upload events trigger document_processing Lambda_
    - _Preservation: Existing S3 bucket configuration remains unchanged_
    - _Requirements: 2.2, 2.4_

  - [x] 3.7 Update CloudWatch alarms for new Lambda functions
    - Extend `_create_alarms()` method to include new Lambda functions
    - Create throttle alarms for all new Lambda functions
    - Create error rate alarms for critical new services (health_score, rag_status, report_scheduling)
    - Create latency alarms for API Gateway routes
    - _Bug_Condition: Missing CloudWatch alarms for new Lambda functions_
    - _Expected_Behavior: CloudWatch alarms created for all new Lambda functions_
    - _Preservation: Existing CloudWatch alarms remain unchanged_
    - _Requirements: 3.7_

  - [x] 3.8 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - All Services with Handlers Are Deployed
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - Verify that all 18+ missing Lambda functions are now deployed
    - Verify that API Gateway routes exist for services that need them
    - Verify that EventBridge triggers exist for event-driven services
    - Verify that S3 trigger exists for document_processing service
    - _Requirements: 2.2, 2.3, 2.4_

  - [x] 3.9 Verify preservation tests still pass
    - **Property 2: Preservation** - Existing Lambda Functions and Routes Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)
    - Verify that existing 10 Lambda functions have unchanged configuration
    - Verify that existing 3 special Lambda functions continue to work
    - Verify that existing API Gateway routes continue to work
    - Verify that Cognito authentication flow continues to work
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 3.6, 3.7_

- [x] 4. Checkpoint - Ensure all tests pass
  - Deploy CDK stack to AWS test environment
  - Run all exploration tests and verify they pass
  - Run all preservation tests and verify they pass
  - Test API Gateway endpoints for new services:
    - Call `/health-score/{projectId}` and verify 200 or 404 (not 500)
    - Call `/rag-status/{projectId}` and verify 200 or 404 (not 500)
    - Call `/report-scheduling/schedule` and verify 200 or 400 (not 500)
    - Call `/pdf-export/generate` and verify 200 or 400 (not 500)
  - Test EventBridge triggers:
    - Verify analysis_trigger Lambda is invoked by EventBridge rule
    - Verify security_monitoring Lambda is invoked by security violation events
  - Test S3 trigger:
    - Upload document to documents_bucket and verify document_processing Lambda is invoked
  - Check CloudWatch logs for successful invocations
  - Verify DynamoDB permissions by invoking Lambda functions and checking they can read/write to tables
  - Ensure all tests pass, ask the user if questions arise
  - _Requirements: All requirements (1.1-3.7)_

## Notes

- **Bug Condition**: Services with `handler.py` files but no deployed Lambda functions
- **Expected Behavior**: All services with `handler.py` files have deployed Lambda functions with API Gateway routes (or EventBridge/S3 triggers)
- **Preservation**: Existing 10 Lambda functions and 3 special functions continue to work without changes
- **Testing Strategy**: Exploration test BEFORE fix (will fail), preservation tests BEFORE fix (will pass), then implement fix and verify both test suites pass
