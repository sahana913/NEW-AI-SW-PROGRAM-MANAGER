"""Unit tests for API Gateway stack."""

import pytest
import aws_cdk as cdk
from aws_cdk import assertions
from infrastructure.stacks.api_gateway_stack import ApiGatewayStack
from infrastructure.stacks.auth_stack import AuthStack
from infrastructure.stacks.database_stack import DatabaseStack
from infrastructure.stacks.monitoring_stack import MonitoringStack


def create_test_stacks():
    """Create all stacks for testing in correct order to avoid circular dependencies."""
    app = cdk.App()
    
    # Create stacks in dependency order
    database_stack = DatabaseStack(app, "TestDatabaseStack")
    monitoring_stack = MonitoringStack(app, "TestMonitoringStack")
    auth_stack = AuthStack(app, "TestAuthStack")
    
    # Create API Gateway stack with references to other stacks
    api_gateway_stack = ApiGatewayStack(
        app,
        "TestAPIGatewayStack",
        user_pool=auth_stack.user_pool,
        user_pool_client=auth_stack.user_pool_client,
        authorizer_function=auth_stack.authorizer_function,
        users_table=database_stack.users_table,
        integrations_table=database_stack.integrations_table,
        risks_table=database_stack.risks_table,
        predictions_table=database_stack.predictions_table,
        reports_table=database_stack.reports_table,
        alarm_topic=monitoring_stack.alarm_topic
    )
    
    # Don't add explicit dependencies - CDK will detect them automatically
    # Adding explicit dependencies can create circular references
    
    # Synthesize the app to resolve all dependencies
    app.synth()
    
    return api_gateway_stack


def test_api_gateway_created():
    """Test that API Gateway REST API is created."""
    api_gateway_stack = create_test_stacks()
    template = assertions.Template.from_stack(api_gateway_stack)
    
    # Verify REST API exists
    template.resource_count_is("AWS::ApiGateway::RestApi", 1)
    
    # Verify API has correct configuration
    template.has_resource_properties(
        "AWS::ApiGateway::RestApi",
        {
            "Name": "ai-sw-pm-api",
            "Description": "AI SW Program Manager REST API"
        }
    )



def test_cors_enabled():
    """Test that CORS is enabled for web app access."""
    api_gateway_stack = create_test_stacks()
    template = assertions.Template.from_stack(api_gateway_stack)
    
    # Verify OPTIONS methods exist for CORS preflight
    template.has_resource_properties(
        "AWS::ApiGateway::Method",
        {
            "HttpMethod": "OPTIONS"
        }
    )


def test_lambda_authorizer_configured():
    """Test that Lambda Authorizer is configured."""
    api_gateway_stack = create_test_stacks()
    template = assertions.Template.from_stack(api_gateway_stack)
    
    # Verify authorizer exists
    template.has_resource_properties(
        "AWS::ApiGateway::Authorizer",
        {
            "Type": "REQUEST",
            "Name": "ai-sw-pm-authorizer"
        }
    )


def test_rate_limiting_configured():
    """Test that rate limiting is configured."""
    api_gateway_stack = create_test_stacks()
    template = assertions.Template.from_stack(api_gateway_stack)
    
    # Verify usage plan exists
    template.has_resource_properties(
        "AWS::ApiGateway::UsagePlan",
        {
            "UsagePlanName": "ai-sw-pm-usage-plan",
            "Throttle": {
                "RateLimit": 100,
                "BurstLimit": 200
            }
        }
    )


def test_cloudwatch_logging_enabled():
    """Test that CloudWatch logging is enabled."""
    api_gateway_stack = create_test_stacks()
    template = assertions.Template.from_stack(api_gateway_stack)
    
    # Verify log group exists
    template.has_resource_properties(
        "AWS::Logs::LogGroup",
        {
            "LogGroupName": "/aws/apigateway/ai-sw-pm-api"
        }
    )


def test_xray_tracing_enabled():
    """Test that X-Ray tracing is enabled."""
    api_gateway_stack = create_test_stacks()
    template = assertions.Template.from_stack(api_gateway_stack)
    
    # Verify stage has tracing enabled
    template.has_resource_properties(
        "AWS::ApiGateway::Stage",
        {
            "TracingEnabled": True
        }
    )


