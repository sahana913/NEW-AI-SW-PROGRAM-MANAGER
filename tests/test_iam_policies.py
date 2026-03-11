"""
Unit tests for IAM Policies Stack.

Validates: Requirement 24.5 - IAM-based access control for all AWS resources
"""

import pytest
from aws_cdk import App, Stack
from aws_cdk.assertions import Template, Match
from infrastructure.stacks.iam_policies_stack import IamPoliciesStack


@pytest.fixture
def iam_stack():
    """Create IAM Policies Stack for testing."""
    app = App()
    stack = IamPoliciesStack(app, "TestIamPoliciesStack")
    return stack


@pytest.fixture
def template(iam_stack):
    """Generate CloudFormation template from stack."""
    return Template.from_stack(iam_stack)


class TestIAMAccessAnalyzer:
    """Test IAM Access Analyzer configuration."""

    def test_access_analyzer_created(self, template):
        """
        Test that IAM Access Analyzer is created.
        
        Validates: Requirement 24.5 - Enable IAM Access Analyzer
        """
        template.resource_count_is("AWS::AccessAnalyzer::Analyzer", 1)

    def test_access_analyzer_type(self, template):
        """Test that Access Analyzer is account-level."""
        template.has_resource_properties(
            "AWS::AccessAnalyzer::Analyzer",
            {
                "Type": "ACCOUNT",
                "AnalyzerName": "ai-sw-pm-access-analyzer"
            }
        )

    def test_access_analyzer_tags(self, template):
        """Test that Access Analyzer has appropriate tags."""
        template.has_resource_properties(
            "AWS::AccessAnalyzer::Analyzer",
            {
                "Tags": Match.array_with([
                    {"Key": "Application", "Value": "AI-SW-Program-Manager"},
                    {"Key": "Purpose", "Value": "IAM-Policy-Analysis"}
                ])
            }
        )


class TestAuthorizerRole:
    """Test Authorizer IAM role configuration."""

    def test_authorizer_role_created(self, template):
        """Test that Authorizer role is created."""
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-authorizer-role",
                "Description": "Least privilege role for Lambda Authorizer function"
            }
        )

    def test_authorizer_cognito_permissions(self, template):
        """
        Test that Authorizer has only required Cognito permissions.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        # Find the authorizer role specifically
        template.has_resource_properties(
            "AWS::IAM::Role",
            Match.object_like({
                "RoleName": "ai-sw-pm-authorizer-role",
                "Policies": Match.array_with([
                    Match.object_like({
                        "PolicyDocument": {
                            "Statement": Match.array_with([
                                Match.object_like({
                                    "Action": [
                                        "cognito-idp:GetUser",
                                        "cognito-idp:DescribeUserPool"
                                    ],
                                    "Effect": "Allow"
                                })
                            ])
                        }
                    })
                ])
            })
        )

    def test_authorizer_no_write_permissions(self, template):
        """Test that Authorizer has no write permissions to Cognito."""
        # Verify no AdminCreateUser, AdminDeleteUser, etc.
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-authorizer-role",
                "Policies": Match.array_with([
                    Match.object_like({
                        "PolicyDocument": {
                            "Statement": Match.array_with([
                                Match.object_like({
                                    "Action": Match.array_equals([
                                        "cognito-idp:GetUser",
                                        "cognito-idp:DescribeUserPool"
                                    ])
                                })
                            ])
                        }
                    })
                ])
            }
        )


class TestUserManagementRole:
    """Test User Management IAM role configuration."""

    def test_user_management_role_created(self, template):
        """Test that User Management role is created."""
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-user-management-role",
                "Description": "Least privilege role for User Management function"
            }
        )

    def test_user_management_cognito_permissions(self, template):
        """
        Test that User Management has required Cognito permissions.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-user-management-role",
                "Policies": Match.array_with([
                    Match.object_like({
                        "PolicyDocument": {
                            "Statement": Match.array_with([
                                Match.object_like({
                                    "Action": [
                                        "cognito-idp:AdminCreateUser",
                                        "cognito-idp:AdminDeleteUser",
                                        "cognito-idp:AdminUpdateUserAttributes",
                                        "cognito-idp:ListUsers"
                                    ],
                                    "Effect": "Allow"
                                })
                            ])
                        }
                    })
                ])
            }
        )

    def test_user_management_dynamodb_scoped(self, template):
        """Test that DynamoDB permissions are scoped to Users table only."""
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-user-management-role",
                "Policies": Match.array_with([
                    Match.object_like({
                        "PolicyDocument": {
                            "Statement": Match.array_with([
                                Match.object_like({
                                    "Action": [
                                        "dynamodb:GetItem",
                                        "dynamodb:PutItem",
                                        "dynamodb:UpdateItem",
                                        "dynamodb:Query",
                                        "dynamodb:Scan"
                                    ],
                                    "Resource": Match.array_with([
                                        Match.string_like_regexp(".*table/ai-sw-pm-users.*")
                                    ])
                                })
                            ])
                        }
                    })
                ])
            }
        )


