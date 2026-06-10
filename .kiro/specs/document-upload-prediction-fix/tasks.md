cd AI-SW-Program-Manager# Implementation Plan

## Phase 1: Exploration Tests (BEFORE Fix)

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Undefined Mock Data Crash on Empty Predictions
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Test all five bug conditions across the upload-to-prediction flow
  - Test implementation details from Bug Condition in design:
    - Cause 1: Mock `getPredictionHistory` to return `{ predictions: [] }` → assert `ReferenceError: mockDashboardData is not defined` is thrown
    - Cause 1 (error path): Mock `getPredictionHistory` to throw network error → assert `ReferenceError` is thrown
    - Cause 2: Mock successful `uploadDocument` → assert `createDelayPrediction` is NOT called
    - Cause 3: Render `PredictionCharts` with `projectId="my-real-project"` → assert `getPredictionHistory` called with hardcoded UUID `770e8400-e29b-41d4-a716-446655440002`
    - Cause 4: Mock API call returning 401 → assert `signOut` called immediately without `fetchAuthSession({ forceRefresh: true })`
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
  - Document counterexamples found to understand root cause
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Buggy Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code for non-buggy inputs:
    - Non-empty predictions render correctly (happy path)
    - Failed upload does not trigger prediction
    - Non-401 errors (500, 403, 404) do not trigger sign-out
    - Unauthenticated access redirects to login
    - File validation errors prevent upload (invalid file type, size > 10MB)
    - Async document status updates work without page reload
  - Write property-based tests capturing observed behavior patterns from Preservation Requirements
  - Property-based testing generates many test cases for stronger guarantees
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

## Phase 2: Implementation

- [x] 3. Fix 1 — Define fallback data constants in PredictionCharts.tsx

  - [x] 3.1 Add defined fallback constants at top of file
    - Define `EMPTY_DELAY_DATA: any[] = []`
    - Define `EMPTY_WORKLOAD_DATA: any[] = []`
    - Define `EMPTY_CONFIDENCE_DATA` with zero values for High/Medium/Low confidence
    - _Bug_Condition: isBugCondition(input) where apiReturnsEmptyPredictions(input) OR apiThrowsError(input)_
    - _Expected_Behavior: Component renders without ReferenceError, displays empty-state UI_
    - _Preservation: Non-empty predictions continue to render correctly_
    - _Requirements: 2.1, 2.2_

  - [x] 3.2 Replace undefined mock data references
    - Replace `mockDashboardData.predictions` with `EMPTY_DELAY_DATA` in empty-predictions branch
    - Replace `mockWorkloadData` with `EMPTY_WORKLOAD_DATA` in empty-predictions branch
    - Replace `mockConfidenceData` with `EMPTY_CONFIDENCE_DATA` in empty-predictions branch
    - Replace same references in `catch` block error path
    - _Requirements: 2.1, 2.2_

  - [x] 3.3 Update empty-state message
    - Change message from "Using demo data - backend is not available." to "No predictions yet — upload a document to get started."
    - Make message actionable and accurate
    - _Requirements: 2.1_

  - [x] 3.4 Verify Fix 1 exploration test now passes
    - **Property 1: Expected Behavior** - Empty Predictions Render Without Crash
    - **IMPORTANT**: Re-run the SAME test from task 1 (Cause 1 cases) - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test for Cause 1 (empty predictions and error path)
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2_

- [x] 4. Fix 2 — Add onUploadComplete callback prop to DocumentUpload.tsx

  - [x] 4.1 Add onUploadComplete prop to component interface
    - Add `onUploadComplete?: (projectId: string, documentId: string) => void` to `DocumentUploadProps`
    - Make prop optional to maintain backward compatibility
    - _Bug_Condition: isBugCondition(input) where input.event == UPLOAD_COMPLETE AND NOT predictionEndpointCalled(input)_
    - _Expected_Behavior: Callback invoked with projectId and documentId after successful upload_
    - _Preservation: Failed uploads do not trigger callback_
    - _Requirements: 2.3, 2.6_

  - [x] 4.2 Call onUploadComplete in uploadFile success path
    - After file state is updated to 'completed', check if `result.documentId` exists and `props.onUploadComplete` is defined
    - Call `props.onUploadComplete(DEFAULT_PROJECT_ID, result.documentId)`
    - Note: DEFAULT_PROJECT_ID will be replaced with dynamic value in Fix 3
    - _Requirements: 2.3, 2.6_

  - [x] 4.3 Verify Fix 2 exploration test now passes
    - **Property 1: Expected Behavior** - Upload Triggers Callback
    - **IMPORTANT**: Re-run the SAME test from task 1 (Cause 2 case) - do NOT write a new test
    - Run bug condition exploration test for Cause 2 (upload completion)
    - **EXPECTED OUTCOME**: Test PASSES (confirms callback is invoked)
    - _Requirements: 2.3, 2.6_

