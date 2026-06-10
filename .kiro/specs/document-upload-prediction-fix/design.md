# Document Upload Prediction Fix — Bugfix Design

## Overview

After a user uploads a document, the dashboard should automatically trigger prediction analysis and refresh the prediction charts with results derived from the uploaded content. Instead, the application crashes with a `ReferenceError` (undefined mock data constants), silently skips the prediction trigger, fetches predictions for the wrong project, and aggressively signs the user out on any 401 response.

This design covers five targeted fixes:

1. **Define fallback data constants** in `PredictionCharts.tsx` to eliminate the `ReferenceError` on the empty-predictions path.
2. **Trigger predictions after upload** in `DocumentUpload.tsx` by calling the prediction endpoints and refreshing the dashboard once the S3 upload completes.
3. **Replace the hardcoded project ID** in `PredictionCharts.tsx` with a dynamic value sourced from the uploaded document or the user's active project.
4. **Soften the 401 handler** in `api.ts` to attempt a Cognito token refresh before signing the user out.
5. **Link the S3 upload to the prediction pipeline** in the frontend by wiring the upload completion callback to the prediction and dashboard refresh calls.

Each fix is minimal and scoped to the defective code path. No existing behavior for non-buggy inputs is changed.

---

## Glossary

- **Bug_Condition (C)**: The set of inputs and states that trigger one or more of the five defects described above.
- **Property (P)**: The desired correct behavior when the bug condition holds — predictions are triggered, charts render without crashing, and the correct project ID is used.
- **Preservation**: Existing behaviors that must remain unchanged — graceful fallback on genuine backend unavailability, redirect to login when token refresh fails, validation errors on bad uploads, and the async document processing status updates.
- **`PredictionCharts`**: The React component in `frontend/src/components/Dashboard/PredictionCharts.tsx` that fetches and renders prediction history charts.
- **`DocumentUpload`**: The React component in `frontend/src/components/Documents/DocumentUpload.tsx` that handles file selection, validation, and S3 upload.
- **`api.ts`**: The Axios instance and endpoint definitions in `frontend/src/services/api.ts`, including the request/response interceptors.
- **`uploadFile`**: The async function inside `DocumentUpload` that calls `apiEndpoints.uploadDocument` and updates file state on completion.
- **`loadPredictions`**: The async function inside `PredictionCharts` that calls `apiEndpoints.getPredictionHistory` for both DELAY and WORKLOAD types.
- **`DEFAULT_PROJECT_ID`**: The hardcoded UUID `770e8400-e29b-41d4-a716-446655440002` currently used in both `DocumentUpload.tsx` and `PredictionCharts.tsx`.
- **`onUploadComplete`**: A new optional callback prop added to `DocumentUpload` to notify the parent (`Dashboard`) when an upload succeeds, carrying the `projectId` and `documentId`.

---

## Bug Details

### Bug Condition

The bug manifests across five distinct but related code paths, all triggered by the document upload flow or its downstream effects.

**Formal Specification:**

```
FUNCTION isBugCondition(input)
  INPUT: input of type { event: AppEvent, state: AppState }
  OUTPUT: boolean

  // Cause 1: PredictionCharts renders with empty or errored prediction API response
  IF input.event == LOAD_PREDICTIONS
     AND (apiReturnsEmptyPredictions(input) OR apiThrowsError(input))
  THEN RETURN true   // mockDashboardData etc. are undefined → ReferenceError

  // Cause 2 & 5: Upload completes but no prediction trigger follows
  IF input.event == UPLOAD_COMPLETE
     AND input.state.uploadStatus == 'success'
     AND NOT predictionEndpointCalled(input)
  THEN RETURN true

  // Cause 3: PredictionCharts fetches with hardcoded project ID
  IF input.event == LOAD_PREDICTIONS
     AND projectIdUsed(input) == HARDCODED_UUID
     AND input.state.activeProjectId != HARDCODED_UUID
  THEN RETURN true

  // Cause 4: API interceptor receives 401 and immediately signs out
  IF input.event == API_RESPONSE
     AND input.response.status == 401
     AND NOT tokenRefreshAttempted(input)
  THEN RETURN true

  RETURN false
END FUNCTION
```

### Examples