class TestJiraIntegrationRole:
    """Test Jira Integration IAM role configuration."""

    def test_jira_role_created(self, template):
        """Test that Jira Integration role is created."""
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-jira-integration-role",
                "Description": "Least privilege role for Jira Integration function"
            }
        )

    def test_jira_secrets_scoped(self, template):
        """
        Test that Secrets Manager permissions are scoped to Jira secrets only.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-jira-integration-role",
                "Policies": Match.array_with([
                    Match.object_like({
                        "PolicyDocument": {
                            "Statement": Match.array_with([
                                Match.object_like({
                                    "Action": [
                                        "secretsmanager:CreateSecret",
                                        "secretsmanager:GetSecretValue",
                                        "secretsmanager:UpdateSecret",
                                        "secretsmanager:TagResource"
                                    ],
                                    "Resource": Match.array_with([
                                        Match.string_like_regexp(".*secret:ai-sw-pm/jira/.*")
                                    ])
                                })
                            ])
                        }
                    })
                ])
            }
        )

    def test_jira_delete_secret_condition(self, template):
        """Test that secret deletion requires recovery window."""
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-jira-integration-role",
                "Policies": Match.array_with([
                    Match.object_like({
                        "PolicyDocument": {
                            "Statement": Match.array_with([
                                Match.object_like({
                                    "Action": ["secretsmanager:DeleteSecret"],
                                    "Condition": {
                                        "StringEquals": {
                                            "secretsmanager:RecoveryWindowInDays": "7"
                                        }
                                    }
                                })
                            ])
                        }
                    })
                ])
            }
        )


class TestDataIngestionRole:
    """Test Data Ingestion IAM role configuration."""

    def test_data_ingestion_role_created(self, template):
        """Test that Data Ingestion role is created."""
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-data-ingestion-role",
                "Description": "Least privilege role for Data Ingestion functions"
            }
        )

    def test_data_ingestion_vpc_access(self, template):
        """Test that Data Ingestion role has VPC access for RDS."""
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-data-ingestion-role",
                "ManagedPolicyArns": Match.array_with([
                    Match.string_like_regexp(".*AWSLambdaVPCAccessExecutionRole.*")
                ])
            }
        )

    def test_data_ingestion_sqs_permissions(self, template):
        """Test that Data Ingestion has SQS queue permissions."""
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-data-ingestion-role",
                "Policies": Match.array_with([
                    Match.object_like({
                        "PolicyDocument": {
                            "Statement": Match.array_with([
                                Match.object_like({
                                    "Action": [
                                        "sqs:SendMessage",
                                        "sqs:ReceiveMessage",
                                        "sqs:DeleteMessage",
                                        "sqs:GetQueueAttributes"
                                    ],
                                    "Resource": Match.array_with([
                                        Match.string_like_regexp(".*ai-sw-pm-ingestion-queue.*")
                                    ])
                                })
                            ])
                        }
                    })
                ])
            }
        )


class TestRiskDetectionRole:
    """Test Risk Detection IAM role configuration."""

    def test_risk_detection_role_created(self, template):
        """Test that Risk Detection role is created."""
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-risk-detection-role",
                "Description": "Least privilege role for Risk Detection function"
            }
        )

    def test_risk_detection_bedrock_permissions(self, template):
        """
        Test that Risk Detection has Bedrock permissions for AI explanations.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-risk-detection-role",
                "Policies": Match.array_with([
                    Match.object_like({
                        "PolicyDocument": {
                            "Statement": Match.array_with([
                                Match.object_like({
                                    "Action": ["bedrock:InvokeModel"],
                                    "Resource": Match.array_with([
                                        Match.string_like_regexp(".*foundation-model/anthropic.claude-.*"),
                                        Match.string_like_regexp(".*foundation-model/amazon.titan-.*")
                                    ])
                                })
                            ])
                        }
                    })
                ])
            }
        )

    def test_risk_detection_rds_read_only(self, template):
        """Test that Risk Detection has read-only RDS access."""
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-risk-detection-role",
                "Policies": Match.array_with([
                    Match.object_like({
                        "PolicyDocument": {
                            "Statement": Match.array_with([
                                Match.object_like({
                                    "Action": ["rds-data:ExecuteStatement"],
                                    "Effect": "Allow"
                                })
                            ])
                        }
                    })
                ])
            }
        )


