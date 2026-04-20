"""Audit Logging Stack - CloudTrail, log retention, and log aggregation."""

from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    aws_cloudtrail as cloudtrail,
    aws_s3 as s3,
    aws_logs as logs,
    aws_kms as kms,
    aws_iam as iam,
    aws_sns as sns,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    CfnOutput,
)
from constructs import Construct


class AuditLoggingStack(Stack):
    """
    Stack for comprehensive audit logging with CloudTrail, log retention, and aggregation.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        alarm_topic: sns.Topic,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.alarm_topic = alarm_topic

        self._create_audit_kms_key()
        self._create_cloudtrail_bucket()
        self._create_cloudtrail()
        self._configure_log_retention()
        self._create_log_aggregation()
        self._create_security_monitoring()
        self._create_audit_export()

    def _create_audit_kms_key(self) -> None:
        """Create KMS key for encrypting audit logs."""

        self.audit_kms_key = kms.Key(
            self,
            "AuditLogsKMSKey",
            description="KMS key for encrypting audit logs",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # Allow CloudTrail to use the key — correct action is kms:Decrypt (not kms:DecryptDataKey)
        self.audit_kms_key.add_to_resource_policy(
            iam.PolicyStatement(
                sid="Allow CloudTrail to encrypt logs",
                principals=[iam.ServicePrincipal("cloudtrail.amazonaws.com")],
                actions=[
                    "kms:GenerateDataKey*",
                    "kms:Decrypt",
                ],
                resources=["*"],
                conditions={
                    "StringLike": {
                        "kms:EncryptionContext:aws:cloudtrail:arn": [
                            f"arn:aws:cloudtrail:*:{self.account}:trail/*"
                        ]
                    }
                }
            )
        )

        # Allow CloudWatch Logs to use the key
        self.audit_kms_key.add_to_resource_policy(
            iam.PolicyStatement(
                sid="Allow CloudWatch Logs to use the key",
                principals=[
                    iam.ServicePrincipal(f"logs.{self.region}.amazonaws.com")
                ],
                actions=[
                    "kms:Encrypt",
                    "kms:Decrypt",
                    "kms:ReEncrypt*",
                    "kms:GenerateDataKey*",
                    "kms:CreateGrant",
                    "kms:DescribeKey",
                ],
                resources=["*"],
                conditions={
                    "ArnLike": {
                        "kms:EncryptionContext:aws:logs:arn": [
                            f"arn:aws:logs:{self.region}:{self.account}:log-group:*"
                        ]
                    }
                }
            )
        )

    def _create_cloudtrail_bucket(self) -> None:
        """Create S3 bucket for CloudTrail logs with security best practices."""

        # Bucket name must be ≤63 chars; account(12)+region(~9) + prefix = safe
        self.cloudtrail_bucket = s3.Bucket(
            self,
            "CloudTrailBucket",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.audit_kms_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="TransitionToIA",
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(90)
                        ),
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(180)
                        ),
                    ]
                ),
                s3.LifecycleRule(
                    id="RetainAuditLogs",
                    expiration=Duration.days(365),
                    abort_incomplete_multipart_upload_after=Duration.days(7)
                ),
            ],
            removal_policy=RemovalPolicy.RETAIN,
            enforce_ssl=True,
            # object_lock_enabled removed: requires bucket to be created with object lock
            # from the very first deployment and is incompatible with standard CDK versioning setup
        )

        # Allow CloudTrail to check bucket ACL
        self.cloudtrail_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AWSCloudTrailAclCheck",
                principals=[iam.ServicePrincipal("cloudtrail.amazonaws.com")],
                actions=["s3:GetBucketAcl"],
                resources=[self.cloudtrail_bucket.bucket_arn]
            )
        )

        # Allow CloudTrail to write logs
        self.cloudtrail_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AWSCloudTrailWrite",
                principals=[iam.ServicePrincipal("cloudtrail.amazonaws.com")],
                actions=["s3:PutObject"],
                resources=[f"{self.cloudtrail_bucket.bucket_arn}/AWSLogs/{self.account}/*"],
                conditions={
                    "StringEquals": {
                        "s3:x-amz-acl": "bucket-owner-full-control"
                    }
                }
            )
        )

    def _create_cloudtrail(self) -> None:
        """Enable CloudTrail for all API calls."""

        self.cloudtrail_log_group = logs.LogGroup(
            self,
            "CloudTrailLogGroup",
            log_group_name="/aws/cloudtrail/ai-sw-pm",
            retention=logs.RetentionDays.ONE_YEAR,
            encryption_key=self.audit_kms_key,
            removal_policy=RemovalPolicy.RETAIN
        )

        # CloudTrail requires an explicit IAM role to write to CloudWatch Logs
        cloudtrail_cw_role = iam.Role(
            self,
            "CloudTrailCWRole",
            assumed_by=iam.ServicePrincipal("cloudtrail.amazonaws.com"),
            description="Role for CloudTrail to write to CloudWatch Logs",
            inline_policies={
                "CloudWatchLogsPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "logs:CreateLogStream",
                                "logs:PutLogEvents",
                            ],
                            resources=[
                                f"{self.cloudtrail_log_group.log_group_arn}:*"
                            ]
                        )
                    ]
                )
            }
        )

        self.trail = cloudtrail.Trail(
            self,
            "AuditTrail",
            trail_name="ai-sw-pm-audit-trail",
            bucket=self.cloudtrail_bucket,
            enable_file_validation=True,
            include_global_service_events=True,
            is_multi_region_trail=True,
            management_events=cloudtrail.ReadWriteType.ALL,
            send_to_cloud_watch_logs=True,
            cloud_watch_logs_retention=logs.RetentionDays.ONE_YEAR,
            cloud_watch_log_group=self.cloudtrail_log_group,
            encryption_key=self.audit_kms_key,
        )

        # Grant the role permission to write to the log group
        self.cloudtrail_log_group.grant_write(cloudtrail_cw_role)

        self.trail.log_all_s3_data_events()
        self.trail.log_all_lambda_data_events()

    def _configure_log_retention(self) -> None:
        """Configure log retention policies for all log groups."""

        self.audit_log_groups = {}

        self.audit_log_groups["audit-logging"] = logs.LogGroup(
            self,
            "AuditLoggingLogGroup",
            log_group_name="/aws/lambda/audit-logging",
            retention=logs.RetentionDays.ONE_YEAR,
            encryption_key=self.audit_kms_key,
            removal_policy=RemovalPolicy.RETAIN
        )

        self.audit_log_groups["security-monitoring"] = logs.LogGroup(
            self,
            "SecurityMonitoringLogGroup",
            log_group_name="/aws/lambda/security-monitoring",
            retention=logs.RetentionDays.ONE_YEAR,
            encryption_key=self.audit_kms_key,
            removal_policy=RemovalPolicy.RETAIN
        )

    def _create_log_aggregation(self) -> None:
        """Create log aggregation and analysis infrastructure."""

        self.aggregated_audit_log_group = logs.LogGroup(
            self,
            "AggregatedAuditLogGroup",
            log_group_name="/aws/audit/aggregated",
            retention=logs.RetentionDays.ONE_YEAR,
            encryption_key=self.audit_kms_key,
            removal_policy=RemovalPolicy.RETAIN
        )

        self._create_audit_metric_filters()

    def _create_audit_metric_filters(self) -> None:
        """Create metric filters for audit log analysis."""

        logs.MetricFilter(
            self,
            "AuthenticationFailureFilter",
            log_group=self.cloudtrail_log_group,
            filter_pattern=logs.FilterPattern.all(
                logs.FilterPattern.string_value("$.eventName", "=", "ConsoleLogin"),
                logs.FilterPattern.string_value("$.errorCode", "=", "Failed authentication")
            ),
            metric_namespace="AISWProgramManager/Audit",
            metric_name="AuthenticationFailures",
            metric_value="1",
            default_value=0
        )

        logs.MetricFilter(
            self,
            "UnauthorizedAccessFilter",
            log_group=self.cloudtrail_log_group,
            filter_pattern=logs.FilterPattern.any(
                logs.FilterPattern.string_value("$.errorCode", "=", "AccessDenied"),
                logs.FilterPattern.string_value("$.errorCode", "=", "UnauthorizedOperation")
            ),
            metric_namespace="AISWProgramManager/Audit",
            metric_name="UnauthorizedAccessAttempts",
            metric_value="1",
            default_value=0
        )

        logs.MetricFilter(
            self,
            "DataModificationFilter",
            log_group=self.aggregated_audit_log_group,
            filter_pattern=logs.FilterPattern.string_value(
                "$.event_type", "=", "data_modification"
            ),
            metric_namespace="AISWProgramManager/Audit",
            metric_name="DataModifications",
            metric_value="1",
            default_value=0
        )

        logs.MetricFilter(
            self,
            "AdminActionFilter",
            log_group=self.aggregated_audit_log_group,
            filter_pattern=logs.FilterPattern.string_value(
                "$.event_type", "=", "administrative_action"
            ),
            metric_namespace="AISWProgramManager/Audit",
            metric_name="AdministrativeActions",
            metric_value="1",
            default_value=0
        )

    def _create_security_monitoring(self) -> None:
        """Create security monitoring and alerting for suspicious activity."""

        auth_failure_alarm = cloudwatch.Alarm(
            self,
            "AuthenticationFailureAlarm",
            alarm_name="ai-sw-pm-auth-failures",
            alarm_description="Alert when authentication failures exceed threshold",
            metric=cloudwatch.Metric(
                namespace="AISWProgramManager/Audit",
                metric_name="AuthenticationFailures",
                statistic="Sum",
                period=Duration.minutes(5)
            ),
            threshold=10,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        auth_failure_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))

        unauthorized_access_alarm = cloudwatch.Alarm(
            self,
            "UnauthorizedAccessAlarm",
            alarm_name="ai-sw-pm-unauthorized-access",
            alarm_description="Alert when unauthorized access attempts exceed threshold",
            metric=cloudwatch.Metric(
                namespace="AISWProgramManager/Audit",
                metric_name="UnauthorizedAccessAttempts",
                statistic="Sum",
                period=Duration.minutes(5)
            ),
            threshold=5,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        unauthorized_access_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))

        data_mod_alarm = cloudwatch.Alarm(
            self,
            "HighVolumeDataModificationAlarm",
            alarm_name="ai-sw-pm-high-data-modifications",
            alarm_description="Alert when data modifications exceed normal threshold",
            metric=cloudwatch.Metric(
                namespace="AISWProgramManager/Audit",
                metric_name="DataModifications",
                statistic="Sum",
                period=Duration.minutes(5)
            ),
            threshold=1000,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        data_mod_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))

    def _create_audit_export(self) -> None:
        """Create infrastructure for audit log export for compliance reporting."""

        self.audit_export_bucket = s3.Bucket(
            self,
            "AuditExportBucket",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.audit_kms_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="RetainExports",
                    expiration=Duration.days(2555),  # 7 years for compliance
                )
            ],
            removal_policy=RemovalPolicy.RETAIN,
            enforce_ssl=True,
        )

        CfnOutput(
            self,
            "AuditExportBucketName",
            value=self.audit_export_bucket.bucket_name,
            description="S3 bucket for audit log exports",
            export_name="AuditExportBucketName"
        )

        CfnOutput(
            self,
            "CloudTrailLogGroupName",
            value=self.cloudtrail_log_group.log_group_name,
            description="CloudWatch log group for CloudTrail logs",
            export_name="CloudTrailLogGroupName"
        )

        CfnOutput(
            self,
            "AggregatedAuditLogGroupName",
            value=self.aggregated_audit_log_group.log_group_name,
            description="CloudWatch log group for aggregated audit logs",
            export_name="AggregatedAuditLogGroupName"
        )