- **Cause 1 — ReferenceError**: User uploads a document; backend returns `{ predictions: [] }`. `PredictionCharts` enters the `if (allPredictions.length === 0)` branch and executes `setDelayData(mockDashboardData.predictions)` — `mockDashboardData` is not defined, throwing `ReferenceError: mockDashboardData is not defined`. The chart component crashes.
- **Cause 1 — Error path**: Backend is unreachable; the `catch` block executes `setDelayData(mockDashboardData.predictions)` — same `ReferenceError`.
- **Cause 2 & 5 — Silent no-op**: User uploads a valid PDF; `uploadFile` resolves with `{ savedToBackend: true, documentId: 'abc-123' }`. The file status is set to `'completed'` but no prediction endpoint is called and the dashboard charts are not refreshed.
- **Cause 3 — Wrong project**: User's active project ID is `proj-999`. `PredictionCharts` calls `getPredictionHistory('770e8400-e29b-41d4-a716-446655440002', 'DELAY')` — returns predictions for a different (possibly non-existent) project, showing stale or empty data.
- **Cause 4 — Premature sign-out**: Cognito ID token expires mid-session; the next API call returns 401. The interceptor immediately calls `signOut()` and redirects to `/login` without attempting `fetchAuthSession()` to get a fresh token.

---

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- WHEN the backend API is genuinely unavailable (network timeout, 5xx error) THEN the system SHALL continue to display a graceful fallback state with a user-facing message — no crash, no undefined variable reference.
- WHEN a user's authentication token is expired AND a token refresh also fails THEN the system SHALL continue to redirect the user to `/login`.
- WHEN no document has been uploaded yet THEN the system SHALL continue to display the empty-state placeholder on the dashboard (no predictions, no crash).
- WHEN a document upload fails due to invalid file type or file size exceeding the limit THEN the system SHALL continue to display the validation error and prevent the upload — no prediction trigger on failed uploads.
- WHEN the user is not authenticated THEN the system SHALL continue to block access to protected routes and redirect to the login page.
- WHEN the backend document processing pipeline (S3 trigger → Textract → DynamoDB) completes asynchronously THEN the system SHALL continue to update the document status in the uploaded files list without requiring a page reload.

**Scope:**

All inputs that do NOT involve the five bug conditions above are completely unaffected by this fix. Specifically:
- Mouse interactions with the dashboard (clicking "Run Prediction", changing time range)
- Successful API calls that return non-empty predictions
- Non-401 API errors (4xx other than 401, 5xx)
- Document uploads that fail validation before reaching the S3 PUT step

---

## Hypothesized Root Cause

### Cause 1 — Undefined Mock Constants

`PredictionCharts.tsx` was refactored to fetch live data but the fallback mock data objects (`mockDashboardData`, `mockWorkloadData`, `mockConfidenceData`) were removed from the file without replacing the references in the empty-predictions and error branches. The component now references identifiers that do not exist in scope.

### Cause 2 & 5 — Missing Post-Upload Prediction Trigger

`DocumentUpload.tsx` was designed as a standalone upload widget. The `uploadFile` function updates local file state on success but has no mechanism to notify the parent component or call the prediction API. The `Dashboard` component renders `<DocumentUpload />` and `<PredictionCharts />` as siblings with no shared state or callback wiring between them. The S3 upload completes but the prediction pipeline is never invoked from the frontend.

### Cause 3 — Hardcoded Project ID

During initial development, a placeholder project UUID was hardcoded in `PredictionCharts.tsx` (and also in `DocumentUpload.tsx` as `DEFAULT_PROJECT_ID`). This was never replaced with a dynamic value. The prediction history query therefore always targets the same fixed project regardless of which project the user is working on.

### Cause 4 — Aggressive 401 Sign-Out

The Axios response interceptor in `api.ts` treats every 401 as a terminal authentication failure and immediately calls `signOut()`. Cognito ID tokens have a 1-hour expiry; after expiry, the next API call returns 401. The correct behavior is to call `fetchAuthSession({ forceRefresh: true })` to obtain a new ID token and retry the original request before giving up and signing out.

---

## Correctness Properties

Property 1: Bug Condition — Prediction Charts Render Without Crash on Empty or Error Response

_For any_ state where the prediction API returns an empty predictions array OR throws an error, the fixed `PredictionCharts` component SHALL render a defined empty-state UI (using only defined fallback data structures) without throwing a `ReferenceError` or crashing the component.

**Validates: Requirements 2.1, 2.2**

Property 2: Bug Condition — Prediction Trigger After Successful Upload

_For any_ successful document upload (S3 PUT returns 2xx and `savedToBackend` is true), the fixed `DocumentUpload` component SHALL call the prediction endpoint (`createDelayPrediction`) for the uploaded document's project ID and SHALL invoke the dashboard refresh callback, causing `PredictionCharts` to reload with updated data.

**Validates: Requirements 2.3, 2.6**

Property 3: Bug Condition — Dynamic Project ID in Prediction Fetch

