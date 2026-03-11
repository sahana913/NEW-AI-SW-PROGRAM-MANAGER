"""Monitoring stack - CloudWatch log groups and X-Ray tracing."""

from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    aws_logs as logs,
    aws_cloudwatch as cloudwatch,
    aws_sns as sns,
    aws_sns_subscriptions as sns_subscriptions,
    aws_cloudwatch_actions as cw_actions,
)
from constructs import Construct


class MonitoringStack(Stack):
    """Stack for monitoring and observability resources."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create SNS topic for alarms
        self._create_alarm_topic()

        # Create CloudWatch log groups
        self._create_log_groups()

        # Create CloudWatch alarms
        self._create_alarms()

        # Create CloudWatch dashboard
        self._create_dashboard()

    def _create_alarm_topic(self) -> None:
        """Create SNS topic for CloudWatch alarms."""

        self.alarm_topic = sns.Topic(
            self,
            "AlarmTopic",
            display_name="AI SW Program Manager Alarms",
            topic_name="ai-sw-pm-alarms"
        )

        # Add email subscription (will be configured via console or CLI)
        # self.alarm_topic.add_subscription(
        #     sns_subscriptions.EmailSubscription("admin@example.com")
        # )

    def _create_log_groups(self) -> None:
        """Create CloudWatch log groups for Lambda functions."""

        # Service-specific log groups
        services = [
            "auth",
            "user-management",
            "data-ingestion",
            "risk-detection",
            "prediction",
            "document-intelligence",
            "report-generation",
            "dashboard"
        ]

        self.log_groups = {}

        for service in services:
            log_group = logs.LogGroup(
                self,
                f"{service.title().replace('-', '')}LogGroup",
                log_group_name=f"/aws/lambda/ai-sw-pm-{service}",
                retention=logs.RetentionDays.THREE_MONTHS,
                removal_policy=RemovalPolicy.RETAIN
            )
            self.log_groups[service] = log_group

        # API Gateway log group
        self.api_gateway_log_group = logs.LogGroup(
            self,
            "APIGatewayLogGroup",
            log_group_name="/aws/apigateway/ai-sw-pm",
            retention=logs.RetentionDays.THREE_MONTHS,
            removal_policy=RemovalPolicy.RETAIN
        )

        # Step Functions log group
        self.step_functions_log_group = logs.LogGroup(
            self,
            "StepFunctionsLogGroup",
            log_group_name="/aws/states/ai-sw-pm",
            retention=logs.RetentionDays.THREE_MONTHS,
            removal_policy=RemovalPolicy.RETAIN
        )

    def _create_alarms(self) -> None:
        """Create CloudWatch alarms for monitoring."""

        # Note: Specific metrics will be created when Lambda functions are deployed
        # These are placeholder alarm configurations

        # API Gateway error rate alarm
        self.api_error_alarm = cloudwatch.Alarm(
            self,
            "APIErrorRateAlarm",
            alarm_name="ai-sw-pm-api-error-rate",
            alarm_description="Alert when API error rate exceeds 5%",
            metric=cloudwatch.Metric(
                namespace="AWS/ApiGateway",
                metric_name="5XXError",
                statistic="Sum",
                period=Duration.minutes(5)
            ),
            threshold=5,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )

        self.api_error_alarm.add_alarm_action(
            cw_actions.SnsAction(self.alarm_topic)
        )

        # API Gateway latency alarm
        self.api_latency_alarm = cloudwatch.Alarm(
            self,
            "APILatencyAlarm",
            alarm_name="ai-sw-pm-api-latency",
            alarm_description="Alert when API latency exceeds 2 seconds",
            metric=cloudwatch.Metric(
                namespace="AWS/ApiGateway",
                metric_name="Latency",
                statistic="Average",
                period=Duration.minutes(5)
            ),
            threshold=2000,  # milliseconds
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )

        self.api_latency_alarm.add_alarm_action(
            cw_actions.SnsAction(self.alarm_topic)
        )

    def _create_dashboard(self) -> None:
        """Create CloudWatch dashboards for monitoring."""
        
        # Create three separate dashboards as per requirements
        self._create_api_metrics_dashboard()
        self._create_business_metrics_dashboard()
        self._create_cost_metrics_dashboard()

    def _create_api_metrics_dashboard(self) -> None:
        """Create dashboard for API metrics (latency, error rate, throughput)."""
        
        self.api_dashboard = cloudwatch.Dashboard(
            self,
            "APIDashboard",
            dashboard_name="ai-sw-pm-api-metrics"
        )

        # Row 1: Throughput metrics
        self.api_dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="API Request Throughput",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="Count",
                        statistic="Sum",
                        period=Duration.minutes(5),
                        label="Total Requests"
                    )
                ],
                width=12,
                height=6
            ),
            cloudwatch.SingleValueWidget(
                title="Requests (Last 5 min)",
                metrics=[
                    cloudwatch.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="Count",
                        statistic="Sum",
                        period=Duration.minutes(5)
                    )
                ],
                width=6,
                height=6
            ),
            cloudwatch.SingleValueWidget(
                title="Requests Per Second",
                metrics=[
                    cloudwatch.MathExpression(
                        expression="m1/300",
                        using_metrics={
                            "m1": cloudwatch.Metric(
                                namespace="AWS/ApiGateway",
                                metric_name="Count",
                                statistic="Sum",
                                period=Duration.minutes(5)
                            )
                        },
                        label="RPS"
                    )
                ],
                width=6,
                height=6
            )
        )

        # Row 2: Error rate metrics
        self.api_dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="API Error Rate",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="4XXError",
                        statistic="Sum",
                        period=Duration.minutes(5),
                        label="4XX Errors",
                        color="#FF9900"
                    ),
                    cloudwatch.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="5XXError",
                        statistic="Sum",
                        period=Duration.minutes(5),
                        label="5XX Errors",
                        color="#D13212"
                    )
                ],
                width=12,
                height=6
            ),
            cloudwatch.GraphWidget(
                title="Error Rate Percentage",
                left=[
                    cloudwatch.MathExpression(
                        expression="(m1+m2)/m3*100",
                        using_metrics={
                            "m1": cloudwatch.Metric(
                                namespace="AWS/ApiGateway",
                                metric_name="4XXError",
                                statistic="Sum",
                                period=Duration.minutes(5)
                            ),
                            "m2": cloudwatch.Metric(
                                namespace="AWS/ApiGateway",
                                metric_name="5XXError",
                                statistic="Sum",
                                period=Duration.minutes(5)
                            ),
                            "m3": cloudwatch.Metric(
                                namespace="AWS/ApiGateway",
                                metric_name="Count",
                                statistic="Sum",
                                period=Duration.minutes(5)
                            )
                        },
                        label="Error Rate %"
                    )
                ],
                width=12,
                height=6
            )
        )

        # Row 3: Latency metrics
        self.api_dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="API Latency (ms)",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="Latency",
                        statistic="Average",
                        period=Duration.minutes(5),
                        label="Average",
                        color="#1F77B4"
                    ),
                    cloudwatch.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="Latency",
                        statistic="p50",
                        period=Duration.minutes(5),
                        label="P50",
                        color="#2CA02C"
                    ),
                    cloudwatch.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="Latency",
                        statistic="p90",
                        period=Duration.minutes(5),
                        label="P90",
                        color="#FF7F0E"
                    ),
                    cloudwatch.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="Latency",
                        statistic="p99",
                        period=Duration.minutes(5),
                        label="P99",
                        color="#D62728"
                    )
                ],
                width=18,
                height=6
            ),
            cloudwatch.SingleValueWidget(
                title="Current P99 Latency (ms)",
                metrics=[
                    cloudwatch.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="Latency",
                        statistic="p99",
                        period=Duration.minutes(5)
                    )
                ],
                width=6,
                height=6
            )
        )

        # Row 4: Integration latency
        self.api_dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Integration Latency (Backend Processing)",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="IntegrationLatency",
                        statistic="Average",
                        period=Duration.minutes(5),
                        label="Average"
                    ),
                    cloudwatch.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="IntegrationLatency",
                        statistic="p99",
                        period=Duration.minutes(5),
                        label="P99"
                    )
                ],
                width=24,
                height=6
            )
        )

    def _create_business_metrics_dashboard(self) -> None:
        """Create dashboard for business metrics (ingestion success rate, prediction accuracy)."""
        
        self.business_dashboard = cloudwatch.Dashboard(
            self,
            "BusinessDashboard",
            dashboard_name="ai-sw-pm-business-metrics"
        )

        # Row 1: Data ingestion metrics
        self.business_dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Data Ingestion Success Rate",
                left=[
                    cloudwatch.Metric(
                        namespace="AISWProgramManager",
                        metric_name="IngestionSuccess",
                        statistic="Sum",
                        period=Duration.hours(1),
                        label="Successful Ingestions",
                        color="#2CA02C"
                    ),
                    cloudwatch.Metric(
                        namespace="AISWProgramManager",
                        metric_name="IngestionFailure",
                        statistic="Sum",
                        period=Duration.hours(1),
                        label="Failed Ingestions",
                        color="#D62728"
                    )
                ],
                width=12,
                height=6
            ),
            cloudwatch.GraphWidget(
                title="Ingestion Success Rate %",
                left=[
                    cloudwatch.MathExpression(
                        expression="m1/(m1+m2)*100",
                        using_metrics={
                            "m1": cloudwatch.Metric(
                                namespace="AISWProgramManager",
                                metric_name="IngestionSuccess",
                                statistic="Sum",
                                period=Duration.hours(1)
                            ),
                            "m2": cloudwatch.Metric(
                                namespace="AISWProgramManager",
                                metric_name="IngestionFailure",
                                statistic="Sum",
                                period=Duration.hours(1)
                            )
                        },
                        label="Success Rate %"
                    )
                ],
                width=12,
                height=6
            )
        )

        # Row 2: Ingestion volume and duration
        self.business_dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Records Ingested",
                left=[
                    cloudwatch.Metric(
                        namespace="AISWProgramManager",
                        metric_name="RecordsIngested",
                        statistic="Sum",
                        period=Duration.hours(1),
                        label="Total Records"
                    )
                ],
                width=12,
                height=6
            ),
            cloudwatch.GraphWidget(
                title="Ingestion Duration (seconds)",
                left=[
                    cloudwatch.Metric(
                        namespace="AISWProgramManager",
                        metric_name="IngestionDuration",
                        statistic="Average",
                        period=Duration.hours(1),
                        label="Average Duration"
                    ),
                    cloudwatch.Metric(
                        namespace="AISWProgramManager",
                        metric_name="IngestionDuration",
                        statistic="Maximum",
                        period=Duration.hours(1),
                        label="Max Duration"
                    )
                ],
                width=12,
                height=6
            )
        )

        # Row 3: Prediction accuracy metrics
        self.business_dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Prediction Accuracy",
                left=[
                    cloudwatch.Metric(
                        namespace="AISWProgramManager",
                        metric_name="DelayPredictionAccuracy",
                        statistic="Average",
                        period=Duration.days(1),
                        label="Delay Prediction Accuracy %",
                        color="#1F77B4"
                    ),
                    cloudwatch.Metric(
                        namespace="AISWProgramManager",
                        metric_name="WorkloadPredictionAccuracy",
                        statistic="Average",
                        period=Duration.days(1),
                        label="Workload Prediction Accuracy %",
                        color="#FF7F0E"
                    )
                ],
                width=12,
                height=6
            ),
            cloudwatch.GraphWidget(
                title="Prediction Confidence Scores",
                left=[
                    cloudwatch.Metric(
                        namespace="AISWProgramManager",
                        metric_name="PredictionConfidence",
                        statistic="Average",
                        period=Duration.hours(1),
                        label="Average Confidence"
                    )
                ],
                width=12,
                height=6
            )
        )

        # Row 4: Risk detection metrics
        self.business_dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Risks Detected by Severity",
                left=[
                    cloudwatch.Metric(
                        namespace="AISWProgramManager",
                        metric_name="RisksDetected",
                        statistic="Sum",
                        period=Duration.hours(1),
                        dimensions_map={"Severity": "CRITICAL"},
                        label="Critical",
                        color="#D13212"
                    ),
                    cloudwatch.Metric(
                        namespace="AISWProgramManager",
                        metric_name="RisksDetected",
                        statistic="Sum",
                        period=Duration.hours(1),
                        dimensions_map={"Severity": "HIGH"},
                        label="High",
                        color="#FF9900"
                    ),
                    cloudwatch.Metric(
                        namespace="AISWProgramManager",
                        metric_name="RisksDetected",
                        statistic="Sum",
                        period=Duration.hours(1),
                        dimensions_map={"Severity": "MEDIUM"},
                        label="Medium",
                        color="#FFD700"
                    ),
                    cloudwatch.Metric(
                        namespace="AISWProgramManager",
                        metric_name="RisksDetected",
                        statistic="Sum",
                        period=Duration.hours(1),
                        dimensions_map={"Severity": "LOW"},
                        label="Low",
                        color="#1F77B4"
                    )
                ],
                width=12,
                height=6
            ),
            cloudwatch.GraphWidget(
                title="Document Processing Success Rate",
                left=[
                    cloudwatch.MathExpression(
                        expression="m1/(m1+m2)*100",
                        using_metrics={
                            "m1": cloudwatch.Metric(
                                namespace="AISWProgramManager",
                                metric_name="DocumentProcessingSuccess",
                                statistic="Sum",
                                period=Duration.hours(1)
                            ),
                            "m2": cloudwatch.Metric(
                                namespace="AISWProgramManager",
                                metric_name="DocumentProcessingFailure",
                                statistic="Sum",
                                period=Duration.hours(1)
                            )
                        },
                        label="Success Rate %"
                    )
                ],
                width=12,
                height=6
            )
        )

        # Row 5: Report generation metrics
        self.business_dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Reports Generated",
                left=[
                    cloudwatch.Metric(
                        namespace="AISWProgramManager",
                        metric_name="ReportsGenerated",
                        statistic="Sum",
                        period=Duration.hours(1),
                        dimensions_map={"ReportType": "WEEKLY_STATUS"},
                        label="Weekly Status"
                    ),
                    cloudwatch.Metric(
                        namespace="AISWProgramManager",
                        metric_name="ReportsGenerated",
                        statistic="Sum",
                        period=Duration.hours(1),
                        dimensions_map={"ReportType": "EXECUTIVE_SUMMARY"},
                        label="Executive Summary"
                    )
                ],
                width=12,
                height=6
            ),
            cloudwatch.GraphWidget(
                title="Report Generation Duration (seconds)",
                left=[
                    cloudwatch.Metric(
                        namespace="AISWProgramManager",
                        metric_name="ReportGenerationDuration",
                        statistic="Average",
                        period=Duration.hours(1),
                        label="Average"
                    ),
                    cloudwatch.Metric(
                        namespace="AISWProgramManager",
                        metric_name="ReportGenerationDuration",
                        statistic="p99",
                        period=Duration.hours(1),
                        label="P99"
                    )
                ],
                width=12,
                height=6
            )
        )

    def _create_cost_metrics_dashboard(self) -> None:
        """Create dashboard for cost metrics (Lambda invocations, data transfer)."""
        
        self.cost_dashboard = cloudwatch.Dashboard(
            self,
            "CostDashboard",
            dashboard_name="ai-sw-pm-cost-metrics"
        )

        # Row 1: Lambda invocation costs
        self.cost_dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Lambda Invocations (All Functions)",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/Lambda",
                        metric_name="Invocations",
                        statistic="Sum",
                        period=Duration.hours(1),
                        label="Total Invocations"
                    )
                ],
                width=12,
                height=6
            ),
            cloudwatch.SingleValueWidget(
                title="Lambda Invocations (Last Hour)",
                metrics=[
                    cloudwatch.Metric(
                        namespace="AWS/Lambda",
                        metric_name="Invocations",
                        statistic="Sum",
                        period=Duration.hours(1)
                    )
                ],
                width=6,
                height=6
            ),
            cloudwatch.SingleValueWidget(
                title="Lambda Invocations (Last 24h)",
                metrics=[
                    cloudwatch.Metric(
                        namespace="AWS/Lambda",
                        metric_name="Invocations",
                        statistic="Sum",
                        period=Duration.days(1)
                    )
                ],
                width=6,
                height=6
            )
        )

        # Row 2: Lambda duration (compute time = cost)
        self.cost_dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Lambda Duration (Compute Time)",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/Lambda",
                        metric_name="Duration",
                        statistic="Average",
                        period=Duration.hours(1),
                        label="Average Duration (ms)"
                    ),
                    cloudwatch.Metric(
                        namespace="AWS/Lambda",
                        metric_name="Duration",
                        statistic="Sum",
                        period=Duration.hours(1),
                        label="Total Duration (ms)"
                    )
                ],
                width=12,
                height=6
            ),
            cloudwatch.GraphWidget(
                title="Lambda Concurrent Executions",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/Lambda",
                        metric_name="ConcurrentExecutions",
                        statistic="Maximum",
                        period=Duration.minutes(5),
                        label="Max Concurrent"
                    )
                ],
                width=12,
                height=6
            )
        )

        # Row 3: Data transfer costs
        self.cost_dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="API Gateway Data Transfer (Bytes)",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="DataProcessed",
                        statistic="Sum",
                        period=Duration.hours(1),
                        label="Data Processed"
                    )
                ],
                width=12,
                height=6
            ),
            cloudwatch.GraphWidget(
                title="S3 Data Transfer",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/S3",
                        metric_name="BytesDownloaded",
                        statistic="Sum",
                        period=Duration.hours(1),
                        label="Bytes Downloaded"
                    ),
                    cloudwatch.Metric(
                        namespace="AWS/S3",
                        metric_name="BytesUploaded",
                        statistic="Sum",
                        period=Duration.hours(1),
                        label="Bytes Uploaded"
                    )
                ],
                width=12,
                height=6
            )
        )

        # Row 4: DynamoDB costs
        self.cost_dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="DynamoDB Read/Write Units",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/DynamoDB",
                        metric_name="ConsumedReadCapacityUnits",
                        statistic="Sum",
                        period=Duration.hours(1),
                        label="Read Units"
                    ),
                    cloudwatch.Metric(
                        namespace="AWS/DynamoDB",
                        metric_name="ConsumedWriteCapacityUnits",
                        statistic="Sum",
                        period=Duration.hours(1),
                        label="Write Units"
                    )
                ],
                width=12,
                height=6
            ),
            cloudwatch.GraphWidget(
                title="DynamoDB Throttled Requests",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/DynamoDB",
                        metric_name="UserErrors",
                        statistic="Sum",
                        period=Duration.hours(1),
                        label="Throttled Requests"
                    )
                ],
                width=12,
                height=6
            )
        )

        # Row 5: AI/ML service costs
        self.cost_dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Bedrock API Invocations",
                left=[
                    cloudwatch.Metric(
                        namespace="AISWProgramManager",
                        metric_name="BedrockInvocations",
                        statistic="Sum",
                        period=Duration.hours(1),
                        label="Total Invocations"
                    )
                ],
                width=12,
                height=6
            ),
            cloudwatch.GraphWidget(
                title="SageMaker Endpoint Invocations",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/SageMaker",
                        metric_name="ModelInvocations",
                        statistic="Sum",
                        period=Duration.hours(1),
                        label="Model Invocations"
                    )
                ],
                width=12,
                height=6
            )
        )

        # Row 6: Cost summary widgets
        self.cost_dashboard.add_widgets(
            cloudwatch.SingleValueWidget(
                title="Estimated Lambda Cost (Last 24h)",
                metrics=[
                    cloudwatch.MathExpression(
                        expression="(m1 * 0.0000166667) / 1000",
                        using_metrics={
                            "m1": cloudwatch.Metric(
                                namespace="AWS/Lambda",
                                metric_name="Duration",
                                statistic="Sum",
                                period=Duration.days(1)
                            )
                        },
                        label="Estimated Cost ($)"
                    )
                ],
                width=8,
                height=6
            ),
            cloudwatch.SingleValueWidget(
                title="API Requests (Last 24h)",
                metrics=[
                    cloudwatch.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="Count",
                        statistic="Sum",
                        period=Duration.days(1)
                    )
                ],
                width=8,
                height=6
            ),
            cloudwatch.SingleValueWidget(
                title="Total Data Transfer (Last 24h, GB)",
                metrics=[
                    cloudwatch.MathExpression(
                        expression="m1 / 1073741824",
                        using_metrics={
                            "m1": cloudwatch.Metric(
                                namespace="AWS/ApiGateway",
                                metric_name="DataProcessed",
                                statistic="Sum",
                                period=Duration.days(1)
                            )
                        },
                        label="Data Transfer (GB)"
                    )
                ],
                width=8,
                height=6
            )
        )
