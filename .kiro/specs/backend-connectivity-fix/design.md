# Backend Connectivity Authentication Bugfix Design

## Overview

The AI SW Program Manager frontend is experiencing authentication failures when communicating with the AWS API Gateway backend, resulting in "Missing Authentication Token" errors and forcing the application to fall back to demo data. This design addresses the root causes in the authentication flow between the React frontend, AWS Cognito, and API Gateway Lambda Authorizer, ensuring proper token validation and seamless data processing for uploaded documents and real predictions.

The fix approach involves correcting token format mismatches, fixing CORS configuration issues, updating the Lambda Authorizer validation logic, and implementing proper error handling throughout the authentication chain.

## Glossary

- **Bug_Condition (C)**: The condition that triggers authentication failures - when API Gateway returns "Missing Authentication Token" despite valid Cognito tokens being present
- **Property (P)**: The desired behavior when authentication succeeds - API calls return real backend data instead of falling back to demo data
- **Preservation**: Existing fallback mechanisms and error handling that must remain unchanged by the fix
- **JWT Token**: JSON Web Token issued by AWS Cognito containing user identity and claims
- **Lambda Authorizer**: AWS Lambda function that validates JWT tokens for API Gateway requests
- **API Gateway**: AWS service that routes HTTP requests to backend Lambda functions
- **Cognito ID Token**: JWT token containing user identity information (sub, email, custom attributes)
- **Bearer Token**: Authorization header format "Bearer <token>" expected by the API Gateway

## Bug Details

### Bug Condition

The bug manifests when the frontend makes authenticated API calls to the backend services. The API Gateway Lambda Authorizer is either not receiving the authorization token correctly, not validating the Cognito JWT token properly, or not handling the token format as expected by the API Gateway integration.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type HTTPRequest with Authorization header
  OUTPUT: boolean
  
  RETURN input.hasAuthorizationHeader = true
         AND input.authToken.isValidCognitoToken = true
         AND input.targetEndpoint IN ['/dashboard/overview', '/risks', '/predictions', '/documents', '/reports']
         AND apiGatewayResponse.status = 401
         AND apiGatewayResponse.message = "Missing Authentication Token"
