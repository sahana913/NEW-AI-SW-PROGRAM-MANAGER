# Report Generation Service

This service provides automated report generation capabilities for the AI SW Program Manager platform, including weekly status reports and executive summaries.

## Features

### Weekly Status Reports
- Aggregates project health scores, RAG status, and key metrics
- Includes completed and upcoming milestones
- Lists active risk alerts with AI-generated explanations
- Displays velocity trends and backlog status with charts
- Provides prediction insights for delays and workload
- Generates AI-powered narrative summaries using Amazon Bedrock

### Executive Summaries
- Portfolio-level overview across multiple projects
- Filters for High and Critical risks only
- Concise format (maximum 500 words)
- Includes trend indicators for key metrics
- Focuses on executive-level decision points

### Report Customization
- Support for section selection in custom reports
- Ad-hoc report generation on demand
- Scheduled report generation (via EventBridge)
- Multiple format support (HTML, with PDF planned)

## Components

### Data Aggregator (`data_aggregator.py`)
Queries and aggregates data from multiple sources:
- RDS PostgreSQL: Projects, sprints, milestones, backlog, resources
- DynamoDB: Risks, predictions, health scores
- Combines data for comprehensive reporting

### Narrative Generator (`narrative_generator.py`)
Uses Amazon Bedrock (Claude) to generate:
- Weekly status report narratives
- Executive summaries (max 500 words)
- Context-aware, actionable insights

### Report Renderer (`report_renderer.py`)
Renders HTML reports with:
- Professional styling and layout
- Embedded charts (velocity trends, backlog status, risk distribution)
- Responsive design for various screen sizes
- Base64-encoded PNG charts using matplotlib

### Report Storage (`report_storage.py`)
Manages report persistence:
- Stores HTML reports in S3 with tenant isolation
- Stores metadata in DynamoDB
- Generates pre-signed URLs (24-hour expiration)
- Handles report lifecycle and cleanup

### Handler (`handler.py`)
Lambda handlers for:
- `generate_weekly_status_report_handler`: Generate weekly status reports
- `generate_executive_summary_handler`: Generate executive summaries
- `get_report_handler`: Retrieve report metadata
- `list_reports_handler`: List reports with filtering

## API Endpoints

### Generate Weekly Status Report
```
POST /reports/weekly-status
Query Parameters:
  - projectIds (optional): Comma-separated project IDs
  - format (optional): HTML (default) or PDF
  - sections (optional): Comma-separated section names

Response:
{
  "reportId": "uuid",
  "reportType": "WEEKLY_STATUS",
  "status": "COMPLETED",
  "downloadUrl": "https://...",
  "expiresAt": "2024-01-15T12:00:00Z",
  "generatedAt": "2024-01-14T12:00:00Z"
}
```

### Generate Executive Summary
```
POST /reports/executive-summary
Query Parameters:
  - projectIds (optional): Comma-separated project IDs (portfolio if omitted)
  - format (optional): HTML (default) or PDF

Response:
{
  "reportId": "uuid",
  "reportType": "EXECUTIVE_SUMMARY",
  "status": "COMPLETED",
  "downloadUrl": "https://...",
  "expiresAt": "2024-01-15T12:00:00Z",
  "generatedAt": "2024-01-14T12:00:00Z"
}
```

### Get Report
```
GET /reports/{reportId}

Response:
{
  "reportId": "uuid",
  "reportType": "WEEKLY_STATUS",
  "status": "COMPLETED",
  "downloadUrl": "https://...",
  "expiresAt": "2024-01-15T12:00:00Z",
  "generatedAt": "2024-01-14T12:00:00Z",
  "format": "HTML",
  "projectIds": ["uuid1", "uuid2"]
}
```

### List Reports
```
GET /reports
Query Parameters:
  - reportType (optional): WEEKLY_STATUS or EXECUTIVE_SUMMARY
  - limit (optional): Maximum results (default 50)

Response:
{
  "reports": [...],
  "count": 10
}
```

## Environment Variables

- `BEDROCK_MODEL_ID`: Bedrock model ID (default: anthropic.claude-3-sonnet-20240229-v1:0)
- `BEDROCK_REGION`: AWS region for Bedrock (default: us-east-1)
- `REPORTS_TABLE`: DynamoDB table for report metadata (default: ai-sw-pm-reports)
- `REPORTS_BUCKET`: S3 bucket for report storage (default: ai-sw-pm-reports-bucket)
- `RISKS_TABLE`: DynamoDB table for risks (default: ai-sw-pm-risks)
- `PREDICTIONS_TABLE`: DynamoDB table for predictions (default: ai-sw-pm-predictions)
- `DB_SECRET_NAME`: Secrets Manager secret for RDS credentials
- `DB_HOST`: RDS PostgreSQL host
- `DB_PORT`: RDS PostgreSQL port (default: 5432)
- `DB_NAME`: RDS database name (default: ai_sw_program_manager)

## Correctness Properties Validated

- **Property 37**: Report Content Completeness - Weekly status reports include all required sections
- **Property 38**: Report Metadata Persistence - Reports stored with timestamp and metadata
- **Property 39**: Report Section Customization - Support for custom section selection
- **Property 40**: Executive Summary Length Constraint - Max 500 words
- **Property 41**: Executive Summary Content - Includes RAG status, risks, decisions, budget/schedule
- **Property 42**: Executive Risk Filtering - Only High and Critical risks in executive summaries
- **Property 43**: Trend Indicator Inclusion - Trend indicators for key metrics
- **Property 46**: Download Link Expiration - Pre-signed URLs expire after 24 hours

## Chart Generation

The service uses matplotlib to generate charts:
- **Velocity Trends**: Line chart showing sprint velocity over time
- **Backlog Status**: Stacked bar chart showing backlog composition by type
- **Risk Distribution**: Pie chart showing risk distribution by severity

Charts are rendered as PNG images, base64-encoded, and embedded directly in HTML reports.

## Scheduled Report Generation

Reports can be scheduled using Amazon EventBridge:
1. Create EventBridge rule with cron expression (e.g., weekly on Monday at 8 AM)
2. Configure rule to invoke report generation Lambda
3. Specify target recipients and distribution list
4. Reports are automatically generated and distributed via email (future enhancement)

## Security

- **Tenant Isolation**: All reports are tenant-scoped with S3 prefix isolation
- **Access Control**: Pre-signed URLs with 24-hour expiration
- **Encryption**: S3 server-side encryption (AES-256)
- **Authentication**: Lambda authorizer validates JWT tokens
- **Authorization**: Tenant ID validation on all operations

## Future Enhancements

1. PDF export support (using WeasyPrint or Puppeteer)
2. Email distribution via Amazon SES
3. Report scheduling management API
4. Custom branding (tenant logos and colors)
5. Interactive charts (using Plotly instead of matplotlib)
6. Report templates and customization
7. Multi-language support
8. Report comparison and diff views
