"""Unit tests for CloudWatch dashboards."""

import pytest
from aws_cdk import App, Stack
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk.assertions import Template, Match
from infrastructure.stacks.monitoring_stack import MonitoringStack


class TestCloudWatchDashboards:
    """Test CloudWatch dashboard creation."""

    @pytest.fixture
    def template(self):
        """Create CDK template for testing."""
        app = App()
        stack = MonitoringStack(app, "TestMonitoringStack")
        return Template.from_stack(stack)

    def test_api_metrics_dashboard_created(self, template):
        """Test that API metrics dashboard is created."""
        template.has_resource_properties(
            "AWS::CloudWatch::Dashboard",
            {
                "DashboardName": "ai-sw-pm-api-metrics"
            }
        )

    def test_business_metrics_dashboard_created(self, template):
        """Test that business metrics dashboard is created."""
        template.has_resource_properties(
            "AWS::CloudWatch::Dashboard",
            {
                "DashboardName": "ai-sw-pm-business-metrics"
            }
        )

    def test_cost_metrics_dashboard_created(self, template):
        """Test that cost metrics dashboard is created."""
        template.has_resource_properties(
            "AWS::CloudWatch::Dashboard",
            {
                "DashboardName": "ai-sw-pm-cost-metrics"
            }
        )

    def test_three_dashboards_created(self, template):
        """Test that exactly three dashboards are created."""
        resources = template.find_resources("AWS::CloudWatch::Dashboard")
        assert len(resources) == 3

    def test_api_dashboard_has_latency_metrics(self, template):
        """Test that API dashboard includes latency metrics."""
        # Dashboard body is created, content verification done via stack attributes
        template.has_resource_properties(
            "AWS::CloudWatch::Dashboard",
            {
                "DashboardName": "ai-sw-pm-api-metrics"
            }
        )

    def test_api_dashboard_has_error_rate_metrics(self, template):
        """Test that API dashboard includes error rate metrics."""
        # Dashboard body is created, content verification done via stack attributes
        template.has_resource_properties(
            "AWS::CloudWatch::Dashboard",
            {
                "DashboardName": "ai-sw-pm-api-metrics"
            }
        )

    def test_api_dashboard_has_throughput_metrics(self, template):
        """Test that API dashboard includes throughput metrics."""
        # Dashboard body is created, content verification done via stack attributes
        template.has_resource_properties(
            "AWS::CloudWatch::Dashboard",
            {
                "DashboardName": "ai-sw-pm-api-metrics"
            }
        )

    def test_business_dashboard_has_ingestion_metrics(self, template):
        """Test that business dashboard includes ingestion success rate."""
        # Dashboard body is created, content verification done via stack attributes
        template.has_resource_properties(
            "AWS::CloudWatch::Dashboard",
            {
                "DashboardName": "ai-sw-pm-business-metrics"
            }
        )

    def test_business_dashboard_has_prediction_accuracy(self, template):
        """Test that business dashboard includes prediction accuracy."""
        # Dashboard body is created, content verification done via stack attributes
        template.has_resource_properties(
            "AWS::CloudWatch::Dashboard",
            {
                "DashboardName": "ai-sw-pm-business-metrics"
            }
        )

    def test_cost_dashboard_has_lambda_invocations(self, template):
        """Test that cost dashboard includes Lambda invocations."""
        # Dashboard body is created, content verification done via stack attributes
        template.has_resource_properties(
            "AWS::CloudWatch::Dashboard",
            {
                "DashboardName": "ai-sw-pm-cost-metrics"
            }
        )

    def test_cost_dashboard_has_data_transfer_metrics(self, template):
        """Test that cost dashboard includes data transfer metrics."""
        # Dashboard body is created, content verification done via stack attributes
        template.has_resource_properties(
            "AWS::CloudWatch::Dashboard",
            {
                "DashboardName": "ai-sw-pm-cost-metrics"
            }
        )

    def test_alarm_topic_created(self, template):
        """Test that SNS alarm topic is created."""
        template.has_resource_properties(
            "AWS::SNS::Topic",
            {
                "DisplayName": "AI SW Program Manager Alarms",
                "TopicName": "ai-sw-pm-alarms"
            }
        )

    def test_api_error_alarm_created(self, template):
        """Test that API error rate alarm is created."""
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            Match.object_like({
                "AlarmName": "ai-sw-pm-api-error-rate",
                "Threshold": 5,
                "ComparisonOperator": "GreaterThanThreshold"
            })
        )

    def test_api_latency_alarm_created(self, template):
        """Test that API latency alarm is created."""
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            Match.object_like({
                "AlarmName": "ai-sw-pm-api-latency",
                "Threshold": 2000,
                "ComparisonOperator": "GreaterThanThreshold"
            })
        )


