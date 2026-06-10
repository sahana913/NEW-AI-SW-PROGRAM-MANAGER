# Lambda Authorizer Missing Dependencies Bugfix Design

## Overview

The Lambda authorizer function fails with `Runtime.ImportModuleError: Unable to import module 'handler': No module named 'jwt'` because the CDK deployment using `lambda_.Code.from_asset()` does not automatically install Python dependencies from `requirements.txt`. This causes complete application failure as all API Gateway requests return 500 errors.

The fix requires configuring CDK to bundle Python dependencies during deployment using the `bundling` parameter with `BundlingOptions`. This will ensure PyJWT==2.8.0 and cryptography==41.0.7 are installed and packaged with the Lambda function code.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug - when the Lambda authorizer is deployed without its Python dependencies (PyJWT and cryptography)
- **Property (P)**: The desired behavior - Lambda authorizer successfully imports jwt module and validates JWT tokens
- **Preservation**: Existing authorizer validation logic, IAM policy generation, and error handling that must remain unchanged
- **lambda_handler**: The main entry point function in `src/authorizer/handler.py` that validates JWT tokens from AWS Cognito
- **Code.from_asset()**: CDK method that packages Lambda function code from a local directory
- **BundlingOptions**: CDK configuration that specifies how to bundle dependencies during deployment
- **PyJWT**: Python library (version 2.8.0) for encoding and decoding JSON Web Tokens
- **cryptography**: Python library (version 41.0.7) required by PyJWT for RSA signature verification

## Bug Details

### Bug Condition

The bug manifests when the Lambda authorizer function is deployed using `lambda_.Code.from_asset()` without bundling configuration. The CDK simply copies the Python source files to the Lambda deployment package but does not install dependencies from `requirements.txt`, causing runtime import failures.

**Formal Specification:**
```
FUNCTION isBugCondition(deployment)
  INPUT: deployment of type LambdaDeployment
  OUTPUT: boolean
  
  RETURN deployment.code_method == "Code.from_asset"
         AND deployment.has_requirements_txt == True
         AND deployment.bundling_config == None
         AND deployment.runtime_error == "No module named 'jwt'"
END FUNCTION
```

### Examples

- **Current Deployment**: `Code.from_asset("../../src/authorizer")` → Runtime error: "No module named 'jwt'"
- **API Gateway Request**: Any authenticated request → 500 Internal Server Error due to authorizer failure
- **Lambda Logs**: "Runtime.ImportModuleError: Unable to import module 'handler': No module named 'jwt'"
- **Expected Deployment**: `Code.from_asset("../../src/authorizer", bundling=...)` → Successful import and token validation

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- JWT token validation logic using PyJWKClient and RS256 algorithm must continue to work exactly as before
- IAM policy generation with Allow/Deny effects must remain unchanged
- Authorization context passing (userId, tenantId, role, email) to downstream Lambda functions must remain unchanged
- Error handling for expired tokens, invalid tokens, and missing headers must remain unchanged
- Logging behavior for authentication events must remain unchanged
- Environment variable usage (USER_POOL_ID, AWS_REGION) must remain unchanged
- IAM permissions for cognito-idp:GetUser and cognito-idp:DescribeUserPool must remain unchanged
- Lambda configuration (Python 3.11 runtime, memory size, timeout) must remain unchanged

**Scope:**
All inputs that do NOT involve the Lambda deployment process should be completely unaffected by this fix. This includes:
- Token validation logic and algorithms
- Policy generation logic
- Error handling and logging
- Environment variable configuration
- IAM permissions

## Hypothesized Root Cause

Based on the bug description and CDK code analysis, the root cause is:

1. **Missing Bundling Configuration**: The `lambda_.Code.from_asset()` method in `auth_stack.py` does not include a `bundling` parameter, which is required to install Python dependencies during CDK deployment.

2. **CDK Default Behavior**: By default, `Code.from_asset()` only copies files from the source directory to the Lambda deployment package. It does NOT automatically detect or install dependencies from `requirements.txt`.

3. **No Layer Alternative**: While the authorizer function is configured to use Lambda layers via `_get_lambda_layers("authorizer")`, the PyJWT and cryptography dependencies are not included in the common layer, so they must be bundled with the function itself.

4. **Deployment Process Gap**: The CDK deployment process lacks the step to run `pip install -r requirements.txt` before packaging the Lambda function code.

## Correctness Properties

Property 1: Bug Condition - Lambda Authorizer Imports Dependencies Successfully

_For any_ Lambda deployment where the authorizer function has a `requirements.txt` file with PyJWT and cryptography dependencies, the fixed CDK configuration SHALL bundle these dependencies into the deployment package, allowing the Lambda function to successfully import the jwt module and validate JWT tokens without Runtime.ImportModuleError.

**Validates: Requirements 2.1, 2.3, 2.4, 2.5**

Property 2: Preservation - Token Validation Logic Unchanged

_For any_ JWT token validation request where the authorizer function successfully imports its dependencies, the fixed code SHALL produce exactly the same validation behavior as the original code, preserving all token validation logic, policy generation, error handling, and authorization context passing.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `infrastructure/stacks/auth_stack.py`

**Function**: `AuthStack.__init__` (authorizer function creation)

**Specific Changes**:

1. **Add Bundling Configuration**: Modify the `lambda_.Function` constructor for the authorizer to include a `bundling` parameter in the `Code.from_asset()` call:

   ```python
   code=lambda_.Code.from_asset(
       os.path.join(os.path.dirname(__file__), "../../src/authorizer"),
       bundling=BundlingOptions(
           image=lambda_.Runtime.PYTHON_3_11.bundling_image,
           command=[
               "bash", "-c",
               "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output"
           ],
       )
   )
   ```

