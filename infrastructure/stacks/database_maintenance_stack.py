"""Database Maintenance Stack - Scheduled database optimization tasks."""

from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct


class DatabaseMaintenanceStack(Stack):
    """Stack for database maintenance Lambda and scheduling."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        database_stack,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create Lambda function for database maintenance
        self.maintenance_function = lambda_.Function(
            self,
            "DatabaseMaintenanceFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("../src/database_maintenance"),
            timeout=Duration.minutes(15),  # Long timeout for VACUUM operations
            memory_size=512,
            environment={
                "DB_SECRET_ARN": database_stack.db_credentials.secret_arn,
                "DB_NAME": "ai_sw_program_manager"
            },
            vpc=database_stack.vpc,
            vpc_subnets=database_stack.vpc.select_subnets(
                subnet_type=database_stack.vpc.private_subnets[0].subnet_type
            ),
            log_retention=logs.RetentionDays.ONE_MONTH,
            description="Performs scheduled database maintenance tasks"
        )

        # Grant permissions to read database credentials
        database_stack.db_credentials.grant_read(self.maintenance_function)

        # Grant permissions to connect to RDS
        database_stack.db_security_group.add_ingress_rule(
            peer=self.maintenance_function.connections.security_groups[0],
            connection=database_stack.db_instance.connections.default_port,
            description="Allow Lambda to connect to RDS"
        )

        # Grant CloudWatch permissions for custom metrics
        self.maintenance_function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "cloudwatch:PutMetricData"
                ],
                resources=["*"]
            )
        )

        # ========================================================================
        # SCHEDULE 1: Refresh Materialized Views (Every 5 minutes)
        # ========================================================================
        # This ensures dashboard queries are fast and meet the 2-second requirement
        
        self.refresh_views_rule = events.Rule(
            self,
            "RefreshViewsSchedule",
            description="Refresh materialized views every 5 minutes",
            schedule=events.Schedule.rate(Duration.minutes(5))
        )

        self.refresh_views_rule.add_target(
            targets.LambdaFunction(
                self.maintenance_function,
                event=events.RuleTargetInput.from_object({
                    "task": "refresh_views"
                })
            )
        )

        # ========================================================================
        # SCHEDULE 2: VACUUM ANALYZE (Daily at 2 AM UTC)
        # ========================================================================
        # This updates query planner statistics for optimal query performance
        
        self.vacuum_analyze_rule = events.Rule(
            self,
            "VacuumAnalyzeSchedule",
            description="Run VACUUM ANALYZE daily at 2 AM UTC",
            schedule=events.Schedule.cron(
                minute="0",
                hour="2",
                month="*",
                week_day="*",
                year="*"
            )
        )

        self.vacuum_analyze_rule.add_target(
            targets.LambdaFunction(
                self.maintenance_function,
                event=events.RuleTargetInput.from_object({
                    "task": "vacuum_analyze"
                })
            )
        )

        # ========================================================================
        # SCHEDULE 3: Performance Check (Every hour)
        # ========================================================================
        # This monitors slow queries and table sizes
        
        self.performance_check_rule = events.Rule(
            self,
            "PerformanceCheckSchedule",
            description="Check query performance every hour",
            schedule=events.Schedule.rate(Duration.hours(1))
        )

        self.performance_check_rule.add_target(
            targets.LambdaFunction(
                self.maintenance_function,
                event=events.RuleTargetInput.from_object({
                    "task": "check_performance"
                })
            )
        )

        # ========================================================================
        # CloudWatch Alarms for Database Performance
        # ========================================================================
        
        # Alarm for slow materialized view refresh
        from aws_cdk import aws_cloudwatch as cloudwatch
        from aws_cdk import aws_sns as sns
        from aws_cdk import aws_cloudwatch_actions as cw_actions

        # Create SNS topic for alarms
        self.alarm_topic = sns.Topic(
            self,
            "DatabaseMaintenanceAlarms",
            display_name="Database Maintenance Alarms"
        )

        # Alarm: Materialized view refresh taking too long
        self.slow_refresh_alarm = cloudwatch.Alarm(
            self,
            "SlowMaterializedViewRefresh",
            metric=cloudwatch.Metric(
                namespace="AI-SW-PM/Database",
                metric_name="MaterializedViewRefreshDuration",
                statistic="Average",
                period=Duration.minutes(5)
            ),
            threshold=30,  # 30 seconds threshold (Requirement 18.7)
            evaluation_periods=2,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Materialized view refresh exceeds 30 seconds",
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )

        self.slow_refresh_alarm.add_alarm_action(
            cw_actions.SnsAction(self.alarm_topic)
        )

        # Alarm: Slow queries detected
        self.slow_query_alarm = cloudwatch.Alarm(
            self,
            "SlowQueriesDetected",
            metric=cloudwatch.Metric(
                namespace="AI-SW-PM/Database",
                metric_name="SlowQueryMeanTime",
                statistic="Average",
                period=Duration.minutes(15)
            ),
            threshold=2000,  # 2 seconds threshold (Requirement 23.1)
            evaluation_periods=2,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Database queries exceeding 2 second threshold",
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )

        self.slow_query_alarm.add_alarm_action(
            cw_actions.SnsAction(self.alarm_topic)
        )

        # Alarm: Lambda function errors
        self.maintenance_error_alarm = cloudwatch.Alarm(
            self,
            "MaintenanceFunctionErrors",
            metric=self.maintenance_function.metric_errors(
                period=Duration.minutes(5)
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            alarm_description="Database maintenance function errors",
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )

        self.maintenance_error_alarm.add_alarm_action(
            cw_actions.SnsAction(self.alarm_topic)
        )

        # ========================================================================
        # CloudWatch Dashboard for Database Performance
        # ========================================================================
        
        self.dashboard = cloudwatch.Dashboard(
            self,
            "DatabasePerformanceDashboard",
            dashboard_name="AI-SW-PM-Database-Performance"
        )

        # Add widgets to dashboard
        self.dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Materialized View Refresh Duration",
                left=[
                    cloudwatch.Metric(
                        namespace="AI-SW-PM/Database",
                        metric_name="MaterializedViewRefreshDuration",
                        statistic="Average",
                        period=Duration.minutes(5)
                    )
                ],
                left_y_axis=cloudwatch.YAxisProps(
                    label="Seconds",
                    min=0
                )
            ),
            cloudwatch.GraphWidget(
                title="Slow Query Mean Time",
                left=[
                    cloudwatch.Metric(
                        namespace="AI-SW-PM/Database",
                        metric_name="SlowQueryMeanTime",
                        statistic="Average",
                        period=Duration.minutes(15)
                    )
                ],
                left_y_axis=cloudwatch.YAxisProps(
                    label="Milliseconds",
                    min=0
                )
            )
        )

        self.dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Lambda Function Duration",
                left=[
                    self.maintenance_function.metric_duration(
                        period=Duration.minutes(5)
                    )
                ],
                left_y_axis=cloudwatch.YAxisProps(
                    label="Milliseconds",
                    min=0
                )
            ),
            cloudwatch.GraphWidget(
                title="Lambda Function Errors",
                left=[
                    self.maintenance_function.metric_errors(
                        period=Duration.minutes(5)
                    )
                ],
                left_y_axis=cloudwatch.YAxisProps(
                    label="Count",
                    min=0
                )
            )
        )

        # ========================================================================
        # Outputs
        # ========================================================================
        
        from aws_cdk import CfnOutput

        CfnOutput(
            self,
            "MaintenanceFunctionArn",
            value=self.maintenance_function.function_arn,
            description="Database maintenance Lambda function ARN"
        )

        CfnOutput(
            self,
            "AlarmTopicArn",
            value=self.alarm_topic.topic_arn,
            description="SNS topic for database maintenance alarms"
        )

        CfnOutput(
            self,
            "DashboardUrl",
            value=f"https://console.aws.amazon.com/cloudwatch/home?region={self.region}#dashboards:name={self.dashboard.dashboard_name}",
            description="CloudWatch dashboard URL"
        )
