#!/usr/bin/env python3
"""AWS CDK application entry point."""

import os
import aws_cdk as cdk
from stacks.auth_stack import AuthStack
from stacks.vpc_network_security_stack import VpcNetworkSecurityStack
from stacks.database_stack import DatabaseStack
from stacks.storage_stack import StorageStack
from stacks.cache_stack import CacheStack
from stacks.monitoring_stack import MonitoringStack
from stacks.ingestion_workflow_stack import IngestionWorkflowStack
from stacks.api_gateway_stack import ApiGatewayStack
from stacks.audit_logging_stack import AuditLoggingStack

app = cdk.App()

# Get environment configuration
env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
)

# Stack naming prefix
stack_prefix = "AISWProgramManager"

# Authentication stack - Cognito User Pool
auth_stack = AuthStack(
    app,
    f"{stack_prefix}-Auth",
    env=env,
    description="Authentication resources for AI SW Program Manager"
)

# VPC and Network Security stack - VPC, security groups, flow logs
vpc_network_stack = VpcNetworkSecurityStack(
    app,
    f"{stack_prefix}-VPCNetworkSecurity",
    env=env,
    description="VPC and network security configuration for AI SW Program Manager"
)

# Database stack - DynamoDB tables and RDS PostgreSQL
database_stack = DatabaseStack(
    app,
    f"{stack_prefix}-Database",
    vpc=vpc_network_stack.vpc,
    rds_security_group=vpc_network_stack.rds_security_group,
    env=env,
    description="Database resources for AI SW Program Manager"
)

# Storage stack - S3 buckets and OpenSearch domain
storage_stack = StorageStack(
    app,
    f"{stack_prefix}-Storage",
    vpc=vpc_network_stack.vpc,
    opensearch_security_group=vpc_network_stack.opensearch_security_group,
    env=env,
    description="Storage resources for AI SW Program Manager"
)

# Cache stack - ElastiCache Redis for dashboard and report caching
cache_stack = CacheStack(
    app,
    f"{stack_prefix}-Cache",
    vpc=vpc_network_stack.vpc,
    env=env,
    description="ElastiCache Redis for dashboard and report caching"
)

# Monitoring stack - CloudWatch log groups and X-Ray
monitoring_stack = MonitoringStack(
    app,
    f"{stack_prefix}-Monitoring",
    env=env,
    description="Monitoring and observability resources for AI SW Program Manager"
)

# Audit Logging stack - CloudTrail, log retention, and log aggregation
audit_logging_stack = AuditLoggingStack(
    app,
    f"{stack_prefix}-AuditLogging",
    alarm_topic=monitoring_stack.alarm_topic,
    env=env,
    description="Comprehensive audit logging with CloudTrail and log aggregation"
)

# Ingestion Workflow stack - Step Functions orchestration
ingestion_workflow_stack = IngestionWorkflowStack(
    app,
    f"{stack_prefix}-IngestionWorkflow",
    integrations_table_name=database_stack.integrations_table.table_name,
    env=env,
    description="Data ingestion workflow orchestration for AI SW Program Manager"
)

# API Gateway stack - REST API with Lambda integrations
api_gateway_stack = ApiGatewayStack(
    app,
    f"{stack_prefix}-APIGateway",
    user_pool=auth_stack.user_pool,
    user_pool_client=auth_stack.user_pool_client,
    authorizer_function=auth_stack.authorizer_function,
    users_table=database_stack.users_table,
    integrations_table=database_stack.integrations_table,
    risks_table=database_stack.risks_table,
    predictions_table=database_stack.predictions_table,
    reports_table=database_stack.reports_table,
    alarm_topic=monitoring_stack.alarm_topic,
    env=env,
    description="API Gateway and Lambda integrations for AI SW Program Manager"
)

# Add dependencies
database_stack.add_dependency(vpc_network_stack)
storage_stack.add_dependency(vpc_network_stack)
cache_stack.add_dependency(vpc_network_stack)
audit_logging_stack.add_dependency(monitoring_stack)
ingestion_workflow_stack.add_dependency(database_stack)
api_gateway_stack.add_dependency(auth_stack)
api_gateway_stack.add_dependency(database_stack)
api_gateway_stack.add_dependency(monitoring_stack)

# Add tags to all stacks
for stack in [
    auth_stack,
    vpc_network_stack,
    database_stack,
    storage_stack,
    cache_stack,
    monitoring_stack,
    audit_logging_stack,
    ingestion_workflow_stack,
    api_gateway_stack
]:
    cdk.Tags.of(stack).add("Project", "AI-SW-Program-Manager")
    cdk.Tags.of(stack).add("ManagedBy", "CDK")

app.synth()
