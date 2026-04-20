"""
Database Maintenance Lambda Handler

This Lambda function handles scheduled database maintenance tasks including:
- Refreshing materialized views
- Running VACUUM ANALYZE
- Monitoring query performance

Validates Requirements 18.7, 23.1
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

import boto3
import psycopg2
from botocore.exceptions import ClientError
from psycopg2.extras import RealDictCursor

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
DB_SECRET_ARN = os.environ.get("DB_SECRET_ARN")
DB_NAME = os.environ.get("DB_NAME", "ai_sw_program_manager")

# AWS clients
secrets_manager = boto3.client("secretsmanager")
cloudwatch = boto3.client("cloudwatch")


def get_db_credentials() -> Dict[str, str]:
    """
    Retrieve database credentials from Secrets Manager.

    Returns:
        Dictionary containing database connection parameters
    """
    try:
        response = secrets_manager.get_secret_value(SecretId=DB_SECRET_ARN)
        secret = json.loads(response["SecretString"])

        return {
            "host": secret.get("host"),
            "port": secret.get("port", 5432),
            "database": DB_NAME,
            "user": secret.get("username"),
            "password": secret.get("password"),
        }
    except ClientError as e:
        logger.error(f"Failed to retrieve database credentials: {str(e)}")
        raise


def get_db_connection():
    """
    Create a database connection.

    Returns:
        psycopg2 connection object
    """
    credentials = get_db_credentials()

    try:
        conn = psycopg2.connect(
            host=credentials["host"],
            port=credentials["port"],
            database=credentials["database"],
            user=credentials["user"],
            password=credentials["password"],
            connect_timeout=10,
        )
        return conn
    except psycopg2.Error as e:
        logger.error(f"Failed to connect to database: {str(e)}")
        raise


def refresh_materialized_views(conn, tenant_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Refresh materialized views.

    Args:
        conn: Database connection
        tenant_id: Optional tenant ID for tenant-specific refresh

    Returns:
        Dictionary with refresh results
    """
    start_time = datetime.utcnow()
    results = {"views_refreshed": [], "errors": [], "duration_seconds": 0}

    views_to_refresh = [
        "project_metrics_summary",
        "sprint_velocity_trends",
        "milestone_status_summary",
    ]

    try:
        with conn.cursor() as cursor:
            for view_name in views_to_refresh:
                try:
                    view_start = datetime.utcnow()

                    # Use CONCURRENTLY to avoid locking the view
                    cursor.execute(
                        f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view_name}"
                    )
                    conn.commit()

                    view_duration = (datetime.utcnow() - view_start).total_seconds()

                    results["views_refreshed"].append(
                        {
                            "view": view_name,
                            "duration_seconds": view_duration,
                            "status": "success",
                        }
                    )

                    logger.info(f"Refreshed {view_name} in {view_duration:.2f} seconds")

                    # Send metric to CloudWatch
                    cloudwatch.put_metric_data(
                        Namespace="AI-SW-PM/Database",
                        MetricData=[
                            {
                                "MetricName": "MaterializedViewRefreshDuration",
                                "Value": view_duration,
                                "Unit": "Seconds",
                                "Dimensions": [
                                    {"Name": "ViewName", "Value": view_name}
                                ],
                            }
                        ],
                    )

                except psycopg2.Error as e:
                    error_msg = f"Failed to refresh {view_name}: {str(e)}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)
                    conn.rollback()

    except Exception as e:
        logger.error(f"Error during materialized view refresh: {str(e)}")
        results["errors"].append(str(e))

    finally:
        results["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()

    return results


def vacuum_analyze_tables(conn) -> Dict[str, Any]:
    """
    Run VACUUM ANALYZE on all tables to update statistics.

    Args:
        conn: Database connection

    Returns:
        Dictionary with vacuum results
    """
    start_time = datetime.utcnow()
    results = {"tables_analyzed": [], "errors": [], "duration_seconds": 0}

    tables = [
        "tenants",
        "projects",
        "sprints",
        "backlog_items",
        "milestones",
        "resources",
        "dependencies",
        "health_scores",
    ]

    try:
        # VACUUM requires autocommit mode
        old_isolation_level = conn.isolation_level
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)

        with conn.cursor() as cursor:
            for table_name in tables:
                try:
                    table_start = datetime.utcnow()

                    cursor.execute(f"VACUUM ANALYZE {table_name}")

                    table_duration = (datetime.utcnow() - table_start).total_seconds()

                    results["tables_analyzed"].append(
                        {
                            "table": table_name,
                            "duration_seconds": table_duration,
                            "status": "success",
                        }
                    )

                    logger.info(
                        f"Vacuumed and analyzed {table_name} in {table_duration:.2f} seconds"
                    )

                except psycopg2.Error as e:
                    error_msg = f"Failed to vacuum {table_name}: {str(e)}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)

        # Restore isolation level
        conn.set_isolation_level(old_isolation_level)

    except Exception as e:
        logger.error(f"Error during vacuum analyze: {str(e)}")
        results["errors"].append(str(e))

    finally:
        results["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()

    return results


def check_slow_queries(conn) -> Dict[str, Any]:
    """
    Check for slow queries and log them.

    Args:
        conn: Database connection

    Returns:
        Dictionary with slow query information
    """
    results = {"slow_queries_count": 0, "slow_queries": [], "errors": []}

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Query pg_stat_statements for slow queries
            cursor.execute(
                """
                SELECT
                    query,
                    calls,
                    total_exec_time,
                    mean_exec_time,
                    max_exec_time
                FROM pg_stat_statements
                WHERE mean_exec_time > 2000  -- Queries taking more than 2 seconds
                ORDER BY mean_exec_time DESC
                LIMIT 10
            """
            )

            slow_queries = cursor.fetchall()
            results["slow_queries_count"] = len(slow_queries)

            for query in slow_queries:
                query_info = {
                    "query": query["query"][:200],  # Truncate for logging
                    "calls": query["calls"],
                    "mean_exec_time_ms": float(query["mean_exec_time"]),
                    "max_exec_time_ms": float(query["max_exec_time"]),
                }
                results["slow_queries"].append(query_info)

                logger.warning(
                    f"Slow query detected: {query_info['mean_exec_time_ms']:.2f}ms avg, "
                    f"{query_info['calls']} calls"
                )

                # Send metric to CloudWatch
                cloudwatch.put_metric_data(
                    Namespace="AI-SW-PM/Database",
                    MetricData=[
                        {
                            "MetricName": "SlowQueryMeanTime",
                            "Value": query_info["mean_exec_time_ms"],
                            "Unit": "Milliseconds",
                        }
                    ],
                )

    except psycopg2.Error as e:
        error_msg = f"Failed to check slow queries: {str(e)}"
        logger.error(error_msg)
        results["errors"].append(error_msg)

    return results


def check_table_sizes(conn) -> Dict[str, Any]:
    """
    Check table sizes and log large tables.

    Args:
        conn: Database connection

    Returns:
        Dictionary with table size information
    """
    results = {"table_sizes": [], "errors": []}

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    schemaname,
                    tablename,
                    pg_total_relation_size(schemaname||'.'||tablename) AS total_bytes,
                    pg_relation_size(schemaname||'.'||tablename) AS table_bytes,
                    pg_total_relation_size(schemaname||'.'||tablename) -
                        pg_relation_size(schemaname||'.'||tablename) AS index_bytes
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
                LIMIT 10
            """
            )

            tables = cursor.fetchall()

            for table in tables:
                table_info = {
                    "table": table["tablename"],
                    "total_mb": round(table["total_bytes"] / (1024 * 1024), 2),
                    "table_mb": round(table["table_bytes"] / (1024 * 1024), 2),
                    "index_mb": round(table["index_bytes"] / (1024 * 1024), 2),
                }
                results["table_sizes"].append(table_info)

                logger.info(
                    f"Table {table_info['table']}: "
                    f"Total={table_info['total_mb']}MB, "
                    f"Table={table_info['table_mb']}MB, "
                    f"Indexes={table_info['index_mb']}MB"
                )

                # Send metric to CloudWatch
                cloudwatch.put_metric_data(
                    Namespace="AI-SW-PM/Database",
                    MetricData=[
                        {
                            "MetricName": "TableSize",
                            "Value": table_info["total_mb"],
                            "Unit": "Megabytes",
                            "Dimensions": [
                                {"Name": "TableName", "Value": table_info["table"]}
                            ],
                        }
                    ],
                )

    except psycopg2.Error as e:
        error_msg = f"Failed to check table sizes: {str(e)}"
        logger.error(error_msg)
        results["errors"].append(error_msg)

    return results


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for database maintenance tasks.

    Event structure:
    {
        "task": "refresh_views" | "vacuum_analyze" | "check_performance" | "all",
        "tenant_id": "optional-tenant-id"
    }

    Args:
        event: Lambda event
        context: Lambda context

    Returns:
        Response with maintenance results
    """
    logger.info(f"Database maintenance triggered: {json.dumps(event)}")

    task = event.get("task", "all")
    tenant_id = event.get("tenant_id")

    results = {
        "task": task,
        "timestamp": datetime.utcnow().isoformat(),
        "success": True,
        "results": {},
    }

    conn = None

    try:
        conn = get_db_connection()
        logger.info("Database connection established")

        # Refresh materialized views
        if task in ["refresh_views", "all"]:
            logger.info("Refreshing materialized views...")
            refresh_results = refresh_materialized_views(conn, tenant_id)
            results["results"]["refresh_views"] = refresh_results

            if refresh_results["errors"]:
                results["success"] = False

        # Vacuum and analyze tables
        if task in ["vacuum_analyze", "all"]:
            logger.info("Running VACUUM ANALYZE...")
            vacuum_results = vacuum_analyze_tables(conn)
            results["results"]["vacuum_analyze"] = vacuum_results

            if vacuum_results["errors"]:
                results["success"] = False

        # Check query performance
        if task in ["check_performance", "all"]:
            logger.info("Checking query performance...")

            slow_query_results = check_slow_queries(conn)
            results["results"]["slow_queries"] = slow_query_results

            table_size_results = check_table_sizes(conn)
            results["results"]["table_sizes"] = table_size_results

        logger.info(f"Database maintenance completed: {json.dumps(results)}")

        return {"statusCode": 200, "body": json.dumps(results)}

    except Exception as e:
        logger.error(f"Database maintenance failed: {str(e)}", exc_info=True)

        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "error": str(e),
                    "task": task,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ),
        }

    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed")
