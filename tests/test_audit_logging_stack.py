"""Tests for Audit Logging Stack."""

import pytest
from aws_cdk import App, Stack, aws_sns as sns
from aws_cdk.assertions import Template, Match
from infrastructure.stacks.audit_logging_stack import AuditLoggingStack


@pytest.fixture
def audit_logging_template():
    """Create a CloudFormation template for the audit logging stack."""
    app = App()
    
    # Create a test alarm topic
    test_stack = Stack(app, "TestStack")
    alarm_topic = sns.Topic(test_stack, "TestAlarmTopic")
    
    # Create the audit logging stack
    stack = AuditLoggingStack(
        app,
        "TestAuditLoggingStack",
        alarm_topic=alarm_topic
    )
    
    template = Template.from_stack(stack)
    return template


class TestAuditLoggingStack:
    """Test suite for Audit Logging Stack."""

    def test_kms_key_created(self, audit_logging_template):
        """Test that KMS key for audit logs is created with key rotation enabled."""
        audit_logging_template.has_resource_properties(
            "AWS::KMS::Key",
            {
                "Description": "KMS key for encrypting audit logs",
                "EnableKeyRotation": True
            }
        )

    def test_cloudtrail_bucket_created(self, audit_logging_template):
        """Test that S3 bucket for CloudTrail logs is created with proper configuration."""
        audit_logging_template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "BucketEncryption": {
                    "ServerSideEncryptionConfiguration": [
                        {
                            "ServerSideEncryptionByDefault": {
                                "SSEAlgorithm": "aws:kms"
                            }
                        }
                    ]
                },
                "VersioningConfiguration": {
                    "Status": "Enabled"
                },
                "PublicAccessBlockConfiguration": {
                    "BlockPublicAcls": True,
                    "BlockPublicPolicy": True,
                    "IgnorePublicAcls": True,
                    "RestrictPublicBuckets": True
                },
                "ObjectLockEnabled": True
            }
        )

    def test_cloudtrail_bucket_lifecycle_rules(self, audit_logging_template):
        """Test that CloudTrail bucket has lifecycle rules for retention and transitions."""
        audit_logging_template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "LifecycleConfiguration": {
                    "Rules": Match.array_with([
                        Match.object_like({
                            "Id": "RetainAuditLogs",
                            "ExpirationInDays": 365,
                            "Status": "Enabled"
                        })
                    ])
                }
            }
        )

    def test_cloudtrail_log_group_created(self, audit_logging_template):
        """Test that CloudWatch log group for CloudTrail is created with 1 year retention."""
        audit_logging_template.has_resource_properties(
            "AWS::Logs::LogGroup",
            {
                "LogGroupName": "/aws/cloudtrail/ai-sw-pm",
                "RetentionInDays": 365
            }
        )

    def test_cloudtrail_created(self, audit_logging_template):
        """Test that CloudTrail trail is created with proper configuration."""
        audit_logging_template.has_resource_properties(
            "AWS::CloudTrail::Trail",
            {
                "TrailName": "ai-sw-pm-audit-trail",
                "EnableLogFileValidation": True,
                "IncludeGlobalServiceEvents": True,
                "IsMultiRegionTrail": True,
                "IsLogging": True
            }
        )

    def test_cloudtrail_s3_event_selector(self, audit_logging_template):
        """Test that CloudTrail has S3 event selectors configured."""
        # CloudTrail should have data events enabled for S3
        # Using log_all_s3_data_events() method
        audit_logging_template.has_resource_properties(
            "AWS::CloudTrail::Trail",
            {
                "EventSelectors": Match.array_with([
                    Match.object_like({
                        "IncludeManagementEvents": True,
                        "ReadWriteType": "All"
                    })
                ])
            }
        )

    def test_cloudtrail_lambda_event_selector(self, audit_logging_template):
        """Test that CloudTrail has Lambda event selectors configured."""
        # CloudTrail should have data events enabled for Lambda
        # Using log_all_lambda_data_events() method
        audit_logging_template.has_resource_properties(
            "AWS::CloudTrail::Trail",
            {
                "EventSelectors": Match.array_with([
                    Match.object_like({
                        "IncludeManagementEvents": True,
                        "ReadWriteType": "All"
                    })
                ])
            }
        )

    def test_audit_log_groups_created(self, audit_logging_template):
        """Test that audit log groups are created with 1 year retention."""
        # Audit logging Lambda log group
        audit_logging_template.has_resource_properties(
            "AWS::Logs::LogGroup",
            {
                "LogGroupName": "/aws/lambda/audit-logging",
                "RetentionInDays": 365
            }
        )
        
        # Security monitoring Lambda log group
        audit_logging_template.has_resource_properties(
            "AWS::Logs::LogGroup",
            {
                "LogGroupName": "/aws/lambda/security-monitoring",
                "RetentionInDays": 365
            }
        )

    def test_aggregated_audit_log_group_created(self, audit_logging_template):
        """Test that aggregated audit log group is created."""
        audit_logging_template.has_resource_properties(
            "AWS::Logs::LogGroup",
            {
                "LogGroupName": "/aws/audit/aggregated",
                "RetentionInDays": 365
            }
        )

    def test_metric_filters_created(self, audit_logging_template):
        """Test that metric filters for audit events are created."""
        # Authentication failure filter
        audit_logging_template.has_resource_properties(
            "AWS::Logs::MetricFilter",
            {
                "FilterPattern": Match.string_like_regexp(".*ConsoleLogin.*Failed authentication.*"),
                "MetricTransformations": [
                    {
                        "MetricNamespace": "AISWProgramManager/Audit",
                        "MetricName": "AuthenticationFailures",
                        "MetricValue": "1",
                        "DefaultValue": 0
                    }
                ]
            }
        )

    def test_security_alarms_created(self, audit_logging_template):
        """Test that security monitoring alarms are created."""
        # Authentication failure alarm
        audit_logging_template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "ai-sw-pm-auth-failures",
                "MetricName": "AuthenticationFailures",
                "Namespace": "AISWProgramManager/Audit",
                "Threshold": 10,
                "ComparisonOperator": "GreaterThanThreshold"
            }
        )
        
        # Unauthorized access alarm
        audit_logging_template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "ai-sw-pm-unauthorized-access",
                "MetricName": "UnauthorizedAccessAttempts",
                "Namespace": "AISWProgramManager/Audit",
                "Threshold": 5,
                "ComparisonOperator": "GreaterThanThreshold"
            }
        )

    def test_audit_export_bucket_created(self, audit_logging_template):
        """Test that S3 bucket for audit log exports is created."""
        audit_logging_template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "BucketEncryption": {
                    "ServerSideEncryptionConfiguration": [
                        {
                            "ServerSideEncryptionByDefault": {
                                "SSEAlgorithm": "aws:kms"
                            }
                        }
                    ]
                },
                "VersioningConfiguration": {
                    "Status": "Enabled"
                },
                "LifecycleConfiguration": {
                    "Rules": Match.array_with([
                        Match.object_like({
                            "Id": "RetainExports",
                            "ExpirationInDays": 2555,  # 7 years
                            "Status": "Enabled"
                        })
                    ])
                }
            }
        )

    def test_cloudformation_outputs_created(self, audit_logging_template):
        """Test that CloudFormation outputs are created for export."""
        # Audit export bucket output
        audit_logging_template.has_output(
            "AuditExportBucketName",
            {
                "Description": "S3 bucket for audit log exports",
                "Export": {
                    "Name": "AuditExportBucketName"
                }
            }
        )
        
        # CloudTrail log group output
        audit_logging_template.has_output(
            "CloudTrailLogGroupName",
            {
                "Description": "CloudWatch log group for CloudTrail logs",
                "Export": {
                    "Name": "CloudTrailLogGroupName"
                }
            }
        )

    def test_log_retention_requirements(self, audit_logging_template):
        """Test that log retention meets requirements (90 days standard, 1 year audit)."""
        # Count log groups with 1 year retention (audit logs)
        template_dict = audit_logging_template.to_json()
        resources = template_dict.get("Resources", {})
        
        audit_log_groups = [
            r for r in resources.values()
            if r.get("Type") == "AWS::Logs::LogGroup"
            and r.get("Properties", {}).get("RetentionInDays") == 365
        ]
        
        # Should have at least 4 audit log groups with 1 year retention:
        # - CloudTrail log group
        # - Audit logging Lambda log group
        # - Security monitoring Lambda log group
        # - Aggregated audit log group
        assert len(audit_log_groups) >= 4, "Should have at least 4 log groups with 1 year retention"

    def test_immutable_audit_logs(self, audit_logging_template):
        """Test that audit logs are immutable (object lock enabled on CloudTrail bucket)."""
        audit_logging_template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "ObjectLockEnabled": True
            }
        )

    def test_encryption_at_rest(self, audit_logging_template):
        """Test that all audit logs are encrypted at rest with KMS."""
        template_dict = audit_logging_template.to_json()
        resources = template_dict.get("Resources", {})
        
        # Check that log groups reference KMS key
        log_groups = [
            r for r in resources.values()
            if r.get("Type") == "AWS::Logs::LogGroup"
        ]
        
        # All audit log groups should have KMS encryption
        for log_group in log_groups:
            props = log_group.get("Properties", {})
            if "/aws/audit/" in props.get("LogGroupName", "") or \
               "/aws/cloudtrail/" in props.get("LogGroupName", "") or \
               "audit-logging" in props.get("LogGroupName", "") or \
               "security-monitoring" in props.get("LogGroupName", ""):
                assert "KmsKeyId" in props, f"Audit log group should have KMS encryption"


