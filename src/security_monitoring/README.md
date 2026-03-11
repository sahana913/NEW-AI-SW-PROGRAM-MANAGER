# Security Monitoring Module

## Overview

The Security Monitoring module detects, blocks, and logs security violations across the AI SW Program Manager platform. It integrates with the tenant isolation decorator to monitor cross-tenant data access attempts and provides immediate alerting to administrators.

## Components

### 1. Violation Detector (`violation_detector.py`)

Detects and handles security violations in real-time.

**Key Functions:**
- `detect_cross_tenant_access()` - Detects cross-tenant access attempts
- `publish_violation_event()` - Publishes violation events to EventBridge
- `alert_administrator()` - Sends immediate SNS alerts to administrators
- `log_violation_attempt()` - Logs violations with full context

**Features:**
- Real-time detection of cross-tenant access attempts
- Automatic blocking at API Gateway level
- Immediate administrator alerts via SNS
- Comprehensive logging with full request context
- EventBridge integration for downstream processing

### 2. Lambda Handler (`handler.py`)

Processes security violation events and maintains audit records.

**Key Functions:**
- `lambda_handler()` - Main event processor
- `store_violation_record()` - Stores violations in DynamoDB
- `get_violations_by_tenant()` - Retrieves violations for a tenant
- `get_violations_by_user()` - Retrieves violations for a user

**Features:**
- EventBridge event processing
- DynamoDB storage for audit trail
- Query capabilities for compliance reporting
- Structured violation records

## Integration with Tenant Isolation

The security monitoring system integrates seamlessly with the existing `with_tenant_isolation` decorator in `shared/decorators.py`:

1. Decorator detects cross-tenant access attempt
2. Calls `detect_cross_tenant_access()` from violation detector
3. Violation is logged with full context
4. EventBridge event is published
5. SNS alert is sent to administrators
6. Request is blocked with 403 error
7. Violation record is stored in DynamoDB

## Data Flow

```
API Request → Lambda Authorizer → with_tenant_isolation Decorator
                                          ↓
                                  Cross-tenant detected?
                                          ↓
                                         Yes
                                          ↓
                            detect_cross_tenant_access()
                                          ↓
                    ┌────────────────────┼────────────────────┐
                    ↓                    ↓                    ↓
            CloudWatch Logs      EventBridge Event      SNS Alert
                    ↓                    ↓                    ↓
            Audit Trail      Security Monitoring      Administrator
                             Lambda Handler
                                    ↓
                            DynamoDB Storage
```

## Environment Variables

### Violation Detector
- `SECURITY_ALERT_TOPIC_ARN` - SNS topic ARN for administrator alerts
- `EVENT_BUS_NAME` - EventBridge event bus name (default: 'default')

### Lambda Handler
- `VIOLATIONS_TABLE_NAME` - DynamoDB table for violation records (default: 'SecurityViolations')
- `EVENT_BUS_NAME` - EventBridge event bus name (default: 'default')

## DynamoDB Schema

### SecurityViolations Table

```
PK: VIOLATION#{violation_id}
SK: TIMESTAMP#{timestamp}

Attributes:
- violation_id: Unique violation identifier
- violation_type: Type of violation (e.g., CROSS_TENANT_ACCESS)
- severity: Violation severity (CRITICAL, HIGH, MEDIUM, LOW)
- user_id: User who attempted the violation
- user_tenant_id: User's tenant ID
- requested_tenant_id: Tenant ID that was requested
- endpoint: API endpoint accessed
- timestamp: ISO 8601 timestamp
- request_context: Full request details (IP, user agent, etc.)
- status: BLOCKED
- created_at: Record creation timestamp

GSI1:
- GSI1PK: TENANT#{user_tenant_id}
- GSI1SK: VIOLATION#{timestamp}

GSI2:
- GSI2PK: USER#{user_id}
- GSI2SK: VIOLATION#{timestamp}
```

## SNS Alert Format

Administrator alerts include:
- Violation ID
- Violation type and severity
- Timestamp
- User details (ID, tenant)
- Request details (endpoint, method, path, IP, user agent)
- Action taken (request blocked)

## EventBridge Event Schema

```json
{
  "Source": "custom.security",
  "DetailType": "Security Violation",
  "Detail": {
    "violation_id": "VIOLATION-20240115120000-abc12345",
    "violation_type": "CROSS_TENANT_ACCESS",
    "severity": "CRITICAL",
    "user_id": "user-123",
    "user_tenant_id": "tenant-A",
    "requested_tenant_id": "tenant-B",
    "endpoint": "GET /api/projects",
    "timestamp": "2024-01-15T12:00:00.000Z",
    "request_context": {
      "http_method": "GET",
      "path": "/api/projects",
      "source_ip": "192.168.1.1",
      "user_agent": "Mozilla/5.0..."
    }
  }
}
```

## Logging

All security violations are logged with structured JSON format including:
- Violation ID
- Violation type
- Severity level
- User ID and tenant ID
- Endpoint and request details
- Source IP and user agent
- Timestamp

Logs are sent to CloudWatch Logs with ERROR severity for immediate visibility.

## Requirements Validation

This module validates:
- **Requirement 25.6**: Cross-tenant data access detection, blocking, and administrator alerting
- **Property 69**: Access violation blocking for detected cross-tenant access attempts

## Testing

See `tests/test_security_monitoring.py` for comprehensive unit tests covering:
- Cross-tenant access detection
- Violation logging
- EventBridge event publishing
- SNS alert sending
- DynamoDB storage
- Integration with tenant isolation decorator

## Usage Example

The security monitoring is automatically active when using the `with_tenant_isolation` decorator:

```python
from shared.decorators import with_tenant_isolation, with_error_handling

@with_tenant_isolation
@with_error_handling
def lambda_handler(event, context):
    # Your Lambda logic here
    # Tenant isolation is automatically enforced
    # Violations are automatically detected and handled
    pass
```

No additional code is required - the security monitoring is transparent to Lambda function implementations.
