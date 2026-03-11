# Health Score Calculation Service

## Overview

The Health Score Calculation Service calculates an overall project health score (0-100) based on weighted components: velocity trend, backlog health, milestone progress, and risk count.

## Components

### score_calculator.py
- Calculates individual component scores (velocity, backlog, milestones, risks)
- Applies weighted composite calculation
- Supports custom tenant-specific weights
- Normalizes final score to 0-100 range

### score_storage.py
- Stores health score history in RDS PostgreSQL
- Retrieves health score history for trend analysis
- Publishes health score events to EventBridge

### handler.py
- Lambda handlers for health score operations
- `calculate_health_score_handler`: Calculate and store health score
- `get_health_score_handler`: Retrieve latest health score
- `get_health_score_history_handler`: Retrieve health score history

### event_trigger.py
- EventBridge trigger handlers for automatic recalculation
- `data_refresh_trigger_handler`: Triggered by DataIngestionCompleted events
- `scheduled_recalculation_handler`: Periodic recalculation for all projects

## Health Score Calculation

### Default Weights
- Velocity: 30%
- Backlog: 25%
- Milestones: 30%
- Risks: 15%

### Component Scores

#### Velocity Score (0-100)
Based on current velocity vs. 4-sprint moving average:
- 100: Current >= average
- 90: Current >= 90% of average
- 70: Current >= 80% of average
- 50: Current >= 70% of average
- 30: Current < 70% of average

#### Backlog Score (0-100)
Based on open backlog ratio:
- 100: <= 30% open
- 90: <= 50% open
- 70: <= 70% open
- 50: <= 85% open
- 30: > 85% open

#### Milestone Score (0-100)
Based on milestone status distribution:
- ON_TRACK/COMPLETED: 100 points
- AT_RISK: 50 points
- DELAYED: 0 points

#### Risk Score (0-100)
Based on active risk severity:
- Impact = (CRITICAL × 30) + (HIGH × 15) + (MEDIUM × 5)
- Score = max(0, 100 - Impact)

### Final Score
```
health_score = (velocity_score × 0.30) + 
               (backlog_score × 0.25) + 
               (milestone_score × 0.30) + 
               (risk_score × 0.15)
```

## API Endpoints

### Calculate Health Score
**POST** `/health-score/calculate`

Request:
```json
{
  "project_id": "uuid",
  "tenant_id": "uuid",
  "custom_weights": {
    "velocity": 0.30,
    "backlog": 0.25,
    "milestones": 0.30,
    "risks": 0.15
  }
}
```

Response:
```json
{
  "health_score": 75,
  "component_scores": {
    "velocity": 80.0,
    "backlog": 70.0,
    "milestones": 75.0,
    "risks": 85.0
  },
  "weights": {
    "velocity": 0.30,
    "backlog": 0.25,
    "milestones": 0.30,
    "risks": 0.15
  },
  "calculated_at": "2024-01-15T10:30:00Z",
  "history_id": "uuid"
}
```

### Get Latest Health Score
**GET** `/health-score/{projectId}`

Response:
```json
{
  "id": "uuid",
  "health_score": 75,
  "velocity_score": 80.0,
  "backlog_score": 70.0,
  "milestone_score": 75.0,
  "risk_score": 85.0,
  "weights": {...},
  "calculated_at": "2024-01-15T10:30:00Z"
}
```

### Get Health Score History
**GET** `/health-score/{projectId}/history?limit=30`

Response:
```json
{
  "history": [
    {
      "id": "uuid",
      "health_score": 75,
      "velocity_score": 80.0,
      "backlog_score": 70.0,
      "milestone_score": 75.0,
      "risk_score": 85.0,
      "calculated_at": "2024-01-15T10:30:00Z"
    }
  ],
  "count": 1
}
```

## Event Integration

### Published Events

#### HealthScoreCalculated
Published to EventBridge after health score calculation:
```json
{
  "Source": "ai-sw-pm.health-score",
  "DetailType": "HealthScoreCalculated",
  "Detail": {
    "project_id": "uuid",
    "tenant_id": "uuid",
    "health_score": 75,
    "component_scores": {...},
    "calculated_at": "2024-01-15T10:30:00Z"
  }
}
```

### Consumed Events

#### DataIngestionCompleted
Triggers health score recalculation after data refresh.

Event format:
```json
{
  "detail-type": "DataIngestionCompleted",
  "source": "ai-sw-pm.data-ingestion",
  "detail": {
    "project_id": "uuid",
    "tenant_id": "uuid",
    "ingestion_type": "JIRA",
    "completed_at": "2024-01-15T10:30:00Z"
  }
}
```

#### RiskDetectionCompleted
Triggers health score recalculation after risk detection.

#### Scheduled Event
Periodic recalculation (e.g., hourly) to ensure all projects have current scores.

## Database Schema

### health_score_history Table
```sql
CREATE TABLE health_score_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    health_score INTEGER NOT NULL,
    velocity_score DECIMAL(5,2),
    backlog_score DECIMAL(5,2),
    milestone_score DECIMAL(5,2),
    risk_score DECIMAL(5,2),
    weights JSONB,
    calculated_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_health_score_project ON health_score_history(project_id, calculated_at DESC);
CREATE INDEX idx_health_score_tenant ON health_score_history(tenant_id);
```

## Requirements Validation

- **Requirement 18.1**: Health score calculated as weighted composite ✓
- **Requirement 18.2**: Normalized to 0-100 scale ✓
- **Requirement 18.3**: Updated on data refresh (via EventBridge) ✓
- **Requirement 18.4**: History stored for trend visualization ✓
- **Requirement 18.5**: Default weights applied ✓
- **Requirement 18.6**: Custom tenant weights supported ✓

## Properties Validated

- **Property 54**: Health Score Composition ✓
- **Property 55**: Health Score Range ✓
- **Property 56**: Health Score Update Triggering ✓
- **Property 57**: Health Score History Persistence ✓
- **Property 58**: Default Weight Application ✓
- **Property 59**: Custom Weight Application ✓

## Testing

Run tests:
```bash
pytest tests/test_health_score.py -v
```

## Deployment

The service is deployed as AWS Lambda functions with:
- EventBridge trigger for automatic recalculation
- API Gateway endpoints for on-demand queries
- RDS PostgreSQL for history storage
- EventBridge for event publishing
