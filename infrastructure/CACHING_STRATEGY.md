# Caching Strategy

## Overview

The AI SW Program Manager platform implements a comprehensive caching strategy using Amazon ElastiCache Redis to improve API response performance and reduce database load. This document describes the caching architecture, TTL configurations, and cache invalidation mechanisms.

**Validates: Requirements 20.3, 23.1**

## Architecture

### ElastiCache Redis Cluster

- **Engine**: Redis 7.0
- **Node Type**: cache.t3.micro (scalable)
- **Deployment**: Multi-AZ with automatic failover
- **Configuration**: 
  - Primary node + 1 replica for high availability
  - Automatic failover enabled
  - At-rest encryption enabled
  - Transit encryption enabled
  - Snapshot retention: 5 days
  - Maintenance window: Sunday 05:00-07:00 UTC

### Network Configuration

- **VPC**: Deployed in private subnets with egress
- **Security Group**: Allows Redis port (6379) from VPC CIDR only
- **Subnet Group**: Spans multiple availability zones for HA

## Cache TTL Configuration

### Dashboard Data (5 minutes)

**Validates: Requirement 20.3**

Dashboard data is cached with a 5-minute TTL to balance freshness with performance:

- **Cache Keys**:
  - `dashboard:overview:{tenant_id}` - Portfolio overview
  - `dashboard:overview:{tenant_id}:{project_ids}` - Filtered overview
  - `dashboard:project:{tenant_id}:{project_id}` - Project dashboard

- **Cached Data**:
  - Project health scores and RAG status
  - Active risk alerts
  - Upcoming milestones
  - Portfolio health metrics
  - Velocity trends
  - Backlog status
  - Predictions

- **Rationale**: 
  - Dashboard is frequently accessed by users
  - 5-minute freshness is acceptable for monitoring use cases
  - Reduces database queries by ~95%
  - Meets requirement for dashboard updates every 5 minutes

### Report Data (1 hour)

**Validates: Requirement 23.1**

Report aggregation data is cached with a 1-hour TTL:

- **Cache Keys**:
  - `report:data:{tenant_id}` - All projects report data
  - `report:data:{tenant_id}:projects:{project_ids}` - Filtered report data
  - `report:data:{tenant_id}:projects:{project_ids}:start:{date}:end:{date}` - Date-ranged data

- **Cached Data**:
  - Project health scores
  - Completed milestones
  - Upcoming milestones
  - Active risks
  - Velocity trends (8 sprints)
  - Backlog status
  - Predictions

- **Rationale**:
  - Reports are generated less frequently than dashboard views
  - Historical data changes infrequently
  - 1-hour TTL provides good balance between freshness and performance
  - Reduces expensive aggregation queries

## Cache Invalidation

**Validates: Requirement 20.3**

### Automatic Invalidation via DynamoDB Streams

The platform implements automatic cache invalidation when underlying data changes:

#### Monitored Tables

1. **Risks Table**
   - Triggers: INSERT, MODIFY events
   - Invalidates: Project dashboard cache, overview cache
   - Handler: `cache_invalidation_handler.py`

2. **Predictions Table**
   - Triggers: INSERT, MODIFY events
   - Invalidates: Project dashboard cache, overview cache
   - Handler: `cache_invalidation_handler.py`

3. **Health Score Updates**
   - Triggers: INSERT, MODIFY events
   - Invalidates: Project dashboard cache, overview cache
   - Handler: `cache_invalidation_handler.py`

#### Invalidation Patterns

```python
# Project-specific invalidation
invalidate_cache(f"dashboard:project:{tenant_id}:{project_id}")

# Overview invalidation (affects all projects)
invalidate_cache_pattern(f"dashboard:overview:{tenant_id}*")

# Report data invalidation
invalidate_cache_pattern(f"report:data:{tenant_id}*")
```

### Manual Invalidation

Cache can be manually invalidated via helper functions:

```python
# Invalidate specific cache key
invalidate_cache(key)

# Invalidate by pattern
invalidate_cache_pattern("dashboard:*")

# Invalidate all tenant cache
invalidate_tenant_cache(tenant_id)

# Invalidate project cache
invalidate_project_cache(tenant_id, project_id)
```

## Cache Key Naming Convention

### Format

```
{service}:{type}:{tenant_id}[:{additional_identifiers}]
```

### Examples

- `dashboard:overview:tenant-123`
- `dashboard:project:tenant-123:project-456`
- `report:data:tenant-123:projects:proj1,proj2`
- `report:data:tenant-123:start:20240101:end:20240131`

### Benefits

- Hierarchical structure enables pattern-based invalidation
- Tenant ID always included for isolation
- Sorted identifiers ensure cache key consistency
- Clear service/type prefixes for monitoring

## Performance Metrics

### Expected Cache Hit Rates