2. **Import BundlingOptions**: Add the import statement at the top of the file:
   ```python
   from aws_cdk import (
       Stack,
       RemovalPolicy,
       Duration,
       BundlingOptions,  # Add this import
       aws_cognito as cognito,
       aws_lambda as lambda_,
       aws_iam as iam,
   )
   ```

3. **Verify Requirements File**: Ensure `src/authorizer/requirements.txt` contains the correct dependencies:
   ```
   PyJWT==2.8.0
   cryptography==41.0.7
   ```

4. **No Changes to Handler Code**: The `src/authorizer/handler.py` file requires NO changes - the import statements and validation logic remain exactly as they are.

5. **No Changes to Lambda Configuration**: The Lambda function's runtime, memory size, timeout, environment variables, and IAM permissions remain unchanged.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed infrastructure, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Deploy the current CDK stack and invoke the authorizer function with a test event. Observe the Runtime.ImportModuleError in CloudWatch Logs. This confirms the dependencies are missing from the deployment package.

**Test Cases**:
1. **Deploy Current Stack**: Run `cdk deploy AuthStack` with current code (will fail on invocation)
2. **Invoke Authorizer**: Send API Gateway request with valid JWT token (will return 500 error)
3. **Check CloudWatch Logs**: Verify "No module named 'jwt'" error appears in logs (confirms bug)
4. **Inspect Deployment Package**: Download Lambda deployment package and verify PyJWT is missing (confirms root cause)

**Expected Counterexamples**:
- Lambda function fails to start with "Runtime.ImportModuleError: Unable to import module 'handler': No module named 'jwt'"
- Possible causes: missing bundling configuration, dependencies not installed during deployment

### Fix Checking

**Goal**: Verify that for all deployments where the bug condition holds (authorizer with requirements.txt), the fixed CDK configuration produces the expected behavior (successful dependency import).

**Pseudocode:**
```
FOR ALL deployment WHERE isBugCondition(deployment) DO
  result := deploy_with_bundling(deployment)
  ASSERT result.imports_jwt_successfully == True
  ASSERT result.validates_tokens == True
  ASSERT result.no_runtime_errors == True
END FOR
```

**Test Plan**:
1. **Deploy Fixed Stack**: Run `cdk deploy AuthStack` with bundling configuration
2. **Invoke Authorizer**: Send API Gateway request with valid JWT token
3. **Verify Success**: Confirm authorizer returns Allow policy and no import errors
4. **Check Deployment Package**: Download Lambda deployment package and verify PyJWT and cryptography are present in the package

**Test Cases**:
1. **Valid Token Test**: Send request with valid Cognito JWT token → Authorizer returns Allow policy
2. **Expired Token Test**: Send request with expired JWT token → Authorizer returns Unauthorized
3. **Invalid Token Test**: Send request with malformed JWT token → Authorizer returns Unauthorized
4. **Missing Header Test**: Send request without Authorization header → Authorizer returns Unauthorized
5. **Package Inspection**: Verify `jwt/` and `cryptography/` directories exist in deployment package

### Preservation Checking

**Goal**: Verify that for all token validation scenarios where the bug condition does NOT hold (i.e., after dependencies are successfully imported), the fixed function produces the same result as the original function would have produced if dependencies were available.

**Pseudocode:**
```
FOR ALL token_validation_request WHERE NOT isBugCondition(deployment) DO
  ASSERT authorizer_fixed(request) = authorizer_original(request)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the token validation input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that validation behavior is unchanged for all token types

**Test Plan**: Observe behavior on UNFIXED code first (if possible with manually installed dependencies), then write property-based tests capturing that behavior.

**Test Cases**:
1. **Token Validation Preservation**: Verify valid tokens are validated exactly as before (same claims extracted, same policy generated)
2. **Error Handling Preservation**: Verify expired/invalid tokens are rejected exactly as before (same error messages, same exceptions)
3. **Policy Generation Preservation**: Verify IAM policies have same structure (principalId, policyDocument, context)
4. **Context Passing Preservation**: Verify authorization context (userId, tenantId, role, email) is passed to downstream functions exactly as before
5. **Logging Preservation**: Verify log messages and log levels remain unchanged
6. **Environment Variable Preservation**: Verify USER_POOL_ID and AWS_REGION are used exactly as before

### Unit Tests

- Test CDK stack synthesis with bundling configuration (verify no errors)
- Test that bundling command installs dependencies correctly (mock pip install)
- Test that deployment package includes jwt and cryptography modules
- Test authorizer function with valid JWT token (integration test)
- Test authorizer function with expired JWT token (integration test)
- Test authorizer function with invalid JWT token (integration test)

### Property-Based Tests

- Generate random valid JWT tokens with different claims and verify authorizer validates them correctly
- Generate random expired JWT tokens and verify authorizer rejects them consistently
- Generate random malformed tokens and verify authorizer rejects them consistently
- Test that all token validation scenarios produce consistent policy structures

### Integration Tests

- Deploy full stack (AuthStack + ApiGatewayStack) and test end-to-end authentication flow
- Test API Gateway request with valid token → Successful API response
- Test API Gateway request with invalid token → 401 Unauthorized response
- Test API Gateway request without token → 401 Unauthorized response
- Verify CloudWatch Logs show successful token validation (no import errors)
- Verify authorization context is passed to downstream Lambda functions correctly