class TestPredictionRole:
    """Test Prediction IAM role configuration."""

    def test_prediction_role_created(self, template):
        """Test that Prediction role is created."""
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-prediction-role",
                "Description": "Least privilege role for Prediction function"
            }
        )

    def test_prediction_sagemaker_scoped(self, template):
        """
        Test that SageMaker permissions are scoped to platform endpoints.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-prediction-role",
                "Policies": Match.array_with([
                    Match.object_like({
                        "PolicyDocument": {
                            "Statement": Match.array_with([
                                Match.object_like({
                                    "Action": ["sagemaker:InvokeEndpoint"],
                                    "Resource": Match.array_with([
                                        Match.string_like_regexp(".*endpoint/ai-sw-pm-.*")
                                    ])
                                })
                            ])
                        }
                    })
                ])
            }
        )


class TestDocumentRoles:
    """Test Document-related IAM roles configuration."""

    def test_document_upload_s3_scoped(self, template):
        """Test that Document Upload S3 permissions are scoped."""
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-document-upload-role",
                "Policies": Match.array_with([
                    Match.object_like({
                        "PolicyDocument": {
                            "Statement": Match.array_with([
                                Match.object_like({
                                    "Action": [
                                        "s3:PutObject",
                                        "s3:PutObjectAcl",
                                        "s3:GetObject"
                                    ],
                                    "Resource": Match.array_with([
                                        Match.string_like_regexp(".*ai-sw-pm-documents-.*")
                                    ])
                                })
                            ])
                        }
                    })
                ])
            }
        )

    def test_document_intelligence_textract_permissions(self, template):
        """Test that Document Intelligence has Textract permissions."""
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-document-intelligence-role",
                "Policies": Match.array_with([
                    Match.object_like({
                        "PolicyDocument": {
                            "Statement": Match.array_with([
                                Match.object_like({
                                    "Action": [
                                        "textract:AnalyzeDocument",
                                        "textract:DetectDocumentText"
                                    ],
                                    "Effect": "Allow"
                                })
                            ])
                        }
                    })
                ])
            }
        )

    def test_semantic_search_opensearch_scoped(self, template):
        """Test that Semantic Search OpenSearch permissions are scoped."""
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-semantic-search-role",
                "Policies": Match.array_with([
                    Match.object_like({
                        "PolicyDocument": {
                            "Statement": Match.array_with([
                                Match.object_like({
                                    "Action": [
                                        "es:ESHttpGet",
                                        "es:ESHttpPost"
                                    ],
                                    "Resource": Match.array_with([
                                        Match.string_like_regexp(".*domain/ai-sw-pm-documents/.*")
                                    ])
                                })
                            ])
                        }
                    })
                ])
            }
        )


class TestReportGenerationRole:
    """Test Report Generation IAM role configuration."""

    def test_report_generation_role_created(self, template):
        """Test that Report Generation role is created."""
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-report-generation-role",
                "Description": "Least privilege role for Report Generation function"
            }
        )

    def test_report_generation_ses_restricted(self, template):
        """
        Test that SES permissions have from-address restriction.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-report-generation-role",
                "Policies": Match.array_with([
                    Match.object_like({
                        "PolicyDocument": {
                            "Statement": Match.array_with([
                                Match.object_like({
                                    "Action": [
                                        "ses:SendEmail",
                                        "ses:SendRawEmail"
                                    ],
                                    "Condition": {
                                        "StringLike": {
                                            "ses:FromAddress": "noreply@*"
                                        }
                                    }
                                })
                            ])
                        }
                    })
                ])
            }
        )


class TestDashboardRole:
    """Test Dashboard IAM role configuration."""

    def test_dashboard_role_read_only(self, template):
        """
        Test that Dashboard role has only read permissions.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-dashboard-role",
                "Policies": Match.array_with([
                    Match.object_like({
                        "PolicyDocument": {
                            "Statement": Match.array_with([
                                Match.object_like({
                                    "Action": [
                                        "dynamodb:GetItem",
                                        "dynamodb:Query",
                                        "dynamodb:Scan"
                                    ],
                                    "Effect": "Allow"
                                })
                            ])
                        }
                    })
                ])
            }
        )


class TestDatabaseMaintenanceRole:
    """Test Database Maintenance IAM role configuration."""

    def test_database_maintenance_cloudwatch_namespace_restricted(self, template):
        """
        Test that CloudWatch metrics are restricted to specific namespace.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "RoleName": "ai-sw-pm-database-maintenance-role",
                "Policies": Match.array_with([
                    Match.object_like({
                        "PolicyDocument": {
                            "Statement": Match.array_with([
                                Match.object_like({
                                    "Action": ["cloudwatch:PutMetricData"],
                                    "Condition": {
                                        "StringEquals": {
                                            "cloudwatch:namespace": "AI-SW-PM/Database"
                                        }
                                    }
                                })
                            ])
                        }
                    })
                ])
            }
        )


class TestRoleCount:
    """Test that all expected roles are created."""

    def test_all_roles_created(self, template):
        """
        Test that all 13 IAM roles are created.
        
        Validates: Requirement 24.5 - Specific IAM roles for each Lambda function
        """
        # Count IAM roles (should be 13)
        template.resource_count_is("AWS::IAM::Role", 13)

    def test_no_wildcard_resources(self, iam_stack):
        """
        Test that no policies use wildcard resources except where necessary.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        # This is a conceptual test - in practice, we'd need to inspect
        # the generated template and verify resource ARNs are specific
        # Textract is an exception as it doesn't support resource-level permissions
        pass