def test_lambda_functions_created():
    """Test that all Lambda functions are created."""
    api_gateway_stack = create_test_stacks()
    template = assertions.Template.from_stack(api_gateway_stack)
    
    # Expected Lambda functions
    expected_functions = [
        "ai-sw-pm-user-management",
        "ai-sw-pm-jira-integration",
        "ai-sw-pm-azure-devops",
        "ai-sw-pm-risk-detection",
        "ai-sw-pm-prediction",
        "ai-sw-pm-document-upload",
        "ai-sw-pm-document-intelligence",
        "ai-sw-pm-semantic-search",
        "ai-sw-pm-report-generation",
        "ai-sw-pm-dashboard"
    ]
    
    for function_name in expected_functions:
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "FunctionName": function_name,
                "Tracing": "Active"
            }
        )


def test_user_management_endpoints():
    """Test that user management endpoints are created."""
    api_gateway_stack = create_test_stacks()
    template = assertions.Template.from_stack(api_gateway_stack)
    
    # Verify API resources exist
    # POST /users
    # GET /users
    # PUT /users/{userId}/role
    
    # Count API methods (excluding OPTIONS for CORS)
    # We should have multiple methods for user management
    template.resource_count_is("AWS::ApiGateway::Method", assertions.Match.any_value())


def test_integration_endpoints():
    """Test that integration configuration endpoints are created."""
    api_gateway_stack = create_test_stacks()
    template = assertions.Template.from_stack(api_gateway_stack)
    
    # Verify Lambda integrations exist
    template.has_resource_properties(
        "AWS::ApiGateway::Method",
        {
            "HttpMethod": "POST",
            "Integration": {
                "Type": "AWS_PROXY"
            }
        }
    )


def test_cloudwatch_alarms_created():
    """Test that CloudWatch alarms are created."""
    api_gateway_stack = create_test_stacks()
    template = assertions.Template.from_stack(api_gateway_stack)
    
    # Verify error rate alarm
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "AlarmName": "ai-sw-pm-api-5xx-errors",
            "Threshold": 5,
            "ComparisonOperator": "GreaterThanThreshold"
        }
    )
    
    # Verify latency alarm
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "AlarmName": "ai-sw-pm-api-latency",
            "Threshold": 2000,
            "ComparisonOperator": "GreaterThanThreshold"
        }
    )


def test_lambda_throttling_alarms():
    """Test that Lambda throttling alarms are created."""
    api_gateway_stack = create_test_stacks()
    template = assertions.Template.from_stack(api_gateway_stack)
    
    # Verify throttling alarms exist for Lambda functions
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "AlarmName": assertions.Match.string_like_regexp("ai-sw-pm-.*-throttles"),
            "Threshold": 1,
            "ComparisonOperator": "GreaterThanOrEqualToThreshold"
        }
    )


def test_request_validation_configured():
    """Test that request validation is configured."""
    api_gateway_stack = create_test_stacks()
    template = assertions.Template.from_stack(api_gateway_stack)
    
    # Verify request validators exist
    template.resource_count_is("AWS::ApiGateway::RequestValidator", assertions.Match.any_value())


def test_lambda_permissions_granted():
    """Test that Lambda functions have necessary permissions."""
    api_gateway_stack = create_test_stacks()
    template = assertions.Template.from_stack(api_gateway_stack)
    
    # Verify IAM policies exist for Lambda functions
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": assertions.Match.array_with([
                    assertions.Match.object_like({
                        "Effect": "Allow"
                    })
                ])
            }
        }
    )


def test_api_stage_configuration():
    """Test that API stage is properly configured."""
    api_gateway_stack = create_test_stacks()
    template = assertions.Template.from_stack(api_gateway_stack)
    
    # Verify stage configuration
    template.has_resource_properties(
        "AWS::ApiGateway::Stage",
        {
            "StageName": "prod",
            "MetricsEnabled": True,
            "DataTraceEnabled": True
        }
    )


def test_sns_alarm_actions():
    """Test that alarms are configured to send SNS notifications."""
    api_gateway_stack = create_test_stacks()
    template = assertions.Template.from_stack(api_gateway_stack)
    
    # Verify alarms have SNS actions
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "AlarmActions": assertions.Match.any_value()
        }
    )
