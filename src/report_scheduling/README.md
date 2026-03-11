# Report Scheduling Service

This service manages scheduled report generation and distribution for the AI SW Program Manager platform.

## Overview

The Report Scheduling Service allows users to configure automated report generation and email distribution on recurring schedules. It uses Amazon EventBridge to trigger report generation at specified intervals (daily, weekly, monthly).

## Requirements Validated

- **Requirement 14.1**: Generate weekly status reports automatically every Monday at 8:00 AM UTC
- **Requirement 17.1**: Support configuring email distribution lists per report type
- **Requirement 17.2**: Send scheduled reports to configured distribution list
- **Requirement 17.5**: Support email scheduling at daily, weekly, or monthly intervals

## Architecture

### Components

1. **handler.py**: Main Lambda handlers for schedule CRUD operations
   - `schedule_report_handler`: Create a new report schedule
   - `get_schedule_handler`: Retrieve schedule details
   - `list_schedules_handler`: List all schedules for a tenant
   - `update_schedule_handler`: Update schedule configuration
   - `delete_schedule_handler`: Delete a schedule

2. **scheduled_execution_handler.py**: EventBridge-triggered handler
   - Executes scheduled reports
   - Generates report via report generation service
   - Distributes report via email distribution service
   - Updates schedule last run time

### Data Flow

```
1. User creates schedule via API
   ↓
2. Schedule stored in DynamoDB
   ↓
3. EventBridge rule created with cron expression
   ↓
4. EventBridge triggers scheduled_execution_handler at specified time
   ↓
5. Handler generates report (invokes report generation Lambda)
   ↓
6. Handler distributes report (invokes email distribution Lambda)
   ↓
7. Schedule last run time updated in DynamoDB
```

## API Endpoints

### POST /reports/schedules

Create a new report schedule.

**Request Body:**
```json
{
  "tenantId": "tenant-123",
  "reportType": "WEEKLY_STATUS",
  "schedule": "cron(0 8 ? * MON *)",
  "recipients": ["user1@example.com", "user2@example.com"],
  "projectIds": ["proj-1", "proj-2"],
  "format": "PDF"
}
```

**Response:**
```json
{
  "scheduleId": "schedule-456",
  "reportType": "WEEKLY_STATUS",
  "schedule": "cron(0 8 ? * MON *)",
  "recipients": ["user1@example.com", "user2@example.com"],
  "projectIds": ["proj-1", "proj-2"],
  "format": "PDF",
  "status": "ACTIVE",
  "nextRunTime": "2024-01-08T08:00:00Z",
  "createdAt": "2024-01-01T10:00:00Z"
}
```

### GET /reports/schedules/{scheduleId}

Retrieve schedule details.

**Response:**
```json
{
  "scheduleId": "schedule-456",
  "reportType": "WEEKLY_STATUS",
  "schedule": "cron(0 8 ? * MON *)",
  "recipients": ["user1@example.com"],
  "status": "ACTIVE",
  "nextRunTime": "2024-01-08T08:00:00Z",
  "lastRunTime": "2024-01-01T08:00:00Z",
  "createdAt": "2024-01-01T10:00:00Z"
}
```

### GET /reports/schedules

List all schedules for a tenant.

**Query Parameters:**
- `status` (optional): Filter by status (ACTIVE, PAUSED)
- `reportType` (optional): Filter by report type

**Response:**
```json
{
  "schedules": [
    {
      "scheduleId": "schedule-456",
      "reportType": "WEEKLY_STATUS",
      "schedule": "cron(0 8 ? * MON *)",
      "recipients": ["user1@example.com"],
      "status": "ACTIVE",
      "nextRunTime": "2024-01-08T08:00:00Z",
      "lastRunTime": "2024-01-01T08:00:00Z"
    }
  ],
  "count": 1
}
```

### PUT /reports/schedules/{scheduleId}

Update a schedule.

**Request Body:**
```json
{
  "status": "PAUSED",
  "recipients": ["new@example.com"],
  "schedule": "cron(0 9 ? * MON *)"
}
```

**Response:**
```json
{
  "scheduleId": "schedule-456",
  "reportType": "WEEKLY_STATUS",
  "schedule": "cron(0 9 ? * MON *)",
  "recipients": ["new@example.com"],
  "status": "PAUSED",
  "nextRunTime": "2024-01-08T09:00:00Z",
  "updatedAt": "2024-01-02T10:00:00Z"
}
```