_For any_ state where `PredictionCharts` loads and an active project ID is available (from props or context), the fixed component SHALL use that dynamic project ID when calling `getPredictionHistory`, and SHALL NOT use the hardcoded UUID `770e8400-e29b-41d4-a716-446655440002`.

**Validates: Requirement 2.4**

Property 4: Bug Condition — Token Refresh Before Sign-Out on 401

_For any_ API response with status 401, the fixed interceptor SHALL first attempt `fetchAuthSession({ forceRefresh: true })` and retry the original request with the new token. The interceptor SHALL only call `signOut()` and redirect to `/login` if the token refresh itself fails or the retried request also returns 401.

**Validates: Requirement 2.5**

Property 5: Preservation — Non-Buggy Inputs Produce Identical Behavior

_For any_ input where the bug condition does NOT hold (successful prediction fetch with non-empty results, non-401 API errors, failed uploads, unauthenticated access), the fixed code SHALL produce exactly the same behavior as the original code, preserving all existing functionality.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

---

## Fix Implementation

### Fix 1 — Define Fallback Data Constants in `PredictionCharts.tsx`

**File**: `AI-SW-Program-Manager/frontend/src/components/Dashboard/PredictionCharts.tsx`

**Specific Changes**:

1. **Add defined fallback constants** at the top of the file (before the component), replacing the undefined references:

```typescript
const EMPTY_DELAY_DATA: any[] = [];
const EMPTY_WORKLOAD_DATA: any[] = [];
const EMPTY_CONFIDENCE_DATA = [
  { name: 'High Confidence', value: 0, color: '#4caf50' },
  { name: 'Medium Confidence', value: 0, color: '#ff9800' },
  { name: 'Low Confidence', value: 0, color: '#f44336' },
];
```

2. **Replace all references** to `mockDashboardData.predictions`, `mockWorkloadData`, and `mockConfidenceData` in both the empty-predictions branch and the `catch` block with the new constants above.

3. **Update the empty-state message** to be actionable: `'No predictions yet — upload a document to get started.'` (instead of the misleading "Using demo data - backend is not available.").

### Fix 2 — Add `onUploadComplete` Callback Prop to `DocumentUpload.tsx`

**File**: `AI-SW-Program-Manager/frontend/src/components/Documents/DocumentUpload.tsx`

**Specific Changes**:

1. **Add an optional `onUploadComplete` prop** to the component interface:

```typescript
interface DocumentUploadProps {
  onUploadComplete?: (projectId: string, documentId: string) => void;
}
```

2. **Call `onUploadComplete`** at the end of the success path in `uploadFile`, after the file state is updated to `'completed'`:

```typescript
if (result.documentId && props.onUploadComplete) {
  props.onUploadComplete(DEFAULT_PROJECT_ID, result.documentId);
}
```

3. **Note**: `DEFAULT_PROJECT_ID` will be replaced by Fix 3 with a dynamic value. The callback is the integration point; the project ID source is addressed separately.

### Fix 3 — Replace Hardcoded Project ID with Dynamic Value

**Files**:
- `AI-SW-Program-Manager/frontend/src/components/Dashboard/PredictionCharts.tsx`
- `AI-SW-Program-Manager/frontend/src/components/Dashboard/Dashboard.tsx`
- `AI-SW-Program-Manager/frontend/src/components/Documents/DocumentUpload.tsx`

**Specific Changes**:

1. **Add a `projectId` prop to `PredictionCharts`**:

```typescript
interface PredictionChartsProps {
  expanded?: boolean;
  projectId?: string;
}
```

Replace the hardcoded `const projectId = '770e8400-...'` with:

```typescript
const effectiveProjectId = props.projectId || '';
```

Use `effectiveProjectId` in all `apiEndpoints` calls. When `effectiveProjectId` is empty, skip the API call and show the empty-state UI directly.

2. **Add state to `Dashboard.tsx`** to track the active project ID:

```typescript
const [activeProjectId, setActiveProjectId] = useState<string>('');
```

3. **Wire the callback in `Dashboard.tsx`**: Pass `onUploadComplete` to `<DocumentUpload>` and update `activeProjectId` when it fires. Pass `activeProjectId` as the `projectId` prop to `<PredictionCharts>`:

```typescript
const handleUploadComplete = useCallback((projectId: string) => {
  setActiveProjectId(projectId);
  // PredictionCharts will re-fetch when projectId prop changes
}, []);

// In renderContent():
case 'upload':
  return <DocumentUpload onUploadComplete={handleUploadComplete} />;
// ...
case 'dashboard':
  // ...
  <PredictionCharts projectId={activeProjectId} />
```

