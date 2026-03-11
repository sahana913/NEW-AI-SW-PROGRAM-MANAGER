# Audit Logging Service

## Overview

The Audit Logging Service provides comprehensive audit trail capabilities for the AI SW Program Manager platform. It logs all authentication attempts, data modifications, and administrative actions to CloudWatch Logs and CloudTrail, ensuring compliance and security monitoring.

## Requirements Validated

- **Requirement 27.1**: Log all errors with severity level, timestamp, and context
- **Requirement 27.2**: Log all API requests with request ID, user ID, tenant ID, and response time
- **Requirement 28.1**: Log all authentication attempts to CloudTrail
- **Requirement 28.2**: Log all data modification operations with user ID, tenant ID, timestamp, and changed data
- **Requirement 28.3**: Log all administrative actions

## Components

### 1. handler.py

Main Lambda handler that processes audit events from EventBridge and direct invocations.

**Event Sources:**
- AWS Cognito (authentication events)
- EventBridge (custom events)
- Direct Lambda invocations

**Event Types:**
- Authentication attempts
- Data modifications
- Administrative actions

### 2. audit_publisher.py

Helper module for publishing audit events to EventBridge from other Lambda functions.

**Functions:**
- `publish_authentication_event()`: Publish authentication audit events
- `publish_data_modification_event()`: Publish data modification audit events
- `publish_admin_action_event()`: Publish administrative action audit events

## Usage

### Using the Logging Decorator

The easiest way to add audit logging to Lambda functions is to use the `with_audit_logging` decorator:

```python
from shared.decorators import with_audit_logging

@with_audit_logging
def handler(event, context):
    # Your Lambda function code
    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Success"})
    }
```

This decorator automatically:
- Logs all API requests with request ID, user ID, tenant ID, and response time
- Logs all errors with severity, timestamp, context, and stack trace
- Uses structured JSON logging format

### Publishing Audit Events

To publish audit events from your Lambda functions:

```python
from audit_logging.audit_publisher import (
    publish_authentication_event,
    publish_data_modification_event,
    publish_admin_action_event
)

# Authentication event
publish_authentication_event(
    user_id="user-123",
    email="user@example.com",
    success=True
)

# Data modification event
publish_data_modification_event(
    user_id="user-123",
    tenant_id="tenant-456",
    operation_type="UPDATE",
    entity_type="project",
    entity_id="project-789",
    changes={"status": "completed"}
)

# Administrative action event
publish_admin_action_event(
    admin_user_id="admin-123",
    action_type="USER_CREATED",
    affected_entities={"user_id": "user-456"},
    details={"role": "PROGRAM_MANAGER"}
)
```

### Direct Invocation

You can also invoke the audit logging Lambda directly:

```python
import boto3
import json

lambda_client = boto3.client('lambda')

response = lambda_client.invoke(
    FunctionName='audit-logging',
    InvocationType='Event',  # Async invocation
    Payload=json.dumps({
        'auditType': 'data_modification',
        'userId': 'user-123',
        'tenantId': 'tenant-456',
        'operationType': 'CREATE',
        'entityType': 'milestone',
        'entityId': 'milestone-789'
    })
)
```

## Log Format

All audit logs use structured JSON format:

### Authentication Log
```json
{
  "audit_type": "authentication",
  "user_id": "user-123",
  "email": "user@example.com",
  "success": true,
  "timestamp": "2024-01-15T10:30:00.000Z",
  "cloudtrail_event": true
}
```

### Data Modification Log
```json
{
  "audit_type": "data_modification",
  "user_id": "user-123",
  "tenant_id": "tenant-456",
  "operation_type": "UPDATE",
  "entity_type": "project",
  "entity_id": "project-789",
  "changes": {"status": "completed"},
  "timestamp": "2024-01-15T10:30:00.000Z",
  "cloudtrail_event": true
}
```

### Administrative Action Log
```json
{
  "audit_type": "administrative_action",
  "admin_user_id": "admin-123",
  "action_type": "USER_CREATED",
  "affected_entities": {"user_id": "user-456"},
  "details": {"role": "PROGRAM_MANAGER"},
  "timestamp": "2024-01-15T10:30:00.000Z",
  "cloudtrail_event": true
}
```

## CloudWatch Integration

All audit logs are automatically sent to CloudWatch Logs with:
- Log group: `/aws/lambda/audit-logging`
- Retention: Minimum 1 year (as per Requirement 28.5)
- Structured JSON format for easy querying

## CloudTrail Integration

Audit logs marked with `cloudtrail_event: true` are also captured by CloudTrail for:
- Immutable audit trail
- Compliance reporting
- Security analysis
- Long-term retention (minimum 1 year)

## Monitoring

The audit logging service includes CloudWatch alarms for:
- Failed event processing
- High error rates
- Missing required fields in events

## Security

- All audit logs are immutable once written
- Logs include tamper-evident timestamps
- Tenant isolation enforced at all levels
- Sensitive data is not logged (passwords, tokens, etc.)

## Testing

Run tests with:
```bash
pytest tests/test_audit_logging.py -v
```
