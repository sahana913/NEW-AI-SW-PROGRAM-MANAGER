# RAG Status Determination Service

## Overview

The RAG Status Determination Service calculates and manages Red-Amber-Green (RAG) status indicators for projects based on their health scores. The service automatically updates RAG status whenever health scores change and generates notifications when status degrades from Green to Amber or Red.

## Components

### 1. `rag_calculator.py`
Core calculation logic for determining RAG status from health scores.

**Key Functions:**
- `get_tenant_thresholds(tenant_id)`: Retrieves custom thresholds for a tenant
- `determine_rag_status(health_score, custom_thresholds)`: Determines RAG status based on thresholds
- `calculate_rag_status(project_id, tenant_id, health_score, custom_thresholds)`: Main calculation function

**Default Thresholds:**
- Green: 80-100
- Amber: 60-79
- Red: <60

### 2. `rag_storage.py`
Storage and history management for RAG status data.

**Key Functions:**
- `store_rag_status(project_id, tenant_id, rag_status_data)`: Stores RAG status in database
- `get_rag_status_history(project_id, tenant_id, limit)`: Retrieves historical RAG status
- `get_latest_rag_status(project_id, tenant_id)`: Gets most recent RAG status
- `get_previous_rag_status(project_id, tenant_id)`: Gets previous RAG status for degradation detection
- `detect_status_degradation(current_status, previous_status)`: Detects Green → Amber/Red transitions
- `publish_rag_status_event(...)`: Publishes RAG status events to EventBridge
- `publish_degradation_notification(...)`: Publishes degradation notifications

### 3. `handler.py`
Lambda handlers for RAG status operations.

**Handlers:**
- `calculate_rag_status_handler`: Calculates RAG status (triggered by health score updates)
- `get_rag_status_handler`: Retrieves current RAG status for a project
- `get_rag_status_history_handler`: Retrieves RAG status history

### 4. `event_trigger.py`
EventBridge configuration for automatic triggering.

**Configuration:**
- Event source: `ai-sw-pm.health-score`
- Event type: `HealthScoreCalculated`
- Trigger: RAG status calculation Lambda

## Architecture

```
Health Score Service
        ↓
    EventBridge (HealthScoreCalculated event)
        ↓
RAG Status Calculation Lambda
        ↓
    ┌───────────────┬──────────────────┐
    ↓               ↓                  ↓
Store in RDS   Publish Event   Check Degradation
                    ↓                  ↓
            Dashboard/Reports   Notification Service
```

## Database Schema

### `rag_status_history` Table

```sql
CREATE TABLE rag_status_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    rag_status VARCHAR(10) NOT NULL,
    health_score INTEGER NOT NULL,
    thresholds JSONB,
    calculated_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_rag_status_project ON rag_status_history(project_id, calculated_at DESC);
CREATE INDEX idx_rag_status_tenant ON rag_status_history(tenant_id, calculated_at DESC);
```

## Event Formats

### Input Event (from Health Score Service)

```json
{
  "detail": {
    "project_id": "uuid",
    "tenant_id": "uuid",
    "health_score": 75,
    "component_scores": {
      "velocity": 80.0,
      "backlog": 70.0,
      "milestones": 75.0,
      "risks": 85.0
    },
    "calculated_at": "2024-01-01T00:00:00Z"
  }
}
```

### Output Event (RAG Status Calculated)

```json
{
  "source": "ai-sw-pm.rag-status",
  "detail-type": "RagStatusCalculated",
  "detail": {
    "project_id": "uuid",
    "tenant_id": "uuid",
    "rag_status": "AMBER",
    "health_score": 75,
    "calculated_at": "2024-01-01T00:00:00Z"
  }
}
```

### Degradation Notification Event

```json
{
  "source": "ai-sw-pm.rag-status",
  "detail-type": "RagStatusDegradation",
  "detail": {
    "project_id": "uuid",
    "tenant_id": "uuid",
    "current_status": "AMBER",
    "previous_status": "GREEN",
    "health_score": 75,
    "notification_type": "RAG_DEGRADATION",
    "severity": "MEDIUM",
    "message": "Project RAG status degraded from GREEN to AMBER",
    "timestamp": "2024-01-01T00:00:00Z"
  }
}
```

## API Endpoints

### Calculate RAG Status (Internal)
- **Method:** POST (EventBridge trigger)
- **Handler:** `calculate_rag_status_handler`
- **Trigger:** Automatic on health score update

### Get Current RAG Status
- **Method:** GET
- **Path:** `/projects/{projectId}/rag-status`
- **Handler:** `get_rag_status_handler`
- **Response:** Latest RAG status for project

### Get RAG Status History
- **Method:** GET
- **Path:** `/projects/{projectId}/rag-status/history`
- **Query Params:** `limit` (default: 30)
- **Handler:** `get_rag_status_history_handler`
- **Response:** Historical RAG status entries

## Properties Validated

- **Property 60:** RAG Status Determination - Assigns status based on health score thresholds
- **Property 61:** Custom Threshold Application - Applies tenant-specific thresholds when configured
- **Property 62:** RAG Status Update Triggering - Updates status whenever health score changes
- **Property 63:** RAG Degradation Notification - Generates notification on Green → Amber/Red transition

## Configuration

### Custom Thresholds

Tenants can configure custom RAG thresholds in their tenant configuration:

```json
{
  "tenant_id": "uuid",
  "rag_thresholds": {
    "green": 85,
    "amber": 65
  }
}
```

### EventBridge Rule

The service is triggered automatically by EventBridge when health scores are updated. No manual configuration is required.

## Error Handling

- **Missing Parameters:** Returns 400 Bad Request with validation error
- **Database Errors:** Logs error and returns 500 Internal Server Error
- **Event Publishing Failures:** Logs error but doesn't fail the request (non-critical)
- **Notification Failures:** Logs error but doesn't fail the request (non-critical)

## Monitoring

### CloudWatch Metrics
- RAG status calculation invocations
- Degradation notifications sent
- Event publishing success/failure rates

### CloudWatch Logs
- All calculations logged with project_id, health_score, and rag_status
- Degradation detections logged with previous and current status
- Event publishing results logged

## Testing

See `tests/test_rag_status.py` for comprehensive unit and property-based tests.

## Dependencies

- `shared.logger`: Logging utilities
- `shared.decorators`: Error handling and tenant isolation
- `shared.database`: Database query execution
- `shared.errors`: Custom error types
- `boto3`: AWS SDK for EventBridge and DynamoDB