- **Dashboard Overview**: 85-95% (frequently accessed, 5-min TTL)
- **Project Dashboard**: 80-90% (frequently accessed, 5-min TTL)
- **Report Data**: 70-85% (less frequent access, 1-hour TTL)

### Performance Improvements

- **Dashboard Load Time**: Reduced from ~2-3s to <200ms (cache hit)
- **Report Generation**: Reduced data aggregation from ~5-10s to <500ms (cache hit)
- **Database Load**: Reduced by ~90% for dashboard queries
- **API Response Time**: 95% of requests under 2 seconds (Requirement 23.1)

## Cache Statistics

The cache manager provides statistics via `get_cache_stats()`:

```python
{
    'total_connections_received': 1000,
    'total_commands_processed': 5000,
    'keyspace_hits': 4500,
    'keyspace_misses': 500,
    'hit_rate': 90.0  # percentage
}
```

## Monitoring and Alerts

### CloudWatch Metrics

- **Cache Hit Rate**: Monitor via custom metric
- **Cache Memory Usage**: ElastiCache built-in metric
- **Evictions**: Monitor for capacity issues
- **Connection Count**: Monitor for connection pool issues

### Recommended Alarms

1. **Cache Hit Rate < 70%**: Indicates TTL may be too short or invalidation too aggressive
2. **Memory Usage > 80%**: Consider scaling up node type
3. **Evictions > 100/min**: Increase cache size or reduce TTL
4. **Connection Errors**: Check security group and network configuration

## Scaling Considerations

### Vertical Scaling

Upgrade node type when:
- Memory usage consistently > 80%
- Evictions occur frequently
- Response times degrade

Node type progression:
- cache.t3.micro (512 MB) - Development/small deployments
- cache.t3.small (1.37 GB) - Small production
- cache.t3.medium (3.09 GB) - Medium production
- cache.r6g.large (13.07 GB) - Large production

### Horizontal Scaling

Add read replicas when:
- Read throughput exceeds single node capacity
- Geographic distribution needed
- Higher availability required

## Security

### Encryption

- **At Rest**: Enabled via AWS-managed encryption
- **In Transit**: TLS encryption enabled
- **Auth Token**: Optional, can be enabled for additional security

### Network Security

- **VPC Isolation**: Redis cluster in private subnets only
- **Security Group**: Restricts access to VPC CIDR
- **No Public Access**: Cluster not accessible from internet

### Access Control

- **IAM**: Lambda execution roles granted network access
- **Security Groups**: Explicit ingress rules required
- **Tenant Isolation**: Cache keys include tenant_id prefix

## Best Practices

### Cache Key Design

1. **Always include tenant_id** for isolation
2. **Sort multi-value identifiers** for consistency
3. **Use hierarchical structure** for pattern invalidation
4. **Keep keys concise** to reduce memory usage

### TTL Selection

1. **Short TTL (1-5 min)**: Frequently changing data, real-time requirements
2. **Medium TTL (15-60 min)**: Moderately changing data, acceptable staleness
3. **Long TTL (1-24 hours)**: Rarely changing data, historical data

### Invalidation Strategy

1. **Prefer automatic invalidation** via DynamoDB Streams
2. **Use pattern invalidation** for related cache entries
3. **Avoid full cache flushes** unless necessary
4. **Log invalidation events** for debugging

### Error Handling

1. **Graceful degradation**: Continue without cache if Redis unavailable
2. **Log cache errors**: Monitor for connectivity issues
3. **Don't fail requests**: Cache is performance optimization, not requirement
4. **Set connection timeouts**: Prevent hanging on Redis issues

## Troubleshooting

### Cache Not Working

1. Check `REDIS_ENDPOINT` environment variable is set
2. Verify Lambda has network access to Redis (VPC configuration)
3. Check security group allows port 6379 from Lambda
4. Review CloudWatch logs for connection errors

### Low Hit Rate

1. Check TTL is appropriate for data change frequency
2. Verify cache invalidation isn't too aggressive
3. Review cache key generation for consistency
4. Monitor eviction rate (may need larger cache)

### High Memory Usage

1. Review cache key count and sizes
2. Consider shorter TTLs for less critical data
3. Implement LRU eviction policy (already configured)
4. Scale up to larger node type

## Future Enhancements

1. **Redis Cluster Mode**: For horizontal scaling beyond single replication group
2. **Multi-Region Replication**: For global deployments
3. **Cache Warming**: Pre-populate cache on deployment
4. **Adaptive TTL**: Adjust TTL based on data change frequency
5. **Cache Compression**: Reduce memory usage for large objects
6. **Read-Through Caching**: Automatic cache population on miss

## References

- [AWS ElastiCache for Redis Documentation](https://docs.aws.amazon.com/elasticache/redis/)
- [Redis Best Practices](https://redis.io/docs/manual/patterns/)
- Requirements 20.3, 23.1 in requirements.md
- Design document section on Dashboard Service