END FUNCTION
```

### Examples

- **Dashboard Data Request**: Frontend calls `GET /dashboard/overview` with valid Cognito ID token → API Gateway returns 401 "Missing Authentication Token" → Frontend falls back to mock dashboard data
- **Risk Data Request**: Frontend calls `GET /risks` with Bearer token → API Gateway returns 401 "Missing Authentication Token" → Frontend displays mock risks instead of real risk analysis
- **Document Upload**: Frontend calls `POST /documents/upload` with authentication → API Gateway returns 401 → Upload falls back to quick upload without backend processing
- **Report Generation**: Frontend calls `POST /reports/generate` with valid token → API Gateway returns 401 → System creates mock report instead of processing real data

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Graceful fallback to demo data when backend is genuinely unavailable (network issues, Lambda cold starts)
- Automatic redirect to login page when tokens are expired or invalid
- CORS handling for preflight OPTIONS requests must continue to work
- Connection diagnostics must continue to show appropriate status messages
- Development mode debug logging and error display must remain functional

**Scope:**
All inputs that do NOT involve authenticated API calls to the backend should be completely unaffected by this fix. This includes:
- Unauthenticated endpoints (if any exist)
- Static asset loading and frontend routing
- Cognito authentication flow (login/logout/signup)
- Local caching and mock data fallback mechanisms

## Hypothesized Root Cause

Based on the bug description and code analysis, the most likely issues are:

1. **Token Format Mismatch**: The frontend may be sending the wrong token type (access token vs ID token) or the Lambda Authorizer may be expecting a different token format than what's being sent

2. **CORS Preflight Issues**: API Gateway may be rejecting requests due to CORS configuration problems, particularly with the Authorization header handling in preflight requests

3. **Lambda Authorizer Configuration**: The RequestAuthorizer may be misconfigured with incorrect identity sources or the authorizer function may not be properly validating Cognito JWT tokens

4. **Token Extraction Logic**: The Lambda Authorizer's token extraction logic may not be correctly parsing the "Bearer <token>" format or handling edge cases in the Authorization header

5. **Environment Variable Issues**: The Lambda Authorizer may not have access to the correct USER_POOL_ID or AWS_REGION environment variables needed for JWT validation

## Correctness Properties

Property 1: Bug Condition - Authentication Success for Valid Tokens

_For any_ HTTP request where a valid Cognito ID token is provided in the Authorization header and the request targets a protected API endpoint, the fixed authentication system SHALL validate the token successfully, allow the request to proceed to the backend Lambda function, and return real data instead of falling back to demo data.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

Property 2: Preservation - Fallback Behavior for Invalid Scenarios

_For any_ HTTP request where the backend is genuinely unavailable, tokens are expired/invalid, or network issues occur, the fixed system SHALL produce exactly the same fallback behavior as the original system, preserving graceful degradation to demo data and appropriate error messaging.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `AI-SW-Program-Manager/frontend/src/services/api.ts`

**Function**: Request interceptor in axios configuration

**Specific Changes**:
1. **Token Type Correction**: Ensure the frontend is sending the Cognito ID token (not access token) in the Authorization header
   - Verify `session.tokens?.idToken?.toString()` is the correct token type
   - Add validation to ensure token exists before making requests

2. **Header Format Standardization**: Ensure consistent "Bearer <token>" format
   - Verify the Authorization header format matches API Gateway expectations
   - Add logging to track token format being sent

**File**: `AI-SW-Program-Manager/infrastructure/stacks/api_gateway_stack.py`

**Function**: `_create_authorizer` method

**Specific Changes**:
3. **Identity Source Configuration**: Fix the RequestAuthorizer identity source configuration
   - Ensure `identity_sources=[apigw.IdentitySource.header("Authorization")]` is correct
   - Verify the authorizer is properly linked to API methods

4. **CORS Configuration Enhancement**: Update API Gateway CORS settings to properly handle Authorization headers
   - Ensure "Authorization" is included in `allow_headers`
   - Verify preflight OPTIONS requests are handled correctly

**File**: `AI-SW-Program-Manager/src/authorizer/handler.py`

**Function**: `extract_token` and `validate_token` functions

**Specific Changes**:
5. **Token Extraction Robustness**: Improve token extraction logic to handle edge cases
   - Add better error handling for malformed Authorization headers
   - Ensure proper parsing of "Bearer <token>" format
   - Add logging for debugging token extraction issues

6. **Environment Variable Validation**: Add validation for required environment variables
   - Ensure USER_POOL_ID and AWS_REGION are properly set
   - Add error handling for missing configuration

7. **JWT Validation Enhancement**: Improve JWT token validation logic
   - Ensure proper JWKS URL construction and caching
   - Add better error messages for different validation failure scenarios
   - Verify token type expectations (ID token vs access token)

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the authentication bug on unfixed code, then verify the fix works correctly and preserves existing fallback behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the authentication bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that simulate authenticated API requests with valid Cognito tokens and assert that the requests succeed and return real data. Run these tests on the UNFIXED code to observe 401 failures and understand the root cause.

**Test Cases**:
1. **Dashboard Authentication Test**: Simulate authenticated request to `/dashboard/overview` with valid ID token (will fail on unfixed code)
2. **Risk Data Authentication Test**: Simulate authenticated request to `/risks` with proper Bearer token format (will fail on unfixed code)
3. **Document Upload Authentication Test**: Simulate authenticated request to `/documents/upload` with Cognito token (will fail on unfixed code)
4. **Token Format Test**: Test different token formats (ID vs access token) to identify correct format (may reveal format mismatch on unfixed code)

**Expected Counterexamples**:
- API Gateway returns 401 "Missing Authentication Token" despite valid tokens being sent
- Possible causes: wrong token type, malformed Authorization header, CORS issues, authorizer misconfiguration

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed authentication system produces the expected behavior.

**Pseudocode:**
```
FOR ALL request WHERE isBugCondition(request) DO
  response := authenticatedAPICall_fixed(request)
  ASSERT response.status = 200
  ASSERT response.data.isRealData = true
  ASSERT response.data != mockData
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed system produces the same result as the original system.

**Pseudocode:**
```
FOR ALL request WHERE NOT isBugCondition(request) DO
  ASSERT authenticatedAPICall_original(request) = authenticatedAPICall_fixed(request)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that fallback behavior is unchanged for all non-authentication scenarios

**Test Plan**: Observe behavior on UNFIXED code first for network failures, expired tokens, and backend unavailability, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Network Failure Preservation**: Verify that network timeouts continue to trigger demo data fallback after fix
2. **Expired Token Preservation**: Verify that expired tokens continue to redirect to login page after fix
3. **Backend Unavailable Preservation**: Verify that Lambda cold starts and 5xx errors continue to show appropriate error messages after fix
4. **CORS Preflight Preservation**: Verify that OPTIONS requests continue to work correctly after CORS configuration changes

### Unit Tests

- Test JWT token extraction with various Authorization header formats
- Test Cognito token validation with valid and invalid tokens
- Test API Gateway authorizer response generation
- Test frontend token attachment in different authentication states

### Property-Based Tests

- Generate random valid Cognito tokens and verify authentication succeeds across all protected endpoints
- Generate random invalid/malformed tokens and verify appropriate error handling
- Test authentication flow across many different user states and token expiration scenarios

### Integration Tests

- Test full authentication flow from frontend login through API Gateway to backend Lambda
- Test connection diagnostics showing successful backend connectivity after fix
- Test document upload and processing with real backend integration
- Test report generation producing real reports instead of mock data
- Test dashboard displaying real project data and metrics