- [x] 5. Fix 3 — Replace hardcoded project ID with dynamic value

  - [x] 5.1 Add projectId prop to PredictionCharts
    - Add `projectId?: string` to `PredictionChartsProps` interface
    - Replace hardcoded `const projectId = '770e8400-...'` with `const effectiveProjectId = props.projectId || ''`
    - When `effectiveProjectId` is empty, skip API call and show empty-state UI directly
    - _Bug_Condition: isBugCondition(input) where projectIdUsed(input) == HARDCODED_UUID AND input.state.activeProjectId != HARDCODED_UUID_
    - _Expected_Behavior: Component uses dynamic projectId from props, not hardcoded UUID_
    - _Preservation: Empty project state shows empty-state message_
    - _Requirements: 2.4_

  - [x] 5.2 Add activeProjectId state to Dashboard.tsx
    - Add `const [activeProjectId, setActiveProjectId] = useState<string>('')`
    - State will track the current project for prediction fetching
    - _Requirements: 2.4_

  - [x] 5.3 Fetch user's active project on Dashboard mount
    - Use `apiEndpoints.getProjects()` in `useEffect` to fetch available projects
    - Set `activeProjectId` to first project's ID if available
    - Handle empty projects array gracefully
    - _Requirements: 2.4_

  - [x] 5.4 Wire projectId prop to PredictionCharts
    - Pass `projectId={activeProjectId}` to `<PredictionCharts>` in dashboard view
    - Component will re-fetch when projectId changes
    - _Requirements: 2.4_

  - [x] 5.5 Update DocumentUpload to use dynamic project ID
    - Replace `DEFAULT_PROJECT_ID` constant usage with a prop or context value (future enhancement)
    - For now, keep using DEFAULT_PROJECT_ID but document that it should be replaced
    - _Requirements: 2.4_

  - [x] 5.6 Verify Fix 3 exploration test now passes
    - **Property 1: Expected Behavior** - Dynamic Project ID Used
    - **IMPORTANT**: Re-run the SAME test from task 1 (Cause 3 case) - do NOT write a new test
    - Run bug condition exploration test for Cause 3 (hardcoded project ID)
    - **EXPECTED OUTCOME**: Test PASSES (confirms dynamic project ID is used)
    - _Requirements: 2.4_

- [x] 6. Fix 4 — Soften 401 handler in api.ts (token refresh + retry)

  - [x] 6.1 Add token refresh logic to 401 interceptor
    - Check if `error.config._retried` flag is set to avoid infinite loops
    - If not retried yet, log "401 received — attempting token refresh"
    - Call `fetchAuthSession({ forceRefresh: true })` to get new ID token
    - If refresh succeeds, set `error.config._retried = true` and update Authorization header
    - Retry original request with `return api(error.config)`
    - _Bug_Condition: isBugCondition(input) where input.response.status == 401 AND NOT tokenRefreshAttempted(input)_
    - _Expected_Behavior: Token refresh attempted before sign-out, request retried with new token_
    - _Preservation: Failed token refresh still redirects to login_
    - _Requirements: 2.5_

  - [x] 6.2 Add sign-out fallback after failed refresh
    - Wrap refresh logic in try-catch
    - If refresh throws or new token is unavailable, log "Token refresh failed — signing out"
    - Call `await signOut()` and `window.location.href = '/login'`
    - Only sign out after refresh attempt fails
    - _Requirements: 2.5, 3.2_

  - [x] 6.3 Preserve existing 401 debug logging
    - Move debug logging before retry block so it still executes
    - Keep development-mode logging for "Missing Authentication Token" errors
    - _Requirements: 2.5_

  - [x] 6.4 Verify Fix 4 exploration test now passes
    - **Property 1: Expected Behavior** - Token Refresh Before Sign-Out
    - **IMPORTANT**: Re-run the SAME test from task 1 (Cause 4 case) - do NOT write a new test
    - Run bug condition exploration test for Cause 4 (401 handling)
    - **EXPECTED OUTCOME**: Test PASSES (confirms token refresh is attempted)
    - _Requirements: 2.5_