### DELETE /reports/schedules/{scheduleId}

Delete a schedule.

**Response:**
```json
{
  "message": "Schedule deleted successfully",
  "scheduleId": "schedule-456"
}
```

## Schedule Expressions

The service supports EventBridge schedule expressions:

### Cron Expressions

Format: `cron(Minutes Hours Day-of-month Month Day-of-week Year)`

Examples:
- `cron(0 8 ? * MON *)` - Every Monday at 8:00 AM UTC
- `cron(0 9 1 * ? *)` - First day of every month at 9:00 AM UTC
- `cron(0 18 ? * MON-FRI *)` - Every weekday at 6:00 PM UTC
- `cron(0 0 * * ? *)` - Every day at midnight UTC

### Rate Expressions

Format: `rate(value unit)`

Examples:
- `rate(1 day)` - Every day
- `rate(7 days)` - Every 7 days
- `rate(1 hour)` - Every hour

## DynamoDB Schema

### ReportSchedules Table

```
PK: TENANT#{tenantId}
SK: SCHEDULE#{scheduleId}

Attributes:
- scheduleId: string
- tenantId: string
- reportType: string (WEEKLY_STATUS, EXECUTIVE_SUMMARY)
- schedule: string (cron or rate expression)
- recipients: list of strings
- projectIds: list of strings (optional)
- format: string (PDF, HTML)
- status: string (ACTIVE, PAUSED)
- ruleName: string (EventBridge rule name)
- nextRunTime: string (ISO 8601 timestamp)
- lastRunTime: string (ISO 8601 timestamp)
- createdAt: string (ISO 8601 timestamp)
- updatedAt: string (ISO 8601 timestamp)
```

## EventBridge Integration

### Rule Creation

When a schedule is created:
1. EventBridge rule is created with the specified schedule expression
2. Rule name format: `report-schedule-{scheduleId}`
3. Target is set to `scheduled_execution_handler` Lambda
4. Input includes tenant_id, schedule_id, report_type, recipients, etc.

### Rule Management

- **Enable/Disable**: When schedule status changes to ACTIVE/PAUSED
- **Update**: When schedule expression is modified
- **Delete**: When schedule is deleted

## Error Handling

### Validation Errors
- Invalid schedule expression
- Missing required fields
- Invalid report type
- Empty recipients list

### Runtime Errors
- EventBridge rule creation failure
- DynamoDB operation failure
- Lambda invocation failure

All errors are logged with context and returned as appropriate HTTP status codes.

## Monitoring

### CloudWatch Logs
- All Lambda invocations logged
- Schedule creation/update/deletion events
- EventBridge rule management operations
- Report generation and distribution results

### CloudWatch Metrics
- Schedule execution count
- Schedule execution failures
- Report generation duration
- Email distribution success rate

## Security

### Tenant Isolation
- All schedules scoped to tenant_id
- EventBridge rules include tenant_id in input
- DynamoDB queries filtered by tenant partition key

### IAM Permissions
Required permissions:
- `events:PutRule` - Create EventBridge rules
- `events:PutTargets` - Add Lambda targets to rules
- `events:EnableRule` - Enable rules
- `events:DisableRule` - Disable rules
- `events:DeleteRule` - Delete rules
- `events:RemoveTargets` - Remove targets from rules
- `lambda:InvokeFunction` - Invoke report generation and email distribution Lambdas
- `dynamodb:PutItem` - Create schedules
- `dynamodb:GetItem` - Retrieve schedules
- `dynamodb:Query` - List schedules
- `dynamodb:UpdateItem` - Update schedules
- `dynamodb:DeleteItem` - Delete schedules

## Testing

### Unit Tests
Test individual functions:
- Schedule validation
- EventBridge rule creation
- DynamoDB operations
- Schedule expression parsing

### Integration Tests
Test end-to-end flows:
- Create schedule → EventBridge rule created
- Schedule triggers → Report generated and distributed
- Update schedule → EventBridge rule updated
- Delete schedule → EventBridge rule deleted

## Future Enhancements

1. **Advanced Scheduling**
   - Support for timezone-specific schedules
   - Holiday exclusions
   - Business day only schedules

2. **Schedule Templates**
   - Pre-configured schedule templates
   - Organization-wide default schedules

3. **Notification Preferences**
   - Per-user notification preferences
   - Delivery time preferences
   - Format preferences

4. **Schedule Analytics**
   - Execution history
   - Delivery success rates
   - Recipient engagement metrics
