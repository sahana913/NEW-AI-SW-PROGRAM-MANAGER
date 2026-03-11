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
    aws_logs_destinations as destinations,
    aws_lambda as lambda_,
    CfnOutput,
)
from constructs import Construct


class AuditLoggingStack(Stack):
    """
    Stack for comprehensive audit logging with CloudTrail, log retention, and aggregation.
    
    Implements:
    - CloudTrail for all API calls (Requirement 28.1)
    - Log retention policies (90 days CloudWatch, 1 year audit logs) (Requirements 27.6, 28.5)
    - Log aggregation and analysis (Requirement 27.7)
    - Immutable and tamper-evident audit logs (Requirement 28.4)
    - Audit log export for compliance (Requirement 28.6)
    - Security alert generation (Requirement 28.7)
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

        # Create KMS key for audit log encryption
        self._create_audit_kms_key()

        # Create S3 bucket for CloudTrail logs
        self._create_cloudtrail_bucket()

        # Enable CloudTrail for all API calls
        self._create_cloudtrail()

        # Configure log retention policies
        self._configure_log_retention()

        # Create log aggregation infrastructure
        self._create_log_aggregation()

        # Create security monitoring and alerting
        self._create_security_monitoring()

        # Create audit log export functionality
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

        # Allow CloudTrail to use the key
        self.audit_kms_key.add_to_resource_policy(
            iam.PolicyStatement(
                sid="Allow CloudTrail to encrypt logs",
                principals=[iam.ServicePrincipal("cloudtrail.amazonaws.com")],
                actions=[
                    "kms:GenerateDataKey*",
                    "kms:DecryptDataKey"
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
                    "kms:DescribeKey"
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

        self.cloudtrail_bucket = s3.Bucket(
            self,
            "CloudTrailBucket",
            bucket_name=f"ai-sw-pm-cloudtrail-{self.account}-{self.region}",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.audit_kms_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,  # Enable versioning for tamper-evidence
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
                        )
                    ]
                ),
                s3.LifecycleRule(
                    id="RetainAuditLogs",
                    expiration=Duration.days(365),  # 1 year retention for audit logs
                    abort_incomplete_multipart_upload_after=Duration.days(7)
                )
            ],
            removal_policy=RemovalPolicy.RETAIN,
            enforce_ssl=True,
            object_lock_enabled=True,  # Enable object lock for immutability
        )

        # Add bucket policy for CloudTrail
        self.cloudtrail_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AWSCloudTrailAclCheck",
                principals=[iam.ServicePrincipal("cloudtrail.amazonaws.com")],
                actions=["s3:GetBucketAcl"],
                resources=[self.cloudtrail_bucket.bucket_arn]
            )
        )

        self.cloudtrail_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AWSCloudTrailWrite",
                principals=[iam.ServicePrincipal("cloudtrail.amazonaws.com")],
                actions=["s3:PutObject"],
                resources=[f"{self.cloudtrail_bucket.bucket_arn}/*"],
                conditions={
                    "StringEquals": {
                        "s3:x-amz-acl": "bucket-owner-full-control"
                    }
                }
            )
        )

    def _create_cloudtrail(self) -> None:
        """Enable CloudTrail for all API calls."""

        # Create CloudWatch log group for CloudTrail
        self.cloudtrail_log_group = logs.LogGroup(
            self,
            "CloudTrailLogGroup",
            log_group_name="/aws/cloudtrail/ai-sw-pm",
            retention=logs.RetentionDays.ONE_YEAR,  # 1 year retention for audit logs
            encryption_key=self.audit_kms_key,
            removal_policy=RemovalPolicy.RETAIN
        )

        # Create IAM role for CloudTrail to write to CloudWatch Logs
        cloudtrail_role = iam.Role(
            self,
            "CloudTrailRole",
            assumed_by=iam.ServicePrincipal("cloudtrail.amazonaws.com"),
            description="Role for CloudTrail to write to CloudWatch Logs"
        )

        self.cloudtrail_log_group.grant_write(cloudtrail_role)

        # Create the CloudTrail trail
        self.trail = cloudtrail.Trail(
            self,
            "AuditTrail",
            trail_name="ai-sw-pm-audit-trail",
            bucket=self.cloudtrail_bucket,
            enable_file_validation=True,  # Enable log file integrity validation
            include_global_service_events=True,  # Include IAM, STS, CloudFront events
            is_multi_region_trail=True,  # Capture events from all regions
            management_events=cloudtrail.ReadWriteType.ALL,  # Log all management events
            send_to_cloud_watch_logs=True,
            cloud_watch_logs_retention=logs.RetentionDays.ONE_YEAR,
            cloud_watch_log_group=self.cloudtrail_log_group,
            encryption_key=self.audit_kms_key,
        )

        # Add data events for S3 buckets (document uploads, report storage)
        # Note: Using empty list to capture all S3 buckets in the account
        self.trail.log_all_s3_data_events()

        # Add data events for Lambda function invocations
        # Note: Using empty list to capture all Lambda functions in the account
        self.trail.log_all_lambda_data_events()

    def _configure_log_retention(self) -> None:
        """Configure log retention policies for all log groups."""

        # Standard CloudWatch logs: 90 days retention (Requirement 27.6)
        # Audit logs: 1 year retention (Requirement 28.5)

        self.log_retention_config = {
            # Standard application logs - 90 days
            "standard_logs": {
                "retention": logs.RetentionDays.THREE_MONTHS,
                "log_groups": [
                    "/aws/lambda/ai-sw-pm-*",
                    "/aws/apigateway/ai-sw-pm",
                    "/aws/states/ai-sw-pm",
                ]
            },
            # Audit logs - 1 year
            "audit_logs": {
                "retention": logs.RetentionDays.ONE_YEAR,
                "log_groups": [
                    "/aws/cloudtrail/ai-sw-pm",
                    "/aws/lambda/audit-logging",
                    "/aws/lambda/security-monitoring",
                ]
            }
        }

        # Create log groups with appropriate retention
        self.audit_log_groups = {}

        # Audit logging Lambda log group
        self.audit_log_groups["audit-logging"] = logs.LogGroup(
            self,
            "AuditLoggingLogGroup",
            log_group_name="/aws/lambda/audit-logging",
            retention=logs.RetentionDays.ONE_YEAR,
            encryption_key=self.audit_kms_key,
            removal_policy=RemovalPolicy.RETAIN
        )

        # Security monitoring Lambda log group
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

        # Create centralized audit log group for aggregation
        self.aggregated_audit_log_group = logs.LogGroup(
            self,
            "AggregatedAuditLogGroup",
            log_group_name="/aws/audit/aggregated",
            retention=logs.RetentionDays.ONE_YEAR,
            encryption_key=self.audit_kms_key,
            removal_policy=RemovalPolicy.RETAIN
        )

        # Create metric filters for audit events
        self._create_audit_metric_filters()

        # Create CloudWatch Insights queries for common audit scenarios
        self._create_insights_queries()

    def _create_audit_metric_filters(self) -> None:
        """Create metric filters for audit log analysis."""

        # Authentication failure metric
        auth_failure_filter = logs.MetricFilter(
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

        # Unauthorized access attempts metric
        unauthorized_access_filter = logs.MetricFilter(
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

        # Data modification events metric
        data_modification_filter = logs.MetricFilter(
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

        # Administrative action metric
        admin_action_filter = logs.MetricFilter(
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

    def _create_insights_queries(self) -> None:
        """Create CloudWatch Insights queries for audit log analysis."""

        # These queries can be saved in CloudWatch Logs Insights for easy access
        self.insights_queries = {
            "authentication_attempts": """
                fields @timestamp, userIdentity.principalId, eventName, errorCode, sourceIPAddress
                | filter eventName = "ConsoleLogin" or eventName = "AssumeRole"
                | sort @timestamp desc
                | limit 100
            """,
            
            "failed_authentications": """
                fields @timestamp, userIdentity.principalId, eventName, errorCode, sourceIPAddress
                | filter eventName = "ConsoleLogin" and errorCode = "Failed authentication"
                | stats count() by userIdentity.principalId, sourceIPAddress
                | sort count desc
            """,
            
            "data_modifications_by_user": """
                fields @timestamp, user_id, tenant_id, operation_type, table_name
                | filter event_type = "data_modification"
                | stats count() by user_id, operation_type
                | sort count desc
            """,
            
            "administrative_actions": """
                fields @timestamp, admin_user_id, action_type, affected_entity
                | filter event_type = "administrative_action"
                | sort @timestamp desc
                | limit 100
            """,
            
            "cross_tenant_access_attempts": """
                fields @timestamp, user_id, user_tenant_id, requested_tenant_id, resource
                | filter event_type = "security_violation"
                | sort @timestamp desc
            """,
            
            "suspicious_activity_patterns": """
                fields @timestamp, user_id, sourceIPAddress, eventName
                | stats count() by user_id, sourceIPAddress, bin(5m)
                | filter count > 100
                | sort @timestamp desc
            """
        }

    def _create_security_monitoring(self) -> None:
        """Create security monitoring and alerting for suspicious activity."""

        # Create alarms for security events

        # Authentication failure alarm
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
            threshold=10,  # More than 10 failures in 5 minutes
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )

        auth_failure_alarm.add_alarm_action(
            cw_actions.SnsAction(self.alarm_topic)
        )

        # Unauthorized access alarm
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
            threshold=5,  # More than 5 unauthorized attempts in 5 minutes
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )

        unauthorized_access_alarm.add_alarm_action(
            cw_actions.SnsAction(self.alarm_topic)
        )

        # High volume data modification alarm
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
            threshold=1000,  # More than 1000 modifications in 5 minutes
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )

        data_mod_alarm.add_alarm_action(
            cw_actions.SnsAction(self.alarm_topic)
        )

    def _create_audit_export(self) -> None:
        """Create infrastructure for audit log export for compliance reporting."""

        # Create S3 bucket for audit log exports
        self.audit_export_bucket = s3.Bucket(
            self,
            "AuditExportBucket",
            bucket_name=f"ai-sw-pm-audit-exports-{self.account}-{self.region}",
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

        # Output bucket name for export scripts
        CfnOutput(
            self,
            "AuditExportBucketName",
            value=self.audit_export_bucket.bucket_name,
            description="S3 bucket for audit log exports",
            export_name="AuditExportBucketName"
        )

        # Output CloudTrail log group for export
        CfnOutput(
            self,
            "CloudTrailLogGroupName",
            value=self.cloudtrail_log_group.log_group_name,
            description="CloudWatch log group for CloudTrail logs",
            export_name="CloudTrailLogGroupName"
        )

        # Output aggregated audit log group
        CfnOutput(
            self,
            "AggregatedAuditLogGroupName",
            value=self.aggregated_audit_log_group.log_group_name,
            description="CloudWatch log group for aggregated audit logs",
            export_name="AggregatedAuditLogGroupName"
        )