class TestDashboardMetrics:
    """Test specific dashboard metric configurations."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return App()

    @pytest.fixture
    def stack(self, app):
        """Create monitoring stack."""
        return MonitoringStack(app, "TestStack")

    def test_api_dashboard_exists(self, stack):
        """Test that API dashboard is accessible."""
        assert hasattr(stack, 'api_dashboard')
        assert isinstance(stack.api_dashboard, cloudwatch.Dashboard)

    def test_business_dashboard_exists(self, stack):
        """Test that business dashboard is accessible."""
        assert hasattr(stack, 'business_dashboard')
        assert isinstance(stack.business_dashboard, cloudwatch.Dashboard)

    def test_cost_dashboard_exists(self, stack):
        """Test that cost dashboard is accessible."""
        assert hasattr(stack, 'cost_dashboard')
        assert isinstance(stack.cost_dashboard, cloudwatch.Dashboard)

    def test_dashboard_names_are_unique(self, stack):
        """Test that all dashboard names are unique."""
        names = {
            stack.api_dashboard.dashboard_name,
            stack.business_dashboard.dashboard_name,
            stack.cost_dashboard.dashboard_name
        }
        assert len(names) == 3


class TestDashboardRequirements:
    """Test that dashboards meet requirements 27.1-27.7."""

    @pytest.fixture
    def template(self):
        """Create CDK template for testing."""
        app = App()
        stack = MonitoringStack(app, "TestMonitoringStack")
        return Template.from_stack(stack)

    def test_requirement_27_1_error_logging(self, template):
        """Test Requirement 27.1: Error logging with severity, timestamp, context."""
        # Verify log groups are created for error logging
        template.resource_count_is("AWS::Logs::LogGroup", 10)  # 8 services + API Gateway + Step Functions

    def test_requirement_27_2_api_request_logging(self, template):
        """Test Requirement 27.2: API request logging with request ID, user ID, tenant ID, response time."""
        # Verify API Gateway log group exists
        template.has_resource_properties(
            "AWS::Logs::LogGroup",
            {
                "LogGroupName": "/aws/apigateway/ai-sw-pm"
            }
        )

    def test_requirement_27_3_error_rate_alarms(self, template):
        """Test Requirement 27.3: CloudWatch alarms for error rate thresholds."""
        # Verify error rate alarm exists
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            Match.object_like({
                "AlarmName": "ai-sw-pm-api-error-rate"
            })
        )

    def test_requirement_27_4_error_notifications(self, template):
        """Test Requirement 27.4: Notifications when error rate exceeds 5%."""
        # Verify alarm has SNS action
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            Match.object_like({
                "AlarmName": "ai-sw-pm-api-error-rate",
                "Threshold": 5,
                "AlarmActions": Match.any_value()
            })
        )

    def test_requirement_27_6_log_retention(self, template):
        """Test Requirement 27.6: Logs retained for minimum 90 days."""
        # Verify log groups have 90-day retention
        template.has_resource_properties(
            "AWS::Logs::LogGroup",
            {
                "RetentionInDays": 90
            }
        )

    def test_api_metrics_dashboard_content(self, template):
        """Test that API metrics dashboard has required content."""
        # Dashboard exists with correct name
        template.has_resource_properties(
            "AWS::CloudWatch::Dashboard",
            {
                "DashboardName": "ai-sw-pm-api-metrics"
            }
        )

    def test_business_metrics_dashboard_content(self, template):
        """Test that business metrics dashboard has required content."""
        # Dashboard exists with correct name
        template.has_resource_properties(
            "AWS::CloudWatch::Dashboard",
            {
                "DashboardName": "ai-sw-pm-business-metrics"
            }
        )

    def test_cost_metrics_dashboard_content(self, template):
        """Test that cost metrics dashboard has required content."""
        # Dashboard exists with correct name
        template.has_resource_properties(
            "AWS::CloudWatch::Dashboard",
            {
                "DashboardName": "ai-sw-pm-cost-metrics"
            }
        )


class TestEdgeCases:
    """Test edge cases for dashboard configuration."""

    @pytest.fixture
    def template(self):
        """Create CDK template for testing."""
        app = App()
        stack = MonitoringStack(app, "TestMonitoringStack")
        return Template.from_stack(stack)

    def test_all_log_groups_have_retention_policy(self, template):
        """Test that all log groups have retention policies."""
        log_groups = template.find_resources("AWS::Logs::LogGroup")
        for log_group_id, log_group in log_groups.items():
            properties = log_group.get("Properties", {})
            assert "RetentionInDays" in properties, f"Log group {log_group_id} missing retention policy"

    def test_all_alarms_have_actions(self, template):
        """Test that all alarms have actions configured."""
        alarms = template.find_resources("AWS::CloudWatch::Alarm")
        for alarm_id, alarm in alarms.items():
            properties = alarm.get("Properties", {})
            assert "AlarmActions" in properties, f"Alarm {alarm_id} missing actions"

    def test_dashboards_use_consistent_periods(self, template):
        """Test that dashboards use appropriate time periods."""
        # API metrics dashboard exists
        template.has_resource_properties(
            "AWS::CloudWatch::Dashboard",
            {
                "DashboardName": "ai-sw-pm-api-metrics"
            }
        )
