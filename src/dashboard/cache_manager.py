"""Cache management using ElastiCache Redis."""

import sys
import os
import json
from typing import Any, Optional
import boto3
from botocore.exceptions import ClientError

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logger import get_logger

logger = get_logger()

# Redis client (initialized lazily)
_redis_client = None

# Environment variables
REDIS_ENDPOINT = os.environ.get('REDIS_ENDPOINT')
REDIS_PORT = int(os.environ.get('REDIS_PORT', '6379'))

# Cache TTL constants (in seconds)
# Validates: Requirement 20.3, 23.1 (cache TTLs)
DASHBOARD_CACHE_TTL = 300  # 5 minutes for dashboard data
REPORT_CACHE_TTL = 3600    # 1 hour for reports


def get_redis_client():
    """
    Get or create Redis client.
    
    Returns:
        Redis client or None if Redis is not available
    """
    global _redis_client
    
    if _redis_client is None:
        try:
            import redis
            
            if not REDIS_ENDPOINT:
                logger.warning("Redis endpoint not configured, caching disabled")
                return None
            
            _redis_client = redis.Redis(
                host=REDIS_ENDPOINT,
                port=REDIS_PORT,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2
            )
            
            # Test connection
            _redis_client.ping()
            logger.info("Redis client initialized successfully")
            
        except ImportError:
            logger.warning("redis-py not installed, caching disabled")
            return None
        except Exception as e:
            logger.error(f"Failed to initialize Redis client: {str(e)}")
            return None
    
    return _redis_client


def get_cached_data(key: str) -> Optional[Any]:
    """
    Get data from cache.
    
    Args:
        key: Cache key
        
    Returns:
        Cached data or None if not found or cache unavailable
    """
    redis_client = get_redis_client()
    
    if not redis_client:
        return None
    
    try:
        cached_value = redis_client.get(key)
        
        if cached_value:
            logger.debug(f"Cache hit for key: {key}")
            return json.loads(cached_value)
        
        logger.debug(f"Cache miss for key: {key}")
        return None
        
    except Exception as e:
        logger.error(f"Failed to get cached data: {str(e)}")
        return None


def set_cached_data(key: str, data: Any, ttl: int = DASHBOARD_CACHE_TTL) -> bool:
    """
    Set data in cache with TTL.
    
    Validates: Requirement 20.3, 23.1 (caching with configurable TTL)
    
    Args:
        key: Cache key
        data: Data to cache
        ttl: Time to live in seconds (default DASHBOARD_CACHE_TTL = 5 minutes)
        
    Returns:
        True if successful, False otherwise
    """
    redis_client = get_redis_client()
    
    if not redis_client:
        return False
    
    try:
        serialized_data = json.dumps(data)
        redis_client.setex(key, ttl, serialized_data)
        
        logger.debug(f"Cached data for key: {key} with TTL: {ttl}s")
        return True
        
    except Exception as e:
        logger.error(f"Failed to set cached data: {str(e)}")
        return False


def invalidate_cache(key: str) -> bool:
    """
    Invalidate (delete) cached data.
    
    Args:
        key: Cache key to invalidate
        
    Returns:
        True if successful, False otherwise
    """
    redis_client = get_redis_client()
    
    if not redis_client:
        return False
    
    try:
        redis_client.delete(key)
        logger.debug(f"Invalidated cache for key: {key}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to invalidate cache: {str(e)}")
        return False


def invalidate_cache_pattern(pattern: str) -> int:
    """
    Invalidate all cache keys matching a pattern.
    
    Args:
        pattern: Redis key pattern (e.g., "dashboard:*")
        
    Returns:
        Number of keys invalidated
    """
    redis_client = get_redis_client()
    
    if not redis_client:
        return 0
    
    try:
        keys = redis_client.keys(pattern)
        
        if keys:
            count = redis_client.delete(*keys)
            logger.info(f"Invalidated {count} cache keys matching pattern: {pattern}")
            return count
        
        return 0
        
    except Exception as e:
        logger.error(f"Failed to invalidate cache pattern: {str(e)}")
        return 0


def invalidate_tenant_cache(tenant_id: str) -> int:
    """
    Invalidate all cache for a specific tenant.
    
    Args:
        tenant_id: Tenant ID
        
    Returns:
        Number of keys invalidated
    """
    pattern = f"dashboard:*:{tenant_id}*"
    return invalidate_cache_pattern(pattern)


def invalidate_project_cache(tenant_id: str, project_id: str) -> int:
    """
    Invalidate all cache for a specific project.
    
    Args:
        tenant_id: Tenant ID
        project_id: Project ID
        
    Returns:
        Number of keys invalidated
    """
    # Invalidate project-specific cache
    project_pattern = f"dashboard:project:{tenant_id}:{project_id}"
    count = invalidate_cache_pattern(project_pattern)
    
    # Also invalidate overview cache that might include this project
    overview_pattern = f"dashboard:overview:{tenant_id}*"
    count += invalidate_cache_pattern(overview_pattern)
    
    return count


def cache_dashboard_data(key: str, data: Any) -> bool:
    """
    Cache dashboard data with 5-minute TTL.
    
    Validates: Requirement 20.3 (5-minute TTL for dashboard data)
    
    Args:
        key: Cache key
        data: Dashboard data to cache
        
    Returns:
        True if successful, False otherwise
    """
    return set_cached_data(key, data, ttl=DASHBOARD_CACHE_TTL)


def cache_report_data(key: str, data: Any) -> bool:
    """
    Cache report data with 1-hour TTL.
    
    Validates: Requirement 23.1 (1-hour TTL for reports)
    
    Args:
        key: Cache key
        data: Report data to cache
        
    Returns:
        True if successful, False otherwise
    """
    return set_cached_data(key, data, ttl=REPORT_CACHE_TTL)


def get_cache_stats() -> dict:
    """
    Get cache statistics.
    
    Returns:
        Dictionary with cache statistics or empty dict if unavailable
    """
    redis_client = get_redis_client()
    
    if not redis_client:
        return {}
    
    try:
        info = redis_client.info('stats')
        
        return {
            'total_connections_received': info.get('total_connections_received', 0),
            'total_commands_processed': info.get('total_commands_processed', 0),
            'keyspace_hits': info.get('keyspace_hits', 0),
            'keyspace_misses': info.get('keyspace_misses', 0),
            'hit_rate': (
                info.get('keyspace_hits', 0) / 
                max(info.get('keyspace_hits', 0) + info.get('keyspace_misses', 0), 1)
            ) * 100
        }
        
    except Exception as e:
        logger.error(f"Failed to get cache stats: {str(e)}")
        return {}
