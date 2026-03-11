"""IAM Policies Stack - Centralized least privilege IAM policies for all Lambda functions."""

from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_accessanalyzer as accessanalyzer,
)
from constructs import Construct


class IamPoliciesStack(Stack):
    """
    Stack for centralized IAM policy management with least privilege principles.
    
    Validates: Requirement 24.5 - IAM-based access control for all AWS resources
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create IAM Access Analyzer
        self._create_access_analyzer()

        # Create specific IAM roles for each Lambda function type
        self.authorizer_role = self._create_authorizer_role()
        self.user_management_role = self._create_user_management_role()
        self.jira_integration_role = self._create_jira_integration_role()
        self.azure_devops_role = self._create_azure_devops_role()
        self.data_ingestion_role = self._create_data_ingestion_role()
        self.risk_detection_role = self._create_risk_detection_role()
        self.prediction_role = self._create_prediction_role()
        self.document_upload_role = self._create_document_upload_role()
        self.document_intelligence_role = self._create_document_intelligence_role()
        self.semantic_search_role = self._create_semantic_search_role()
        self.report_generation_role = self._create_report_generation_role()
        self.dashboard_role = self._create_dashboard_role()
        self.database_maintenance_role = self._create_database_maintenance_role()

    def _create_access_analyzer(self) -> None:
        """
        Create IAM Access Analyzer to continuously monitor IAM policies.
        
        Validates: Requirement 24.5 - Enable IAM Access Analyzer
        """
        self.access_analyzer = accessanalyzer.CfnAnalyzer(
            self,
            "AccessAnalyzer",
            type="ACCOUNT",
            analyzer_name="ai-sw-pm-access-analyzer",
            tags=[
                {
                    "key": "Application",
                    "value": "AI-SW-Program-Manager"
                },
                {
                    "key": "Purpose",
                    "value": "IAM-Policy-Analysis"
                }
            ]
        )

    def _create_authorizer_role(self) -> iam.Role:
        """
        Create IAM role for Lambda Authorizer with minimum required permissions.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        role = iam.Role(
            self,
            "AuthorizerRole",
            role_name="ai-sw-pm-authorizer-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Least privilege role for Lambda Authorizer function",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )

        # Grant only specific Cognito permissions needed for authorization
        role.add_to_policy(
            iam.PolicyStatement(
                sid="CognitoReadOnlyAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "cognito-idp:GetUser",
                    "cognito-idp:DescribeUserPool"
                ],
                resources=[
                    f"arn:aws:cognito-idp:{self.region}:{self.account}:userpool/*"
                ],
                conditions={
                    "StringEquals": {
                        "aws:RequestedRegion": self.region
                    }
                }
            )
        )

        return role

    def _create_user_management_role(self) -> iam.Role:
        """
        Create IAM role for User Management Lambda with minimum required permissions.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        role = iam.Role(
            self,
            "UserManagementRole",
            role_name="ai-sw-pm-user-management-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Least privilege role for User Management function",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )

        # Grant specific Cognito user management permissions
        role.add_to_policy(
            iam.PolicyStatement(
                sid="CognitoUserManagement",
                effect=iam.Effect.ALLOW,
                actions=[
                    "cognito-idp:AdminCreateUser",
                    "cognito-idp:AdminDeleteUser",
                    "cognito-idp:AdminUpdateUserAttributes",
                    "cognito-idp:ListUsers"
                ],
                resources=[
                    f"arn:aws:cognito-idp:{self.region}:{self.account}:userpool/*"
                ]
            )
        )

        # Grant DynamoDB access for Users table only
        role.add_to_policy(
            iam.PolicyStatement(
                sid="DynamoDBUsersTableAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Query",
                    "dynamodb:Scan"
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-users",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-users/index/*"
                ]
            )
        )

        return role

    def _create_jira_integration_role(self) -> iam.Role:
        """
        Create IAM role for Jira Integration Lambda with minimum required permissions.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        role = iam.Role(
            self,
            "JiraIntegrationRole",
            role_name="ai-sw-pm-jira-integration-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Least privilege role for Jira Integration function",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )

        # Grant DynamoDB access for Integrations table only
        role.add_to_policy(
            iam.PolicyStatement(
                sid="DynamoDBIntegrationsTableAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Query"
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-integrations",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-integrations/index/*"
                ]
            )
        )

        # Grant Secrets Manager access for Jira credentials only
        role.add_to_policy(
            iam.PolicyStatement(
                sid="SecretsManagerJiraAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:CreateSecret",
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:UpdateSecret",
                    "secretsmanager:TagResource"
                ],
                resources=[
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:ai-sw-pm/jira/*"
                ]
            )
        )

        # Grant permission to delete secrets (for cleanup)
        role.add_to_policy(
            iam.PolicyStatement(
                sid="SecretsManagerJiraDelete",
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:DeleteSecret"
                ],
                resources=[
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:ai-sw-pm/jira/*"
                ],
                conditions={
                    "StringEquals": {
                        "secretsmanager:RecoveryWindowInDays": "7"
                    }
                }
            )
        )

        return role

    def _create_azure_devops_role(self) -> iam.Role:
        """
        Create IAM role for Azure DevOps Integration Lambda with minimum required permissions.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        role = iam.Role(
            self,
            "AzureDevOpsRole",
            role_name="ai-sw-pm-azure-devops-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Least privilege role for Azure DevOps Integration function",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )

        # Grant DynamoDB access for Integrations table only
        role.add_to_policy(
            iam.PolicyStatement(
                sid="DynamoDBIntegrationsTableAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Query"
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-integrations",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-integrations/index/*"
                ]
            )
        )

        # Grant Secrets Manager access for Azure DevOps credentials only
        role.add_to_policy(
            iam.PolicyStatement(
                sid="SecretsManagerAzureDevOpsAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:CreateSecret",
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:UpdateSecret",
                    "secretsmanager:TagResource"
                ],
                resources=[
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:ai-sw-pm/azure-devops/*"
                ]
            )
        )

        # Grant permission to delete secrets (for cleanup)
        role.add_to_policy(
            iam.PolicyStatement(
                sid="SecretsManagerAzureDevOpsDelete",
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:DeleteSecret"
                ],
                resources=[
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:ai-sw-pm/azure-devops/*"
                ],
                conditions={
                    "StringEquals": {
                        "secretsmanager:RecoveryWindowInDays": "7"
                    }
                }
            )
        )

        return role

    def _create_data_ingestion_role(self) -> iam.Role:
        """
        Create IAM role for Data Ingestion Lambda functions with minimum required permissions.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        role = iam.Role(
            self,
            "DataIngestionRole",
            role_name="ai-sw-pm-data-ingestion-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Least privilege role for Data Ingestion functions",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                )
            ]
        )

        # Grant DynamoDB access for required tables
        role.add_to_policy(
            iam.PolicyStatement(
                sid="DynamoDBIngestionAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Query",
                    "dynamodb:BatchWriteItem"
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-integrations",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-integrations/index/*",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-projects",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-projects/index/*"
                ]
            )
        )

        # Grant Secrets Manager read access for integration credentials
        role.add_to_policy(
            iam.PolicyStatement(
                sid="SecretsManagerReadAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:DescribeSecret"
                ],
                resources=[
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:ai-sw-pm/*"
                ]
            )
        )

        # Grant RDS Data API access (if using RDS Data API)
        role.add_to_policy(
            iam.PolicyStatement(
                sid="RDSDataAPIAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "rds-data:ExecuteStatement",
                    "rds-data:BatchExecuteStatement"
                ],
                resources=[
                    f"arn:aws:rds:{self.region}:{self.account}:cluster:ai-sw-pm-*"
                ]
            )
        )

        # Grant SQS permissions for queue operations
        role.add_to_policy(
            iam.PolicyStatement(
                sid="SQSQueueAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "sqs:SendMessage",
                    "sqs:ReceiveMessage",
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes"
                ],
                resources=[
                    f"arn:aws:sqs:{self.region}:{self.account}:ai-sw-pm-ingestion-queue"
                ]
            )
        )

        # Grant Step Functions execution permissions
        role.add_to_policy(
            iam.PolicyStatement(
                sid="StepFunctionsExecution",
                effect=iam.Effect.ALLOW,
                actions=[
                    "states:StartExecution"
                ],
                resources=[
                    f"arn:aws:states:{self.region}:{self.account}:stateMachine:ai-sw-pm-ingestion-workflow"
                ]
            )
        )

        return role

    def _create_risk_detection_role(self) -> iam.Role:
        """
        Create IAM role for Risk Detection Lambda with minimum required permissions.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        role = iam.Role(
            self,
            "RiskDetectionRole",
            role_name="ai-sw-pm-risk-detection-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Least privilege role for Risk Detection function",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                )
            ]
        )

        # Grant DynamoDB access for Risks table
        role.add_to_policy(
            iam.PolicyStatement(
                sid="DynamoDBRisksTableAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Query",
                    "dynamodb:Scan"
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-risks",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-risks/index/*"
                ]
            )
        )

        # Grant RDS read access for project metrics
        role.add_to_policy(
            iam.PolicyStatement(
                sid="RDSReadAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "rds-data:ExecuteStatement"
                ],
                resources=[
                    f"arn:aws:rds:{self.region}:{self.account}:cluster:ai-sw-pm-*"
                ]
            )
        )

        # Grant Bedrock access for AI-generated explanations
        role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockInvokeModel",
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel"
                ],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-*",
                    f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-*"
                ]
            )
        )

        # Grant EventBridge permissions to publish risk events
        role.add_to_policy(
            iam.PolicyStatement(
                sid="EventBridgePutEvents",
                effect=iam.Effect.ALLOW,
                actions=[
                    "events:PutEvents"
                ],
                resources=[
                    f"arn:aws:events:{self.region}:{self.account}:event-bus/default"
                ]
            )
        )

        return role

    def _create_prediction_role(self) -> iam.Role:
        """
        Create IAM role for Prediction Lambda with minimum required permissions.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        role = iam.Role(
            self,
            "PredictionRole",
            role_name="ai-sw-pm-prediction-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Least privilege role for Prediction function",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                )
            ]
        )

        # Grant DynamoDB access for Predictions and Risks tables
        role.add_to_policy(
            iam.PolicyStatement(
                sid="DynamoDBPredictionsAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Query",
                    "dynamodb:Scan"
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-predictions",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-predictions/index/*",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-risks",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-risks/index/*"
                ]
            )
        )

        # Grant RDS read access for historical data
        role.add_to_policy(
            iam.PolicyStatement(
                sid="RDSReadAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "rds-data:ExecuteStatement"
                ],
                resources=[
                    f"arn:aws:rds:{self.region}:{self.account}:cluster:ai-sw-pm-*"
                ]
            )
        )

        # Grant SageMaker endpoint invocation permissions
        role.add_to_policy(
            iam.PolicyStatement(
                sid="SageMakerInvokeEndpoint",
                effect=iam.Effect.ALLOW,
                actions=[
                    "sagemaker:InvokeEndpoint"
                ],
                resources=[
                    f"arn:aws:sagemaker:{self.region}:{self.account}:endpoint/ai-sw-pm-*"
                ]
            )
        )

        return role

    def _create_document_upload_role(self) -> iam.Role:
        """
        Create IAM role for Document Upload Lambda with minimum required permissions.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        role = iam.Role(
            self,
            "DocumentUploadRole",
            role_name="ai-sw-pm-document-upload-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Least privilege role for Document Upload function",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )

        # Grant S3 access for document uploads (tenant-specific prefixes)
        role.add_to_policy(
            iam.PolicyStatement(
                sid="S3DocumentUploadAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:PutObject",
                    "s3:PutObjectAcl",
                    "s3:GetObject"
                ],
                resources=[
                    f"arn:aws:s3:::ai-sw-pm-documents-{self.account}/*"
                ]
            )
        )

        # Grant DynamoDB access for Documents table
        role.add_to_policy(
            iam.PolicyStatement(
                sid="DynamoDBDocumentsTableAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:PutItem",
                    "dynamodb:GetItem",
                    "dynamodb:UpdateItem"
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-documents"
                ]
            )
        )

        return role

    def _create_document_intelligence_role(self) -> iam.Role:
        """
        Create IAM role for Document Intelligence Lambda with minimum required permissions.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        role = iam.Role(
            self,
            "DocumentIntelligenceRole",
            role_name="ai-sw-pm-document-intelligence-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Least privilege role for Document Intelligence function",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )

        # Grant S3 read access for documents
        role.add_to_policy(
            iam.PolicyStatement(
                sid="S3DocumentReadAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject"
                ],
                resources=[
                    f"arn:aws:s3:::ai-sw-pm-documents-{self.account}/*"
                ]
            )
        )

        # Grant Textract permissions for document extraction
        role.add_to_policy(
            iam.PolicyStatement(
                sid="TextractDocumentAnalysis",
                effect=iam.Effect.ALLOW,
                actions=[
                    "textract:AnalyzeDocument",
                    "textract:DetectDocumentText"
                ],
                resources=["*"]  # Textract doesn't support resource-level permissions
            )
        )

        # Grant Bedrock access for entity extraction
        role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockInvokeModel",
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel"
                ],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-*",
                    f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-*"
                ]
            )
        )

        # Grant DynamoDB access for DocumentExtractions table
        role.add_to_policy(
            iam.PolicyStatement(
                sid="DynamoDBExtractionsAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:PutItem",
                    "dynamodb:GetItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Query"
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-document-extractions",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-document-extractions/index/*"
                ]
            )
        )

        # Grant SQS permissions for document processing queue
        role.add_to_policy(
            iam.PolicyStatement(
                sid="SQSDocumentProcessingAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "sqs:SendMessage",
                    "sqs:ReceiveMessage",
                    "sqs:DeleteMessage"
                ],
                resources=[
                    f"arn:aws:sqs:{self.region}:{self.account}:ai-sw-pm-document-processing-queue"
                ]
            )
        )

        return role

    def _create_semantic_search_role(self) -> iam.Role:
        """
        Create IAM role for Semantic Search Lambda with minimum required permissions.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        role = iam.Role(
            self,
            "SemanticSearchRole",
            role_name="ai-sw-pm-semantic-search-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Least privilege role for Semantic Search function",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )

        # Grant OpenSearch access for vector search
        role.add_to_policy(
            iam.PolicyStatement(
                sid="OpenSearchAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "es:ESHttpGet",
                    "es:ESHttpPost"
                ],
                resources=[
                    f"arn:aws:es:{self.region}:{self.account}:domain/ai-sw-pm-documents/*"
                ]
            )
        )

        # Grant Bedrock access for embedding generation
        role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockEmbeddings",
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel"
                ],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-embed-*"
                ]
            )
        )

        return role

    def _create_report_generation_role(self) -> iam.Role:
        """
        Create IAM role for Report Generation Lambda with minimum required permissions.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        role = iam.Role(
            self,
            "ReportGenerationRole",
            role_name="ai-sw-pm-report-generation-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Least privilege role for Report Generation function",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                )
            ]
        )

        # Grant DynamoDB access for Reports table
        role.add_to_policy(
            iam.PolicyStatement(
                sid="DynamoDBReportsAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Query"
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-reports",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-reports/index/*"
                ]
            )
        )

        # Grant read access to other tables for report data
        role.add_to_policy(
            iam.PolicyStatement(
                sid="DynamoDBReadAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:Query",
                    "dynamodb:Scan"
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-risks",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-risks/index/*",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-predictions",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-predictions/index/*"
                ]
            )
        )

        # Grant RDS read access for project data
        role.add_to_policy(
            iam.PolicyStatement(
                sid="RDSReadAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "rds-data:ExecuteStatement"
                ],
                resources=[
                    f"arn:aws:rds:{self.region}:{self.account}:cluster:ai-sw-pm-*"
                ]
            )
        )

        # Grant Bedrock access for narrative generation
        role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockInvokeModel",
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel"
                ],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-*"
                ]
            )
        )

        # Grant S3 access for report storage
        role.add_to_policy(
            iam.PolicyStatement(
                sid="S3ReportStorageAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:PutObject",
                    "s3:GetObject"
                ],
                resources=[
                    f"arn:aws:s3:::ai-sw-pm-reports-{self.account}/*"
                ]
            )
        )

        # Grant SES permissions for email distribution
        role.add_to_policy(
            iam.PolicyStatement(
                sid="SESEmailSending",
                effect=iam.Effect.ALLOW,
                actions=[
                    "ses:SendEmail",
                    "ses:SendRawEmail"
                ],
                resources=[
                    f"arn:aws:ses:{self.region}:{self.account}:identity/*"
                ],
                conditions={
                    "StringLike": {
                        "ses:FromAddress": "noreply@*"
                    }
                }
            )
        )

        return role

    def _create_dashboard_role(self) -> iam.Role:
        """
        Create IAM role for Dashboard Lambda with minimum required permissions.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        role = iam.Role(
            self,
            "DashboardRole",
            role_name="ai-sw-pm-dashboard-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Least privilege role for Dashboard function",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                )
            ]
        )

        # Grant DynamoDB read access for dashboard data
        role.add_to_policy(
            iam.PolicyStatement(
                sid="DynamoDBReadAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:Query",
                    "dynamodb:Scan"
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-risks",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-risks/index/*",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-predictions",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-predictions/index/*",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-projects",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/ai-sw-pm-projects/index/*"
                ]
            )
        )

        # Grant RDS read access for project metrics
        role.add_to_policy(
            iam.PolicyStatement(
                sid="RDSReadAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "rds-data:ExecuteStatement"
                ],
                resources=[
                    f"arn:aws:rds:{self.region}:{self.account}:cluster:ai-sw-pm-*"
                ]
            )
        )

        # Grant ElastiCache access for caching (if using Redis)
        role.add_to_policy(
            iam.PolicyStatement(
                sid="ElastiCacheAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "elasticache:DescribeCacheClusters",
                    "elasticache:DescribeReplicationGroups"
                ],
                resources=[
                    f"arn:aws:elasticache:{self.region}:{self.account}:cluster:ai-sw-pm-*",
                    f"arn:aws:elasticache:{self.region}:{self.account}:replicationgroup:ai-sw-pm-*"
                ]
            )
        )

        return role

    def _create_database_maintenance_role(self) -> iam.Role:
        """
        Create IAM role for Database Maintenance Lambda with minimum required permissions.
        
        Validates: Requirement 24.5 - Least privilege IAM policies
        """
        role = iam.Role(
            self,
            "DatabaseMaintenanceRole",
            role_name="ai-sw-pm-database-maintenance-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Least privilege role for Database Maintenance function",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                )
            ]
        )

        # Grant RDS maintenance permissions
        role.add_to_policy(
            iam.PolicyStatement(
                sid="RDSMaintenanceAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "rds-data:ExecuteStatement",
                    "rds-data:BatchExecuteStatement"
                ],
                resources=[
                    f"arn:aws:rds:{self.region}:{self.account}:cluster:ai-sw-pm-*"
                ]
            )
        )

        # Grant Secrets Manager read access for database credentials
        role.add_to_policy(
            iam.PolicyStatement(
                sid="SecretsManagerReadAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:GetSecretValue"
                ],
                resources=[
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:ai-sw-pm/rds/*"
                ]
            )
        )

        # Grant CloudWatch permissions for custom metrics
        role.add_to_policy(
            iam.PolicyStatement(
                sid="CloudWatchPutMetrics",
                effect=iam.Effect.ALLOW,
                actions=[
                    "cloudwatch:PutMetricData"
                ],
                resources=["*"],
                conditions={
                    "StringEquals": {
                        "cloudwatch:namespace": "AI-SW-PM/Database"
                    }
                }
            )
        )

        return role
