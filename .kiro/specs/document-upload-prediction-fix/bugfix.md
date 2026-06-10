# Bugfix Requirements Document

## Introduction

When a user uploads a document in the frontend, the application fails to use the uploaded document data for predictions and analysis. Instead, the dashboard displays "Using demo data - backend is not available." This bug has multiple contributing causes:

1. **Missing mock data constants**: `PredictionCharts.tsx` references `mockDashboardData`, `mockWorkloadData`, and `mockConfidenceData` that are never defined in the file, causing runtime errors when the fallback path is reached.
2. **No post-upload prediction refresh**: After a successful document upload, the frontend does not trigger a new prediction run or refresh the dashboard — the prediction charts remain disconnected from the uploaded content.
3. **Hardcoded project ID in predictions**: `PredictionCharts.tsx` uses a hardcoded `projectId` constant, so predictions are never fetched for the project associated with the uploaded document.
4. **Aggressive 401 sign-out**: The API client signs the user out and redirects to `/login` on any 401 response, preventing meaningful error recovery and masking the real connectivity failure.
5. **No S3-to-prediction pipeline linkage in the frontend**: The document upload flow completes the S3 upload but does not call the prediction endpoint to generate analysis from the newly uploaded document content.

The combined effect is that every document upload either silently fails to produce predictions or crashes the prediction chart component, leaving users with hardcoded demo data and no actionable feedback.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a user uploads a document and the backend prediction API returns an empty predictions array THEN the system attempts to reference undefined variables (`mockDashboardData`, `mockWorkloadData`, `mockConfidenceData`) causing a runtime error in `PredictionCharts.tsx`

1.2 WHEN a user uploads a document and the backend prediction API call throws an error THEN the system attempts to reference the same undefined mock data variables and displays "Using demo data - backend is not available."

1.3 WHEN a user successfully uploads a document THEN the system does not call the prediction endpoint to generate new predictions from the uploaded document content

1.4 WHEN the prediction charts load THEN the system fetches prediction history using a hardcoded project ID (`770e8400-e29b-41d4-a716-446655440002`) regardless of which project the uploaded document belongs to

1.5 WHEN the backend API returns a 401 Unauthorized response THEN the system immediately signs the user out and redirects to `/login` instead of surfacing a recoverable error or retrying with a refreshed token

1.6 WHEN a document upload completes successfully THEN the system shows "File uploaded and saved to backend" but does not refresh the prediction charts or health score card with data derived from the uploaded document

### Expected Behavior (Correct)

2.1 WHEN a user uploads a document and the backend prediction API returns an empty predictions array THEN the system SHALL display a defined empty-state UI (e.g., "No predictions yet — upload a document to get started") without referencing undefined variables

2.2 WHEN a user uploads a document and the backend prediction API call throws an error THEN the system SHALL display a clear error message using only defined fallback data structures, without crashing the component

2.3 WHEN a user successfully uploads a document THEN the system SHALL automatically trigger a prediction run for the associated project and refresh the prediction charts with the newly generated results

2.4 WHEN the prediction charts load THEN the system SHALL use the project ID associated with the most recently uploaded document (or the authenticated user's active project) rather than a hardcoded constant

2.5 WHEN the backend API returns a 401 Unauthorized response THEN the system SHALL attempt to refresh the Cognito session token and retry the request before signing the user out, and SHALL only redirect to `/login` if the token refresh also fails

2.6 WHEN a document upload completes successfully THEN the system SHALL refresh the prediction charts and health score card to reflect analysis derived from the uploaded document content

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the backend API is genuinely unavailable (network timeout, 5xx error) THEN the system SHALL CONTINUE TO display a graceful fallback state with an appropriate user-facing message

3.2 WHEN a user's authentication token is expired and cannot be refreshed THEN the system SHALL CONTINUE TO redirect the user to the login page

3.3 WHEN no document has been uploaded yet THEN the system SHALL CONTINUE TO display the empty-state or demo-data placeholder on the dashboard

3.4 WHEN a document upload fails due to an invalid file type or file size exceeding the limit THEN the system SHALL CONTINUE TO display the validation error and prevent the upload

3.5 WHEN the user is not authenticated THEN the system SHALL CONTINUE TO block access to protected routes and redirect to the login page

3.6 WHEN the backend document processing pipeline (S3 trigger → Textract → DynamoDB) completes asynchronously THEN the system SHALL CONTINUE TO update the document status in the uploaded files list without requiring a page reload
