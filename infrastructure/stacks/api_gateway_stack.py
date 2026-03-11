"""API Gateway stack - REST API with Lambda integrations."""

from aws_cdk import (
    Stack,
    Duration,
    aws_apigateway as apigw,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_logs as logs,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    RemovalPolicy,
)
from constructs import Construct
import os
from ..lambda_optimization_config import (
    PROVISIONED_CONCURRENCY_CONFIG,
    MEMORY_CONFIG
)


class ApiGatewayStack(Stack):
    """Stack for API Gateway and Lambda function integrations."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        user_pool,
        user_pool_client,
        authorizer_function,
        users_table,
        integrations_table,
        risks_table,
        predictions_table,
        reports_table,
        alarm_topic: sns.Topic,
        lambda_layers=None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Store references
        self.user_pool = user_pool
        self.user_pool_client = user_pool_client
        self.authorizer_function = authorizer_function
        self.users_table = users_table
        self.integrations_table = integrations_table
        self.risks_table = risks_table
        self.predictions_table = predictions_table
        self.reports_table = reports_table
        self.alarm_topic = alarm_topic
        self.lambda_layers = lambda_layers or {}

        # Create API Gateway
        self._create_api_gateway()

        # Create Lambda Authorizer
        self._create_authorizer()

        # Create Lambda functions
        self._create_lambda_functions()

        # Configure provisioned concurrency for critical functions
        self._configure_provisioned_concurrency()

        # Create API resources and methods
        self._create_user_management_endpoints()
        self._create_integration_endpoints()
        self._create_risk_detection_endpoints()
        self._create_prediction_endpoints()
        self._create_document_endpoints()
        self._create_report_endpoints()
        self._create_dashboard_endpoints()

        # Configure CloudWatch alarms
        self._create_alarms()

        # Enable X-Ray tracing
        self._enable_xray_tracing()

    def _create_api_gateway(self) -> None:
        """Create API Gateway REST API."""

        # Create CloudWatch log group for API Gateway
        api_log_group = logs.LogGroup(
            self,
            "APIGatewayLogGroup",
            log_group_name="/aws/apigateway/ai-sw-pm-api",
            retention=logs.RetentionDays.THREE_MONTHS,
            removal_policy=RemovalPolicy.RETAIN
        )

        # Create REST API
        self.api = apigw.RestApi(
            self,
            "RestAPI",
            rest_api_name="ai-sw-pm-api",
            description="AI SW Program Manager REST API",
            # Enable CORS
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=[
                    "Content-Type",
                    "X-Amz-Date",
                    "Authorization",
                    "X-Api-Key",
                    "X-Amz-Security-Token"
                ],
                allow_credentials=True
            ),
            # CloudWatch logging
            cloud_watch_role=True,
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                throttling_rate_limit=1000,  # Requests per second
                throttling_burst_limit=2000,  # Burst capacity
                logging_level=apigw.MethodLoggingLevel.INFO,
                data_trace_enabled=True,
                access_log_destination=apigw.LogGroupLogDestination(api_log_group),
                access_log_format=apigw.AccessLogFormat.json_with_standard_fields(
                    caller=True,
                    http_method=True,
                    ip=True,
                    protocol=True,
                    request_time=True,
                    resource_path=True,
                    response_length=True,
                    status=True,
                    user=True
                ),
                # Enable X-Ray tracing
                tracing_enabled=True,
                # Metrics
                metrics_enabled=True
            ),
            # Request validation
            endpoint_types=[apigw.EndpointType.REGIONAL]
        )

        # Create usage plan for rate limiting per tenant
        self.usage_plan = self.api.add_usage_plan(
            "UsagePlan",
            name="ai-sw-pm-usage-plan",
            description="Usage plan with rate limiting per tenant",
            throttle=apigw.ThrottleSettings(
                rate_limit=100,  # Requests per second per tenant
                burst_limit=200  # Burst capacity per tenant
            ),
            quota=apigw.QuotaSettings(
                limit=1000000,  # 1M requests per month per tenant
                period=apigw.Period.MONTH
            )
        )

        # Associate usage plan with API stage
        self.usage_plan.add_api_stage(
            stage=self.api.deployment_stage
        )

    def _create_authorizer(self) -> None:
        """Create Lambda Authorizer for API Gateway."""

        self.authorizer = apigw.RequestAuthorizer(
            self,
            "LambdaAuthorizer",
            handler=self.authorizer_function,
            identity_sources=[apigw.IdentitySource.header("Authorization")],
            results_cache_ttl=Duration.minutes(5),
            authorizer_name="ai-sw-pm-authorizer"
        )

    def _get_lambda_config(self, function_type: str) -> dict:
        """
        Get optimized Lambda configuration for a function type.
        
        Validates: Requirements 23.1, 23.2, 23.4
        """
        for config_type, config in MEMORY_CONFIG.items():
            if function_type in config["functions"]:
                return {
                    "memory_size": config["memory_size"],
                    "timeout": config["timeout"]
                }
        # Default configuration
        return {
            "memory_size": 512,
            "timeout": Duration.seconds(30)
        }

    def _get_lambda_layers(self, function_type: str) -> list:
        """
        Get appropriate Lambda layers for a function type.
        
        Validates: Requirement 23.2 (reduce package size)
        """
        layers = []
        
        # All functions get common layer
        if "common" in self.lambda_layers:
            layers.append(self.lambda_layers["common"])
        
        # Add data processing layer for specific functions
        if function_type in ["risk_detection", "prediction", "report_generation"]:
            if "data_processing" in self.lambda_layers:
                layers.append(self.lambda_layers["data_processing"])
        
        # Add AI/ML layer for AI-powered functions
        if function_type in ["document_intelligence", "report_generation", "risk_detection"]:
            if "ai_ml" in self.lambda_layers:
                layers.append(self.lambda_layers["ai_ml"])
        
        return layers

    def _create_lambda_functions(self) -> None:
        """
        Create Lambda functions for API endpoints with optimized settings.
        
        Validates: Requirements 23.1, 23.2, 23.4
        """

        # Common Lambda environment variables
        common_env = {
            "USER_POOL_ID": self.user_pool.user_pool_id,
            "USERS_TABLE_NAME": self.users_table.table_name,
            "INTEGRATIONS_TABLE_NAME": self.integrations_table.table_name,
            "RISKS_TABLE_NAME": self.risks_table.table_name,
            "PREDICTIONS_TABLE_NAME": self.predictions_table.table_name,
            "REPORTS_TABLE_NAME": self.reports_table.table_name,
        }

        # User Management Lambda - optimized for standard workload
        user_mgmt_config = self._get_lambda_config("user_management")
        self.user_management_function = lambda_.Function(
            self,
            "UserManagementFunction",
            function_name="ai-sw-pm-user-management",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.create_user",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/user_management")
            ),
            environment=common_env,
            timeout=user_mgmt_config["timeout"],
            memory_size=user_mgmt_config["memory_size"],
            tracing=lambda_.Tracing.ACTIVE,
            description="User management operations",
            layers=self._get_lambda_layers("user_management")
        )

        # Grant permissions
        self.users_table.grant_read_write_data(self.user_management_function)
        self.user_management_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "cognito-idp:AdminCreateUser",
                    "cognito-idp:AdminDeleteUser",
                    "cognito-idp:AdminUpdateUserAttributes",
                    "cognito-idp:ListUsers"
                ],
                resources=[self.user_pool.user_pool_arn]
            )
        )

        # Jira Integration Lambda - optimized for standard workload
        jira_config = self._get_lambda_config("jira_integration")
        self.jira_integration_function = lambda_.Function(
            self,
            "JiraIntegrationFunction",
            function_name="ai-sw-pm-jira-integration",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.configure_jira_integration",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/jira_integration")
            ),
            environment=common_env,
            timeout=jira_config["timeout"],
            memory_size=jira_config["memory_size"],
            tracing=lambda_.Tracing.ACTIVE,
            description="Jira integration configuration",
            layers=self._get_lambda_layers("jira_integration")
        )

        self.integrations_table.grant_read_write_data(self.jira_integration_function)
        self.jira_integration_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "secretsmanager:CreateSecret",
                    "secretsmanager:DeleteSecret",
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:TagResource"
                ],
                resources=["*"]
            )
        )

        # Azure DevOps Integration Lambda - optimized for standard workload
        azure_config = self._get_lambda_config("azure_devops")
        self.azure_devops_function = lambda_.Function(
            self,
            "AzureDevOpsFunction",
            function_name="ai-sw-pm-azure-devops",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/azure_devops_integration")
            ),
            environment=common_env,
            timeout=azure_config["timeout"],
            memory_size=azure_config["memory_size"],
            tracing=lambda_.Tracing.ACTIVE,
            description="Azure DevOps integration",
            layers=self._get_lambda_layers("azure_devops")
        )

        self.integrations_table.grant_read_write_data(self.azure_devops_function)
        self.azure_devops_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "secretsmanager:CreateSecret",
                    "secretsmanager:DeleteSecret",
                    "secretsmanager:GetSecretValue"
                ],
                resources=["*"]
            )
        )

        # Risk Detection Lambda - optimized for memory-intensive workload
        risk_config = self._get_lambda_config("risk_detection")
        self.risk_detection_function = lambda_.Function(
            self,
            "RiskDetectionFunction",
            function_name="ai-sw-pm-risk-detection",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.list_risks_handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/risk_detection")
            ),
            environment=common_env,
            timeout=risk_config["timeout"],
            memory_size=risk_config["memory_size"],
            tracing=lambda_.Tracing.ACTIVE,
            description="Risk detection and listing",
            layers=self._get_lambda_layers("risk_detection")
        )

        self.risks_table.grant_read_write_data(self.risk_detection_function)

        # Prediction Lambda - optimized for memory-intensive workload
        prediction_config = self._get_lambda_config("prediction")
        self.prediction_function = lambda_.Function(
            self,
            "PredictionFunction",
            function_name="ai-sw-pm-prediction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.predict_delay_handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/prediction")
            ),
            environment=common_env,
            timeout=prediction_config["timeout"],
            memory_size=prediction_config["memory_size"],
            tracing=lambda_.Tracing.ACTIVE,
            description="ML-based predictions",
            layers=self._get_lambda_layers("prediction")
        )

        self.predictions_table.grant_read_write_data(self.prediction_function)
        self.risks_table.grant_read_write_data(self.prediction_function)
        self.prediction_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sagemaker:InvokeEndpoint"],
                resources=["*"]
            )
        )

        # Document Upload Lambda - optimized for standard workload
        doc_upload_config = self._get_lambda_config("document_upload")
        self.document_upload_function = lambda_.Function(
            self,
            "DocumentUploadFunction",
            function_name="ai-sw-pm-document-upload",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/document_upload")
            ),
            environment=common_env,
            timeout=doc_upload_config["timeout"],
            memory_size=doc_upload_config["memory_size"],
            tracing=lambda_.Tracing.ACTIVE,
            description="Document upload pre-signed URL generation",
            layers=self._get_lambda_layers("document_upload")
        )

        self.document_upload_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject", "s3:GetObject"],
                resources=["arn:aws:s3:::ai-sw-pm-documents-*/*"]
            )
        )

        # Document Intelligence Lambda - optimized for heavy processing
        doc_intel_config = self._get_lambda_config("document_intelligence")
        self.document_intelligence_function = lambda_.Function(
            self,
            "DocumentIntelligenceFunction",
            function_name="ai-sw-pm-document-intelligence",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/document_intelligence")
            ),
            environment=common_env,
            timeout=doc_intel_config["timeout"],
            memory_size=doc_intel_config["memory_size"],
            tracing=lambda_.Tracing.ACTIVE,
            description="Document intelligence and extraction",
            layers=self._get_lambda_layers("document_intelligence")
        )

        self.document_intelligence_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "textract:AnalyzeDocument",
                    "textract:DetectDocumentText"
                ],
                resources=["*"]
            )
        )

        # Semantic Search Lambda - optimized for standard workload
        search_config = self._get_lambda_config("semantic_search")
        self.semantic_search_function = lambda_.Function(
            self,
            "SemanticSearchFunction",
            function_name="ai-sw-pm-semantic-search",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="search_handler.lambda_handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/semantic_search")
            ),
            environment=common_env,
            timeout=search_config["timeout"],
            memory_size=search_config["memory_size"],
            tracing=lambda_.Tracing.ACTIVE,
            description="Semantic document search",
            layers=self._get_lambda_layers("semantic_search")
        )

        self.semantic_search_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["es:ESHttpPost", "es:ESHttpGet"],
                resources=["*"]
            )
        )

        # Report Generation Lambda - optimized for heavy processing
        report_config = self._get_lambda_config("report_generation")
        self.report_generation_function = lambda_.Function(
            self,
            "ReportGenerationFunction",
            function_name="ai-sw-pm-report-generation",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.generate_weekly_status_report_handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/report_generation")
            ),
            environment=common_env,
            timeout=report_config["timeout"],
            memory_size=report_config["memory_size"],
            tracing=lambda_.Tracing.ACTIVE,
            description="Report generation",
            layers=self._get_lambda_layers("report_generation")
        )

        self.reports_table.grant_read_write_data(self.report_generation_function)
        self.report_generation_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "s3:PutObject",
                    "s3:GetObject"
                ],
                resources=["*"]
            )
        )

        # Dashboard Lambda - optimized for standard workload with higher memory
        dashboard_config = self._get_lambda_config("dashboard")
        self.dashboard_function = lambda_.Function(
            self,
            "DashboardFunction",
            function_name="ai-sw-pm-dashboard",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.get_dashboard_overview_handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/dashboard")
            ),
            environment=common_env,
            timeout=dashboard_config["timeout"],
            memory_size=1024,  # Higher memory for faster aggregation
            tracing=lambda_.Tracing.ACTIVE,
            description="Dashboard data aggregation",
            layers=self._get_lambda_layers("dashboard")
        )

        self.risks_table.grant_read_data(self.dashboard_function)
        self.predictions_table.grant_read_data(self.dashboard_function)

    def _configure_provisioned_concurrency(self) -> None:
        """
        Configure provisioned concurrency for critical Lambda functions.
        
        Reduces cold start latency for high-traffic functions.
        Validates: Requirements 23.1, 23.6
        """
        # Configure provisioned concurrency for authorizer function
        if "authorizer" in PROVISIONED_CONCURRENCY_CONFIG:
            authorizer_alias = self.authorizer_function.current_version.add_alias(
                "prod",
                provisioned_concurrent_executions=PROVISIONED_CONCURRENCY_CONFIG["authorizer"]
            )
            # Note: API Gateway authorizer should reference the alias for provisioned concurrency benefits
        
        # Configure provisioned concurrency for dashboard function
        if "dashboard" in PROVISIONED_CONCURRENCY_CONFIG:
            dashboard_alias = self.dashboard_function.current_version.add_alias(
                "prod",
                provisioned_concurrent_executions=PROVISIONED_CONCURRENCY_CONFIG["dashboard"]
            )
        
        # Configure provisioned concurrency for user management function
        if "user_management" in PROVISIONED_CONCURRENCY_CONFIG:
            user_mgmt_alias = self.user_management_function.current_version.add_alias(
                "prod",
                provisioned_concurrent_executions=PROVISIONED_CONCURRENCY_CONFIG["user_management"]
            )

    def _create_user_management_endpoints(self) -> None:
        """Create user management API endpoints."""

        # /users resource
        users_resource = self.api.root.add_resource("users")

        # POST /users - Create user
        users_resource.add_method(
            "POST",
            apigw.LambdaIntegration(self.user_management_function),
            authorizer=self.authorizer,
            authorization_type=apigw.AuthorizationType.CUSTOM,
            request_validator=self._create_request_validator("CreateUserValidator", validate_body=True)
        )

        # GET /users - List users
        users_resource.add_method(
            "GET",
            apigw.LambdaIntegration(
                self.user_management_function,
                request_templates={"application/json": '{"handler": "list_users"}'}
            ),
            authorizer=self.authorizer,
            authorization_type=apigw.AuthorizationType.CUSTOM
        )

        # /users/{userId} resource
        user_resource = users_resource.add_resource("{userId}")

        # PUT /users/{userId}/role - Update user role
        role_resource = user_resource.add_resource("role")
        role_resource.add_method(
            "PUT",
            apigw.LambdaIntegration(
                self.user_management_function,
                request_templates={"application/json": '{"handler": "update_user_role"}'}
            ),
            authorizer=self.authorizer,
            authorization_type=apigw.AuthorizationType.CUSTOM,
            request_validator=self._create_request_validator("UpdateRoleValidator", validate_body=True)
        )

    def _create_integration_endpoints(self) -> None:
        """Create integration configuration API endpoints."""

        # /integrations resource
        integrations_resource = self.api.root.add_resource("integrations")

        # /integrations/jira resource
        jira_resource = integrations_resource.add_resource("jira")

        # POST /integrations/jira/configure
        configure_resource = jira_resource.add_resource("configure")
        configure_resource.add_method(
            "POST",
            apigw.LambdaIntegration(self.jira_integration_function),
            authorizer=self.authorizer,
            authorization_type=apigw.AuthorizationType.CUSTOM,
            request_validator=self._create_request_validator("ConfigureJiraValidator", validate_body=True)
        )

        # /integrations/azure-devops resource
        azure_resource = integrations_resource.add_resource("azure-devops")

        # POST /integrations/azure-devops/configure
        azure_configure_resource = azure_resource.add_resource("configure")
        azure_configure_resource.add_method(
            "POST",
            apigw.LambdaIntegration(self.azure_devops_function),
            authorizer=self.authorizer,
            authorization_type=apigw.AuthorizationType.CUSTOM,
            request_validator=self._create_request_validator("ConfigureAzureValidator", validate_body=True)
        )

    def _create_risk_detection_endpoints(self) -> None:
        """Create risk detection API endpoints."""

        # /risks resource
        risks_resource = self.api.root.add_resource("risks")

        # GET /risks - List risks
        risks_resource.add_method(
            "GET",
            apigw.LambdaIntegration(self.risk_detection_function),
            authorizer=self.authorizer,
            authorization_type=apigw.AuthorizationType.CUSTOM
        )

        # /risks/{riskId} resource
        risk_resource = risks_resource.add_resource("{riskId}")

        # PUT /risks/{riskId}/dismiss - Dismiss risk
        dismiss_resource = risk_resource.add_resource("dismiss")
        dismiss_resource.add_method(
            "PUT",
            apigw.LambdaIntegration(
                self.risk_detection_function,
                request_templates={"application/json": '{"handler": "dismiss_risk_handler"}'}
            ),
            authorizer=self.authorizer,
            authorization_type=apigw.AuthorizationType.CUSTOM,
            request_validator=self._create_request_validator("DismissRiskValidator", validate_body=True)
        )

    def _create_prediction_endpoints(self) -> None:
        """Create prediction API endpoints."""

        # /predictions resource
        predictions_resource = self.api.root.add_resource("predictions")

        # POST /predictions/delay-probability
        delay_resource = predictions_resource.add_resource("delay-probability")
        delay_resource.add_method(
            "POST",
            apigw.LambdaIntegration(self.prediction_function),
            authorizer=self.authorizer,
            authorization_type=apigw.AuthorizationType.CUSTOM,
            request_validator=self._create_request_validator("PredictDelayValidator", validate_body=True)
        )

        # POST /predictions/workload-imbalance
        workload_resource = predictions_resource.add_resource("workload-imbalance")
        workload_resource.add_method(
            "POST",
            apigw.LambdaIntegration(
                self.prediction_function,
                request_templates={"application/json": '{"handler": "predict_workload_handler"}'}
            ),
            authorizer=self.authorizer,
            authorization_type=apigw.AuthorizationType.CUSTOM,
            request_validator=self._create_request_validator("PredictWorkloadValidator", validate_body=True)
        )

        # GET /predictions/history
        history_resource = predictions_resource.add_resource("history")
        history_resource.add_method(
            "GET",
            apigw.LambdaIntegration(
                self.prediction_function,
                request_templates={"application/json": '{"handler": "get_prediction_history_handler"}'}
            ),
            authorizer=self.authorizer,
            authorization_type=apigw.AuthorizationType.CUSTOM
        )

    def _create_document_endpoints(self) -> None:
        """Create document management API endpoints."""

        # /documents resource
        documents_resource = self.api.root.add_resource("documents")

        # POST /documents/upload
        upload_resource = documents_resource.add_resource("upload")
        upload_resource.add_method(
            "POST",
            apigw.LambdaIntegration(self.document_upload_function),
            authorizer=self.authorizer,
            authorization_type=apigw.AuthorizationType.CUSTOM,
            request_validator=self._create_request_validator("UploadDocumentValidator", validate_body=True)
        )

        # /documents/{documentId} resource
        document_resource = documents_resource.add_resource("{documentId}")

        # POST /documents/{documentId}/process
        process_resource = document_resource.add_resource("process")
        process_resource.add_method(
            "POST",
            apigw.LambdaIntegration(self.document_intelligence_function),
            authorizer=self.authorizer,
            authorization_type=apigw.AuthorizationType.CUSTOM
        )

        # GET /documents/{documentId}/extractions
        extractions_resource = document_resource.add_resource("extractions")
        extractions_resource.add_method(
            "GET",
            apigw.LambdaIntegration(
                self.document_intelligence_function,
                request_templates={"application/json": '{"handler": "get_extractions"}'}
            ),
            authorizer=self.authorizer,
            authorization_type=apigw.AuthorizationType.CUSTOM
        )

        # POST /documents/search
        search_resource = documents_resource.add_resource("search")
        search_resource.add_method(
            "POST",
            apigw.LambdaIntegration(self.semantic_search_function),
            authorizer=self.authorizer,
            authorization_type=apigw.AuthorizationType.CUSTOM,
            request_validator=self._create_request_validator("SearchDocumentsValidator", validate_body=True)
        )

    def _create_report_endpoints(self) -> None:
        """Create report generation API endpoints."""

        # /reports resource
        reports_resource = self.api.root.add_resource("reports")

        # POST /reports/generate
        generate_resource = reports_resource.add_resource("generate")
        generate_resource.add_method(
            "POST",
            apigw.LambdaIntegration(self.report_generation_function),
            authorizer=self.authorizer,
            authorization_type=apigw.AuthorizationType.CUSTOM,
            request_validator=self._create_request_validator("GenerateReportValidator", validate_body=True)
        )

        # GET /reports/{reportId}
        report_resource = reports_resource.add_resource("{reportId}")
        report_resource.add_method(
            "GET",
            apigw.LambdaIntegration(
                self.report_generation_function,
                request_templates={"application/json": '{"handler": "get_report_handler"}'}
            ),
            authorizer=self.authorizer,
            authorization_type=apigw.AuthorizationType.CUSTOM
        )

        # GET /reports - List reports
        reports_resource.add_method(
            "GET",
            apigw.LambdaIntegration(
                self.report_generation_function,
                request_templates={"application/json": '{"handler": "list_reports_handler"}'}
            ),
            authorizer=self.authorizer,
            authorization_type=apigw.AuthorizationType.CUSTOM
        )

    def _create_dashboard_endpoints(self) -> None:
        """Create dashboard API endpoints."""

        # /dashboard resource
        dashboard_resource = self.api.root.add_resource("dashboard")

        # GET /dashboard/overview
        overview_resource = dashboard_resource.add_resource("overview")
        overview_resource.add_method(
            "GET",
            apigw.LambdaIntegration(self.dashboard_function),
            authorizer=self.authorizer,
            authorization_type=apigw.AuthorizationType.CUSTOM
        )

        # GET /dashboard/project/{projectId}
        project_resource = dashboard_resource.add_resource("project")
        project_id_resource = project_resource.add_resource("{projectId}")
        project_id_resource.add_method(
            "GET",
            apigw.LambdaIntegration(
                self.dashboard_function,
                request_templates={"application/json": '{"handler": "get_project_dashboard_handler"}'}
            ),
            authorizer=self.authorizer,
            authorization_type=apigw.AuthorizationType.CUSTOM
        )

        # GET /dashboard/metrics/{projectId}
        metrics_resource = dashboard_resource.add_resource("metrics")
        metrics_project_resource = metrics_resource.add_resource("{projectId}")
        metrics_project_resource.add_method(
            "GET",
            apigw.LambdaIntegration(
                self.dashboard_function,
                request_templates={"application/json": '{"handler": "get_metrics_handler"}'}
            ),
            authorizer=self.authorizer,
            authorization_type=apigw.AuthorizationType.CUSTOM
        )

    def _create_request_validator(self, validator_id: str, validate_body: bool = False, validate_params: bool = False) -> apigw.RequestValidator:
        """Create request validator for API Gateway."""

        return apigw.RequestValidator(
            self,
            validator_id,
            rest_api=self.api,
            validate_request_body=validate_body,
            validate_request_parameters=validate_params
        )

    def _create_alarms(self) -> None:
        """Create CloudWatch alarms for API Gateway monitoring."""

        # API Gateway 5XX error rate alarm (Requirement 27.4)
        api_5xx_alarm = cloudwatch.Alarm(
            self,
            "API5XXErrorAlarm",
            alarm_name="ai-sw-pm-api-5xx-errors",
            alarm_description="Alert when API 5XX error rate exceeds 5%",
            metric=self.api.metric_server_error(
                statistic="Sum",
                period=Duration.minutes(5)
            ),
            threshold=5,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )

        api_5xx_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))

        # API Gateway latency alarm (Requirement 27.5)
        api_latency_alarm = cloudwatch.Alarm(
            self,
            "APILatencyAlarm",
            alarm_name="ai-sw-pm-api-latency",
            alarm_description="Alert when API latency exceeds 2 seconds",
            metric=self.api.metric_latency(
                statistic="Average",
                period=Duration.minutes(5)
            ),
            threshold=2000,  # milliseconds
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )

        api_latency_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))

        # Lambda throttling alarm
        for function_name, function in [
            ("user-management", self.user_management_function),
            ("jira-integration", self.jira_integration_function),
            ("risk-detection", self.risk_detection_function),
            ("prediction", self.prediction_function),
            ("document-upload", self.document_upload_function),
            ("report-generation", self.report_generation_function),
            ("dashboard", self.dashboard_function)
        ]:
            throttle_alarm = cloudwatch.Alarm(
                self,
                f"{function_name.title().replace('-', '')}ThrottleAlarm",
                alarm_name=f"ai-sw-pm-{function_name}-throttles",
                alarm_description=f"Alert when {function_name} Lambda is throttled",
                metric=function.metric_throttles(
                    statistic="Sum",
                    period=Duration.minutes(5)
                ),
                threshold=1,
                evaluation_periods=1,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
            )

            throttle_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))

    def _enable_xray_tracing(self) -> None:
        """Enable X-Ray tracing for all Lambda functions (Requirement 27.6)."""

        # X-Ray tracing is already enabled via tracing=lambda_.Tracing.ACTIVE
        # in Lambda function definitions and tracing_enabled=True in API Gateway stage options
        pass