4. **Fetch the user's active project on mount** in `Dashboard.tsx` using `apiEndpoints.getProjects()` to populate `activeProjectId` with the first available project, so the charts load correctly even before any upload in the current session.

### Fix 4 — Soften 401 Handler in `api.ts`

**File**: `AI-SW-Program-Manager/frontend/src/services/api.ts`

**Specific Changes**:

1. **Replace the immediate sign-out** in the 401 branch with a token-refresh-and-retry pattern:

```typescript
if (status === 401) {
  // Avoid infinite retry loops
  if (error.config._retried) {
    console.log('[API] Token refresh did not resolve 401 — signing out');
    await signOut();
    window.location.href = '/login';
    return Promise.reject(error);
  }

  try {
    console.log('[API] 401 received — attempting token refresh');
    const session = await fetchAuthSession({ forceRefresh: true });
    const newIdToken = session.tokens?.idToken?.toString();

    if (!newIdToken) {
      throw new Error('No ID token after refresh');
    }

    // Retry the original request with the refreshed token
    error.config._retried = true;
    error.config.headers.Authorization = `Bearer ${newIdToken}`;
    return api(error.config);
  } catch (refreshError) {
    console.log('[API] Token refresh failed — signing out', refreshError);
    await signOut();
    window.location.href = '/login';
    return Promise.reject(error);
  }
}
```

2. **Add `_retried` to the Axios config type** (or use a type assertion) to avoid TypeScript errors.

3. **Preserve all other 401 handling logic** (debug logging in development mode) — move it before the new retry block so it still executes.

### Fix 5 — Trigger Prediction After Upload (S3-to-Prediction Pipeline Linkage)

**File**: `AI-SW-Program-Manager/frontend/src/components/Dashboard/Dashboard.tsx`

**Specific Changes**:

1. **Expand `handleUploadComplete`** to call the prediction endpoint after a successful upload:

```typescript
const handleUploadComplete = useCallback(async (projectId: string, documentId: string) => {
  setActiveProjectId(projectId);
  try {
    // Trigger delay prediction for the newly uploaded document's project
    await apiEndpoints.createDelayPrediction(projectId);
  } catch (err) {
    // Non-fatal: prediction trigger failure should not block the UI
    console.warn('[Dashboard] Post-upload prediction trigger failed:', err);
  }
  // Signal PredictionCharts to reload by updating a refresh key
  setPredictionRefreshKey(prev => prev + 1);
}, []);
```

2. **Add a `refreshKey` prop to `PredictionCharts`** that causes `loadPredictions` to re-run when it changes:

```typescript
// In PredictionCharts:
interface PredictionChartsProps {
  expanded?: boolean;
  projectId?: string;
  refreshKey?: number;
}

useEffect(() => {
  loadPredictions();
}, [timeRange, effectiveProjectId, props.refreshKey]);
```

3. **Add `predictionRefreshKey` state to `Dashboard.tsx`**:

```typescript
const [predictionRefreshKey, setPredictionRefreshKey] = useState(0);
```

Pass it to `<PredictionCharts refreshKey={predictionRefreshKey} />`.

---

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate each bug on the unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate each bug BEFORE implementing the fix. Confirm or refute the root cause analysis.

**Test Plan**: Write unit tests that mock the API layer and render the affected components, asserting the defective behavior on unfixed code.

**Test Cases**:

1. **Cause 1 — Empty predictions crash**: Mock `getPredictionHistory` to return `{ predictions: [] }`. Render `PredictionCharts`. Assert that a `ReferenceError` is thrown (will fail on unfixed code, pass after Fix 1).
2. **Cause 1 — API error crash**: Mock `getPredictionHistory` to throw a network error. Render `PredictionCharts`. Assert that a `ReferenceError` is thrown (will fail on unfixed code, pass after Fix 1).
3. **Cause 2 — No prediction trigger after upload**: Mock `uploadDocument` to succeed. Render `DocumentUpload`. Simulate a file drop and upload. Assert that `createDelayPrediction` was NOT called (demonstrates the bug; after Fix 2+5 it WILL be called).
4. **Cause 3 — Hardcoded project ID**: Render `PredictionCharts` with `projectId="my-real-project"`. Assert that `getPredictionHistory` is called with `"770e8400-..."` (demonstrates the bug; after Fix 3 it will use `"my-real-project"`).
5. **Cause 4 — Immediate sign-out on 401**: Mock an API call to return 401. Assert that `signOut` is called immediately without any `fetchAuthSession` call (demonstrates the bug; after Fix 4 a refresh is attempted first).

