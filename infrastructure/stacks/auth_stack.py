"""Authentication stack - AWS Cognito User Pool."""

from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    aws_cognito as cognito,
    aws_lambda as lambda_,
    aws_iam as iam,
)
from constructs import Construct
import os
from ..lambda_optimization_config import MEMORY_CONFIG


class AuthStack(Stack):
    """Stack for authentication resources."""

    def __init__(self, scope: Construct, construct_id: str, lambda_layers=None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.lambda_layers = lambda_layers or {}

        # Create Cognito User Pool
        self.user_pool = cognito.UserPool(
            self,
            "UserPool",
            user_pool_name="ai-sw-pm-user-pool",
            # Sign-in configuration
            sign_in_aliases=cognito.SignInAliases(
                email=True,
                username=False
            ),
            # Self sign-up disabled - users created by admin only
            self_sign_up_enabled=False,
            # Password policy
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
                temp_password_validity=Duration.days(7)
            ),
            # MFA configuration
            mfa=cognito.Mfa.OPTIONAL,
            mfa_second_factor=cognito.MfaSecondFactor(
                sms=True,
                otp=True
            ),
            # Account recovery
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            # Email configuration
            email=cognito.UserPoolEmail.with_cognito(),
            # Standard attributes
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(
                    required=True,
                    mutable=True
                ),
                given_name=cognito.StandardAttribute(
                    required=True,
                    mutable=True
                ),
                family_name=cognito.StandardAttribute(
                    required=True,
                    mutable=True
                )
            ),
            # Custom attributes for tenant_id and role
            custom_attributes={
                "tenant_id": cognito.StringAttribute(
                    min_len=1,
                    max_len=256,
                    mutable=False  # Tenant ID cannot be changed after creation
                ),
                "role": cognito.StringAttribute(
                    min_len=1,
                    max_len=50,
                    mutable=True  # Role can be updated
                )
            },
            # Advanced security
            advanced_security_mode=cognito.AdvancedSecurityMode.ENFORCED,
            # Removal policy
            removal_policy=RemovalPolicy.RETAIN
        )

        # Create User Pool Client for web application
        self.user_pool_client = self.user_pool.add_client(
            "WebAppClient",
            user_pool_client_name="ai-sw-pm-web-client",
            # OAuth flows
            auth_flows=cognito.AuthFlow(
                user_password=True,
                user_srp=True,
                custom=False,
                admin_user_password=True
            ),
            # Token validity
            access_token_validity=Duration.hours(1),
            id_token_validity=Duration.hours(1),
            refresh_token_validity=Duration.days(30),
            # Prevent user existence errors
            prevent_user_existence_errors=True,
            # Read and write attributes
            read_attributes=cognito.ClientAttributes()
                .with_standard_attributes(
                    email=True,
                    given_name=True,
                    family_name=True
                )
                .with_custom_attributes("tenant_id", "role"),
            write_attributes=cognito.ClientAttributes()
                .with_standard_attributes(
                    email=True,
                    given_name=True,
                    family_name=True
                )
        )

        # Create User Pool Domain for hosted UI (optional)
        self.user_pool_domain = self.user_pool.add_domain(
            "UserPoolDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix="ai-sw-pm"
            )
        )

        # Create Lambda Authorizer with optimized settings
        authorizer_config = self._get_lambda_config("authorizer")
        self.authorizer_function = lambda_.Function(
            self,
            "AuthorizerFunction",
            function_name="ai-sw-pm-authorizer",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/authorizer")
            ),
            environment={
                "USER_POOL_ID": self.user_pool.user_pool_id
            },
            timeout=authorizer_config["timeout"],
            memory_size=authorizer_config["memory_size"],
            description="Lambda Authorizer for API Gateway - validates JWT tokens from Cognito",
            layers=self._get_lambda_layers("authorizer")
        )

        # Grant the authorizer function permissions to describe the user pool
        self.authorizer_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "cognito-idp:GetUser",
                    "cognito-idp:DescribeUserPool"
                ],
                resources=[self.user_pool.user_pool_arn]
            )
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
            "memory_size": 256,
            "timeout": Duration.seconds(10)
        }

    def _get_lambda_layers(self, function_type: str) -> list:
        """
        Get appropriate Lambda layers for a function type.
        
        Validates: Requirement 23.2 (reduce package size)
        """
        layers = []
        
        # Authorizer gets common layer
        if "common" in self.lambda_layers:
            layers.append(self.lambda_layers["common"])
        
        return layers