- [x] 7. Fix 5 — Trigger prediction after upload in Dashboard.tsx

  - [x] 7.1 Add predictionRefreshKey state to Dashboard
    - Add `const [predictionRefreshKey, setPredictionRefreshKey] = useState(0)`
    - State will trigger PredictionCharts reload when incremented
    - _Bug_Condition: isBugCondition(input) where input.event == UPLOAD_COMPLETE AND NOT predictionEndpointCalled(input)_
    - _Expected_Behavior: Prediction endpoint called after upload, charts refreshed_
    - _Preservation: Failed uploads do not trigger prediction_
    - _Requirements: 2.3, 2.6_

  - [x] 7.2 Create handleUploadComplete callback
    - Define `handleUploadComplete = useCallback(async (projectId: string, documentId: string) => { ... }, [])`
    - Set `activeProjectId` to the uploaded document's project ID
    - Call `await apiEndpoints.createDelayPrediction(projectId)` to trigger prediction
    - Wrap in try-catch; log warning if prediction trigger fails (non-fatal)
    - Increment `predictionRefreshKey` to signal charts to reload
    - _Requirements: 2.3, 2.6_

  - [x] 7.3 Wire callback to DocumentUpload
    - Pass `onUploadComplete={handleUploadComplete}` to `<DocumentUpload>` in upload view
    - Callback will fire after successful S3 upload
    - _Requirements: 2.3, 2.6_

  - [x] 7.4 Add refreshKey prop to PredictionCharts
    - Add `refreshKey?: number` to `PredictionChartsProps` interface
    - Add `props.refreshKey` to `useEffect` dependency array for `loadPredictions`
    - Component will re-fetch when refreshKey changes
    - _Requirements: 2.6_

  - [x] 7.5 Wire refreshKey prop in Dashboard
    - Pass `refreshKey={predictionRefreshKey}` to `<PredictionCharts>` in dashboard view
    - Charts will reload when key increments after upload
    - _Requirements: 2.6_

  - [x] 7.6 Verify Fix 5 exploration test now passes
    - **Property 1: Expected Behavior** - Prediction Triggered After Upload
    - **IMPORTANT**: Re-run the SAME test from task 1 (Cause 2 & 5 cases) - do NOT write a new test
    - Run bug condition exploration test for Cause 2 & 5 (prediction trigger)
    - **EXPECTED OUTCOME**: Test PASSES (confirms prediction is triggered)
    - _Requirements: 2.3, 2.6_

## Phase 3: Validation

- [x] 8. Verify all preservation tests still pass
  - **Property 2: Preservation** - Non-Buggy Behavior Unchanged
  - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
  - Run preservation property tests from Phase 1
  - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
  - Confirm all preservation requirements are satisfied:
    - Non-empty predictions render correctly
    - Failed uploads do not trigger predictions
    - Non-401 errors do not trigger sign-out
    - Unauthenticated access redirects to login
    - File validation errors prevent upload
    - Async document status updates work
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 9. Run integration tests
  - Test full upload-to-dashboard flow: upload file → verify prediction API called → verify PredictionCharts re-renders with refreshed data
  - Test session expiry recovery: simulate expired token (401) → verify token refresh → verify original request completes → verify user remains on current page
  - Test switching between dashboard views: navigate to Upload, upload file, navigate back to Dashboard → verify prediction charts show updated project ID
  - Test empty project state: load dashboard with no uploads → verify empty-state message shown in prediction charts, no crash
  - _Requirements: All_

- [x] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - All 5 fixes implemented and validated
  - All bug condition tests pass (exploration tests from Phase 1 now pass)
  - All preservation tests pass (no regressions)
  - Integration tests pass (end-to-end flows work correctly)
