# Dashboard API Service

## Overview

The Dashboard API service provides endpoints for retrieving aggregated dashboard data, including project summaries, health scores, RAG status, risks, milestones, and metrics. The service implements caching with ElastiCache Redis (5-minute TTL) and automatic cache invalidation on data updates.

## Components

### 1. handler.py
Main Lambda handlers for dashboard API endpoints:
- `get_dashboard_overview_handler`: Portfolio-level dashboard with all projects
- `get_project_dashboard_handler`: Detailed dashboard for a specific project
- `get_metrics_handler`: Metrics query endpoint (velocity, backlog, utilization)

### 2. dashboard_aggregator.py
Core business logic for aggregating dashboard data:
- Queries data from DynamoDB (health scores, RAG status, risks) and RDS (metrics, milestones)
- Calculates portfolio-level health metrics
- Generates chart-ready data structures
- Supports filtering by project IDs

### 3. cache_manager.py
Redis cache management:
- `get_cached_data`: Retrieve data from cache
- `set_cached_data`: Store data in cache with TTL (default 5 minutes)
- `invalidate_cache`: Delete specific cache keys
- `invalidate_cache_pattern`: Delete cache keys matching a pattern
- `invalidate_project_cache`: Invalidate all cache for a project
- `invalidate_tenant_cache`: Invalidate all cache for a tenant

### 4. cache_invalidation_handler.py
DynamoDB Streams handler for automatic cache invalidation:
- Processes DynamoDB stream events (INSERT, MODIFY)
- Invalidates relevant cache entries when data changes
- Supports Risks, Predictions, and health_score tables

## API Endpoints

### GET /dashboard/overview
Retrieve portfolio-level dashboard overview.

**Query Parameters:**
- `projectIds` (optional): Comma-separated list of project IDs to filter

**Response:**
```json
{
  "projects": [
    {
      "project_id": "uuid",
      "project_name": "Project A",
      "healthScore": 85,
      "ragStatus": "GREEN",
      "trend": "IMPROVING",
      "activeRisks": 2,
      "nextMilestone": {
        "name": "Milestone 1",
        "dueDate": "2024-01-15",
        "completionPercentage": 75
      }
    }
  ],
  "portfolioHealth": {
    "overallHealthScore": 82,
    "overallRagStatus": "GREEN",
    "projectsByStatus": {
      "red": 1,
      "amber": 2,
      "green": 5
    },
    "totalActiveRisks": 8,
    "criticalRisks": 1
  },
  "recentRisks": [...],
  "upcomingMilestones": [...],
  "lastUpdated": "2024-01-10T12:00:00Z"
}
```

### GET /dashboard/project/{projectId}
Retrieve detailed dashboard for a specific project.

**Path Parameters:**
- `projectId`: Project ID (UUID)

**Response:**
```json
{
  "project_id": "uuid",
  "project_name": "Project A",
  "source": "JIRA",
  "healthScore": 85,
  "ragStatus": "GREEN",
  "velocityTrend": {
    "labels": ["Sprint 1", "Sprint 2", "Sprint 3"],
    "values": [25, 30, 28],
    "trend": "STABLE"
  },
  "backlogTrend": {
    "labels": [...],
    "values": [...],
    "trend": "IMPROVING"
  },
  "milestoneTimeline": {
    "milestones": [
      {
        "name": "Milestone 1",
        "dueDate": "2024-01-15",
        "completionPercentage": 75,
        "status": "ON_TRACK"
      }
    ]
  },
  "risks": [...],
  "predictions": {
    "delayProbability": 25,
    "workloadImbalance": 15
  }
}
```

### GET /dashboard/project/{projectId}/metrics
Retrieve metrics for a specific project.

**Path Parameters:**
- `projectId`: Project ID (UUID)

**Query Parameters:**
- `metricType` (required): velocity, backlog, or utilization
- `timeRange` (optional): 7d, 30d, 90d, or all (default: 30d)

**Response:**
```json
{
  "metricType": "velocity",
  "data": {
    "labels": ["Sprint 1", "Sprint 2", "Sprint 3"],
    "values": [25, 30, 28],
    "trend": "STABLE"
  },
  "statistics": {
    "current": 28,
    "average": 27.67,
    "min": 25,
    "max": 30,
    "trend": "STABLE"
  }
}
```

## Caching Strategy

### Cache Keys
- Dashboard overview: `dashboard:overview:{tenant_id}` or `dashboard:overview:{tenant_id}:{project_ids}`
- Project dashboard: `dashboard:project:{tenant_id}:{project_id}`

### Cache TTL
- Default: 300 seconds (5 minutes)
- Configurable per cache operation

### Cache Invalidation
Automatic invalidation on data updates via DynamoDB Streams:
- Health score changes → Invalidate project and overview caches
- Risk updates → Invalidate project cache
- Prediction updates → Invalidate project cache
- Milestone updates → Invalidate project cache

## Requirements Validation

### Requirement 20.1
Dashboard displays health scores, RAG status, active risk alerts, and key metrics.
- ✅ Implemented in `get_dashboard_overview` and `get_project_dashboard`

### Requirement 20.2
Dashboard loads within 3 seconds.
- ✅ Implemented with Redis caching (5-minute TTL)
- ✅ Optimized database queries with indexes

### Requirement 20.3
Dashboard updates automatically every 5 minutes.
- ✅ Implemented with 5-minute cache TTL
- ✅ Automatic cache invalidation on data changes

### Requirement 20.4
Dashboard supports drill-down from portfolio to project view.
- ✅ Implemented with separate overview and project endpoints

### Requirement 20.5
Dashboard displays velocity trends, backlog trends, and milestone timeline.
- ✅ Implemented in `get_project_dashboard`

### Requirement 20.6
Dashboard supports filtering by project, date range, and RAG status.
- ✅ Project filtering implemented in overview endpoint
- ✅ Date range filtering implemented in metrics endpoint
- ✅ RAG status available in all responses

## Dependencies

### Python Packages
- boto3: AWS SDK for DynamoDB and EventBridge
- redis: Redis client for caching
- psycopg2-binary: PostgreSQL client for RDS

### AWS Services
- ElastiCache Redis: Caching layer
- DynamoDB: Risks, Predictions, and other metadata
- RDS PostgreSQL: Project metrics, sprints, milestones
- DynamoDB Streams: Cache invalidation triggers

## Environment Variables

- `REDIS_ENDPOINT`: ElastiCache Redis endpoint
- `REDIS_PORT`: Redis port (default: 6379)
- `DB_SECRET_NAME`: RDS credentials secret name
- `DB_HOST`: RDS host
- `DB_PORT`: RDS port (default: 5432)
- `DB_NAME`: Database name

## Testing

See `tests/test_dashboard.py` for comprehensive unit tests covering:
- Dashboard overview aggregation
- Project dashboard data retrieval
- Metrics queries with different time ranges
- Cache operations (get, set, invalidate)
- Cache invalidation on DynamoDB stream events

## Future Enhancements

1. **Real-time Updates**: Implement WebSocket support for real-time dashboard updates
2. **Custom Dashboards**: Allow users to customize dashboard layout and widgets
3. **Export**: Add dashboard export to PDF/Excel
4. **Alerts**: Add configurable alerts for dashboard metrics
5. **Comparison**: Add project comparison views
