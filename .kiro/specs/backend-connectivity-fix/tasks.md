# Implementation Plan

## Bug Condition Exploration Tests (BEFORE Fix)

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Authentication Token Validation Failure
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate authentication failures with valid tokens
  - **Scoped PBT Approach**: Focus on concrete failing cases with valid Cognito ID tokens to protected endpoints
  - Test that authenticated requests to `/dashboard/overview`, `/risks`, `/predictions`, `/documents`, `/reports` with valid Cognito ID tokens succeed and return real data (not mock data)
  - The test assertions should verify: response.status = 200, response.data.isRealData = true, response.data != mockData
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS with 401 "Missing Authentication Token" errors (this is correct - it proves the bug exists)
  - Document counterexamples found: specific endpoints, token formats, and error responses
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Fallback Behavior for Invalid Scenarios
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code for scenarios where authentication should fail or fallback
  - Test cases: network failures, expired tokens, backend unavailability, invalid tokens, CORS preflight requests
  - Write property-based tests capturing observed fallback behavior patterns from Preservation Requirements
  - Verify graceful degradation to demo data, login redirects, and error messaging work correctly
  - Property-based testing generates many test cases for stronger preservation guarantees
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline fallback behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

## Frontend Authentication Token Handling Fixes

- [ ] 3. Fix frontend token handling and format

  - [x] 3.1 Implement frontend authentication token fixes
    - Fix token type selection in `AI-SW-Program-Manager/frontend/src/services/api.ts`
    - Ensure Cognito ID token (not access token) is used: `session.tokens?.idToken?.toString()`
    - Standardize Authorization header format to "Bearer <token>"
    - Add token validation before making requests to prevent empty/undefined tokens
    - Add debug logging for token format and presence in development mode
    - Implement proper error handling for token extraction failures
    - _Bug_Condition: isBugCondition(input) where input.hasAuthorizationHeader = true AND input.authToken.isValidCognitoToken = true_
    - _Expected_Behavior: API calls succeed and return real backend data instead of falling back to demo data_
    - _Preservation: Maintain existing fallback mechanisms for network issues and invalid tokens_
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 3.2 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Authentication Token Validation Success
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior for valid authentication
    - When this test passes, it confirms authenticated requests succeed with real data
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms frontend token handling is fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

## API Gateway and Lambda Authorizer Configuration Fixes

- [ ] 4. Fix API Gateway CORS and authorizer configuration

  - [x] 4.1 Implement API Gateway configuration fixes
    - Update CORS settings in `AI-SW-Program-Manager/infrastructure/stacks/api_gateway_stack.py`
    - Ensure "Authorization" header is included in `allow_headers` for CORS
    - Verify preflight OPTIONS requests handle Authorization header correctly
    - Fix RequestAuthorizer identity source configuration: `identity_sources=[apigw.IdentitySource.header("Authorization")]`
    - Ensure authorizer is properly linked to all protected API methods
    - Add proper error handling for authorizer configuration issues
    - _Bug_Condition: API Gateway returns 401 despite valid authorization headers due to CORS or authorizer misconfiguration_
    - _Expected_Behavior: API Gateway properly validates authorization headers and routes requests to backend_
    - _Preservation: Maintain existing CORS handling for non-authenticated requests_
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 4.2 Verify API Gateway configuration changes
    - Test that CORS preflight requests work correctly with Authorization header
    - Verify RequestAuthorizer is properly configured and linked
    - Test API Gateway routing to backend Lambda functions
    - Confirm no regressions in existing CORS functionality
    - _Requirements: 2.1, 2.2, 2.3_

## Backend Authentication Validation Improvements

- [ ] 5. Fix Lambda Authorizer token validation logic

  - [x] 5.1 Implement Lambda Authorizer improvements
    - Enhance token extraction logic in `AI-SW-Program-Manager/src/authorizer/handler.py`
    - Improve `extract_token` function to handle edge cases in Authorization header parsing
    - Add robust "Bearer <token>" format validation with better error messages
    - Add validation for required environment variables (USER_POOL_ID, AWS_REGION)
    - Enhance JWT validation logic with proper JWKS URL construction and caching
    - Improve error handling for different validation failure scenarios
    - Add debug logging for token extraction and validation steps
    - Ensure proper handling of Cognito ID tokens vs access tokens
    - _Bug_Condition: Lambda Authorizer fails to validate valid Cognito tokens due to extraction or validation issues_
    - _Expected_Behavior: Lambda Authorizer successfully validates Cognito ID tokens and allows requests to proceed_
    - _Preservation: Maintain existing error responses for genuinely invalid tokens_
    - _Requirements: 2.1, 2.2, 2.4, 2.5_

  - [x] 5.2 Verify Lambda Authorizer improvements
    - Test token extraction with various Authorization header formats
    - Test JWT validation with valid and invalid Cognito tokens
    - Verify proper error messages for different failure scenarios
    - Test environment variable validation and error handling
    - Confirm authorizer response generation works correctly
    - _Requirements: 2.1, 2.2, 2.4, 2.5_

## Integration Testing and Verification

- [ ] 6. Integration testing and final verification

  - [x] 6.1 Run comprehensive integration tests
    - Test full authentication flow from frontend login through API Gateway to backend Lambda
    - Verify connection diagnostics show successful backend connectivity
    - Test document upload and processing with real backend integration
    - Test report generation produces real reports instead of mock data
    - Test dashboard displays real project data and metrics
    - Verify all protected endpoints work with authenticated requests
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 6.2 Verify preservation tests still pass
    - **Property 2: Preservation** - Fallback Behavior for Invalid Scenarios
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions in fallback behavior)
    - Confirm graceful fallback to demo data for network issues still works
    - Verify expired token handling still redirects to login page
    - Confirm CORS preflight requests still work for non-authenticated endpoints
    - Ensure error messaging and connection diagnostics remain functional
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 7. Checkpoint - Ensure all tests pass
  - Verify bug condition exploration test passes (authentication works)
  - Verify preservation tests pass (no regressions in fallback behavior)
  - Confirm all integration tests pass
  - Validate that frontend no longer falls back to demo data for authenticated requests
  - Ensure connection diagnostics show successful backend connectivity
  - Ask the user if any questions arise or additional testing is needed