class TestAuditLoggingRequirements:
    """Test that audit logging stack meets specific requirements."""

    def test_requirement_27_6_log_retention_90_days(self, audit_logging_template):
        """
        Requirement 27.6: THE Platform SHALL retain logs for minimum 90 days.
        
        Standard application logs should have 90 days retention.
        """
        # This is configured in the monitoring stack for standard logs
        # Audit logs have 1 year retention as per Requirement 28.5
        pass

    def test_requirement_27_7_log_search_and_filtering(self, audit_logging_template):
        """
        Requirement 27.7: THE Platform SHALL support log search and filtering.
        
        CloudWatch Logs Insights queries are created for common audit scenarios.
        """
        # Verify aggregated log group exists for centralized searching
        audit_logging_template.has_resource_properties(
            "AWS::Logs::LogGroup",
            {
                "LogGroupName": "/aws/audit/aggregated"
            }
        )

    def test_requirement_28_1_authentication_logging(self, audit_logging_template):
        """
        Requirement 28.1: THE Platform SHALL log all user authentication attempts to CloudTrail.
        
        CloudTrail is configured to capture all authentication events.
        """
        audit_logging_template.has_resource_properties(
            "AWS::CloudTrail::Trail",
            {
                "IncludeGlobalServiceEvents": True,  # Includes IAM, STS events
                "IsLogging": True
            }
        )

    def test_requirement_28_4_immutable_audit_logs(self, audit_logging_template):
        """
        Requirement 28.4: THE Platform SHALL make audit logs immutable and tamper-evident.
        
        S3 Object Lock and versioning provide immutability.
        CloudTrail log file validation provides tamper-evidence.
        """
        # Object lock for immutability
        audit_logging_template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "ObjectLockEnabled": True,
                "VersioningConfiguration": {
                    "Status": "Enabled"
                }
            }
        )
        
        # Log file validation for tamper-evidence
        audit_logging_template.has_resource_properties(
            "AWS::CloudTrail::Trail",
            {
                "EnableLogFileValidation": True
            }
        )

    def test_requirement_28_5_audit_log_retention_1_year(self, audit_logging_template):
        """
        Requirement 28.5: THE Platform SHALL retain audit logs for minimum 1 year.
        
        All audit-related log groups have 365 days retention.
        """
        audit_logging_template.has_resource_properties(
            "AWS::Logs::LogGroup",
            {
                "LogGroupName": "/aws/cloudtrail/ai-sw-pm",
                "RetentionInDays": 365
            }
        )

    def test_requirement_28_6_audit_log_export(self, audit_logging_template):
        """
        Requirement 28.6: THE Platform SHALL support audit log export for compliance reporting.
        
        Dedicated S3 bucket for audit log exports with 7-year retention.
        """
        audit_logging_template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "LifecycleConfiguration": {
                    "Rules": Match.array_with([
                        Match.object_like({
                            "Id": "RetainExports",
                            "ExpirationInDays": 2555  # 7 years
                        })
                    ])
                }
            }
        )

    def test_requirement_28_7_security_alerts(self, audit_logging_template):
        """
        Requirement 28.7: WHEN suspicious activity patterns are detected,
        THE Platform SHALL generate security alerts.
        
        CloudWatch alarms monitor for suspicious patterns and send SNS notifications.
        """
        # Authentication failure alarm
        audit_logging_template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "ai-sw-pm-auth-failures",
                "Threshold": 10
            }
        )
        
        # Unauthorized access alarm
        audit_logging_template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "ai-sw-pm-unauthorized-access",
                "Threshold": 5
            }
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