**Expected Counterexamples**:
- `ReferenceError: mockDashboardData is not defined` in `PredictionCharts` on empty/error path.
- `createDelayPrediction` call count is 0 after a successful upload.
- `getPredictionHistory` called with hardcoded UUID regardless of `projectId` prop.
- `signOut` called without prior `fetchAuthSession({ forceRefresh: true })` on 401.

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed code produces the expected behavior.

**Pseudocode:**

```
FOR ALL input WHERE isBugCondition(input) DO
  result := fixedComponent(input)
  ASSERT expectedBehavior(result)
END FOR
```

**Test Cases**:

1. **Fix 1 — Empty state renders**: Mock empty predictions → assert component renders "No predictions yet" message, no crash.
2. **Fix 1 — Error state renders**: Mock API error → assert component renders error alert with defined message, no crash.
3. **Fix 2+5 — Prediction triggered after upload**: Mock successful upload → assert `createDelayPrediction` called with correct project ID.
4. **Fix 3 — Dynamic project ID**: Render with `projectId="proj-abc"` → assert `getPredictionHistory` called with `"proj-abc"`.
5. **Fix 4 — Token refresh on 401**: Mock 401 then successful refresh → assert `fetchAuthSession({ forceRefresh: true })` called, original request retried, `signOut` NOT called.
6. **Fix 4 — Sign-out after failed refresh**: Mock 401 then failed refresh → assert `signOut` called after refresh attempt.

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed code produces the same result as the original code.

**Pseudocode:**

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalBehavior(input) = fixedBehavior(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because it generates many test cases automatically across the input domain, catching edge cases that manual unit tests might miss.

**Test Cases**:

1. **Non-empty predictions render unchanged**: Mock `getPredictionHistory` to return 5 predictions → assert charts render with the same data as before the fix (no regression in the happy path).
2. **Failed upload does not trigger prediction**: Mock `uploadDocument` to throw → assert `createDelayPrediction` is NOT called and error state is shown.
3. **Non-401 errors not affected**: Mock API to return 500 → assert `signOut` is NOT called and error propagates normally.
4. **Unauthenticated access still blocked**: Render `Dashboard` without auth → assert redirect to `/login` still occurs.
5. **File validation still enforced**: Attempt to upload a `.exe` file → assert validation error shown, upload not attempted.
6. **Async document status updates preserved**: Mock document status polling → assert status chip updates from `'processing'` to `'completed'` without page reload.

### Unit Tests

- Test `PredictionCharts` renders empty-state UI when predictions array is empty (no crash).
- Test `PredictionCharts` renders error alert when API throws (no crash).
- Test `PredictionCharts` uses `projectId` prop in API calls, not hardcoded UUID.
- Test `DocumentUpload` calls `onUploadComplete` callback with correct `projectId` and `documentId` on success.
- Test `DocumentUpload` does NOT call `onUploadComplete` when upload fails.
- Test `api.ts` interceptor calls `fetchAuthSession({ forceRefresh: true })` on 401 before `signOut`.
- Test `api.ts` interceptor calls `signOut` only after token refresh fails.
- Test `api.ts` interceptor does not retry more than once (no infinite loop via `_retried` flag).
- Test `Dashboard` calls `createDelayPrediction` after `handleUploadComplete` fires.
- Test `Dashboard` passes updated `projectId` to `PredictionCharts` after upload.

### Property-Based Tests

- **Property 2 (Upload → Prediction)**: Generate random valid file objects and project IDs. For any successful upload, assert `createDelayPrediction` is called exactly once with the correct project ID.
- **Property 4 (401 Retry)**: Generate random API endpoints and request configs. For any 401 response where token refresh succeeds, assert `signOut` is never called and the request is retried exactly once.
- **Property 5 (Preservation — Non-empty predictions)**: Generate random prediction arrays with 1–100 items. For any non-empty array, assert the chart data state matches the mapped prediction values (same as original behavior).
- **Property 5 (Preservation — Non-401 errors)**: Generate random HTTP error status codes (400, 403, 404, 429, 500, 502, 503). For any non-401 status, assert `signOut` is never called.

### Integration Tests

- Test full upload-to-dashboard flow: upload a file → verify prediction API called → verify `PredictionCharts` re-renders with refreshed data.
- Test session expiry recovery: simulate expired token (401) → verify token refresh → verify original request completes → verify user remains on current page.
- Test switching between dashboard views: navigate to Upload, upload a file, navigate back to Dashboard → verify prediction charts show updated project ID.
- Test empty project state: load dashboard with no uploads → verify empty-state message shown in prediction charts, no crash.
