# Risk Detection Service

This module implements comprehensive risk detection for the AI SW Program Manager platform.

## Overview

The risk detection service analyzes project data from multiple sources (sprints, backlog, milestones) to identify potential risks and generate AI-powered explanations and recommendations.

## Components

### 1. Velocity Analysis (`velocity_analysis.py`)
Detects velocity decline risks by analyzing sprint velocity trends.

**Key Functions:**
- `query_last_sprints()` - Retrieves last N sprints from RDS
- `calculate_velocity_trend()` - Calculates moving average and trend
- `detect_velocity_decline()` - Identifies velocity decline > 20% over 2 sprints
- `analyze_velocity_risk()` - Main entry point for velocity analysis

**Validates:**
- Property 15: Velocity Trend Calculation
- Property 16: Velocity Decline Risk Detection

### 2. Backlog Analysis (`backlog_analysis.py`)
Detects backlog growth risks by analyzing backlog metrics.

**Key Functions:**
- `query_backlog_metrics()` - Retrieves current backlog metrics
- `calculate_team_completion_rate()` - Calculates weekly completion rate
- `calculate_backlog_growth_rate()` - Calculates weekly growth rate
- `detect_backlog_growth_risk()` - Identifies rapid growth or excessive backlog
- `analyze_backlog_risk()` - Main entry point for backlog analysis

**Detection Criteria:**
- Backlog grows > 30% in single week, OR
- Backlog size > 2x team's weekly completion rate

**Validates:**
- Property 17: Backlog Growth Risk Detection

### 3. Milestone Analysis (`milestone_analysis.py`)
Detects milestone slippage risks by analyzing milestone progress.

**Key Functions:**
- `query_active_milestones()` - Retrieves non-completed milestones
- `calculate_milestone_metrics()` - Calculates completion and time metrics
- `estimate_delay_days()` - Estimates delay based on current progress
- `detect_milestone_slippage_risk()` - Identifies at-risk milestones
- `analyze_milestone_risks()` - Main entry point for milestone analysis

**Detection Criteria:**
- Milestone < 70% complete with < 20% time remaining

**Validates:**
- Property 18: Milestone Slippage Risk Detection
- Property 22: Dependency Impact Analysis

### 4. AI Explanations (`ai_explanations.py`)
Generates AI-powered risk explanations using Amazon Bedrock.

**Key Functions:**
- `create_velocity_decline_prompt()` - Creates prompt for velocity risks
- `create_backlog_growth_prompt()` - Creates prompt for backlog risks
- `create_milestone_slippage_prompt()` - Creates prompt for milestone risks
- `invoke_bedrock_claude()` - Invokes Bedrock Claude model
- `generate_risk_explanation()` - Generates explanation and recommendations
- `enrich_risk_with_ai()` - Main entry point for AI enrichment

**Validates:**
- Property 20: AI-Generated Risk Explanations

### 5. Risk Storage (`risk_storage.py`)
Manages risk alert storage and retrieval using DynamoDB.

**Key Functions:**
- `store_risk_alert()` - Stores risk in DynamoDB
- `list_risks()` - Lists risks with filtering
- `dismiss_risk()` - Dismisses a risk alert
- `publish_risk_event()` - Publishes risk events to EventBridge

**DynamoDB Schema:**
```
PK: TENANT#{tenant_id}
SK: RISK#{risk_id}
GSI1PK: PROJECT#{project_id}
GSI1SK: RISK#{detected_at}
GSI2PK: TENANT#{tenant_id}#SEVERITY#{severity}
GSI2SK: RISK#{detected_at}
```

**Validates:**
- Property 21: Risk Alert Content Completeness

### 6. Handler (`handler.py`)
Main Lambda handlers for risk detection API endpoints.

**Handlers:**
- `detect_risks_handler()` - Detects all risks for a project
- `list_risks_handler()` - Lists risks with filtering
- `dismiss_risk_handler()` - Dismisses a risk

## Risk Severity Levels

Risks are assigned severity levels based on metrics:

- **CRITICAL**: Severe issues requiring immediate attention
  - Velocity decline ≥ 40%
  - Backlog growth ≥ 50% or size > 3x completion rate
  - Milestone < 50% complete with < 10% time remaining

- **HIGH**: Significant issues requiring prompt action
  - Velocity decline ≥ 30%
  - Backlog growth ≥ 40% or size > 2.5x completion rate
  - Milestone < 60% complete with < 15% time remaining

- **MEDIUM**: Moderate issues requiring attention
  - Velocity decline ≥ 20%
  - Backlog growth ≥ 30% or size > 2x completion rate
  - Milestone < 70% complete with < 20% time remaining

- **LOW**: Minor issues to monitor
  - Below medium thresholds but still concerning

## Usage

### Detect Risks for a Project

```python
from risk_detection.handler import detect_risks_handler

event = {
    'project_id': 'project-123',
    'tenant_id': 'tenant-456'
}

response = detect_risks_handler(event, context)
```

### List Risks

```python
from risk_detection.handler import list_risks_handler

event = {
    'tenant_id': 'tenant-456',
    'queryStringParameters': {
        'projectId': 'project-123',
        'severity': 'HIGH',
        'status': 'ACTIVE'
    }
}

response = list_risks_handler(event, context)
```

### Dismiss Risk

```python
from risk_detection.handler import dismiss_risk_handler

event = {
    'tenant_id': 'tenant-456',
    'pathParameters': {
        'riskId': 'risk-789'
    },
    'body': json.dumps({
        'reason': 'False positive - already addressed'
    })
}

response = dismiss_risk_handler(event, context)
```

## Environment Variables

- `DB_SECRET_NAME` - RDS credentials secret name
- `DB_HOST` - RDS host
- `DB_PORT` - RDS port (default: 5432)
- `DB_NAME` - Database name
- `RISKS_TABLE_NAME` - DynamoDB risks table name
- `EVENT_BUS_NAME` - EventBridge event bus name
- `BEDROCK_MODEL_ID` - Bedrock model ID (default: Claude 3 Sonnet)
- `BEDROCK_REGION` - Bedrock region (default: us-east-1)

## Testing

Run tests with:

```bash
pytest tests/test_velocity_analysis.py -v
pytest tests/test_backlog_analysis.py -v
pytest tests/test_milestone_analysis.py -v
pytest tests/test_risk_storage.py -v
```

All tests include comprehensive coverage of:
- Normal operation
- Edge cases
- Error handling
- Data validation

## Integration

The risk detection service integrates with:

1. **Data Ingestion** - Triggered after data ingestion completes
2. **EventBridge** - Publishes risk events for downstream processing
3. **DynamoDB** - Stores risk alerts with tenant isolation
4. **Amazon Bedrock** - Generates AI explanations
5. **RDS PostgreSQL** - Queries project data

## Future Enhancements

- Historical backlog tracking for accurate growth rate calculation
- Milestone dependency tracking for impact analysis
- Custom risk thresholds per tenant
- Risk trend analysis and prediction
- Integration with notification service
- Risk resolution workflow
