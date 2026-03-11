"""Encryption and Secrets Management Stack.

This stack centralizes encryption key management and secrets configuration
for the AI SW Program Manager platform.

Requirements:
- 24.1: Encrypt all data at rest using AES-256
- 24.2: Encrypt all data in transit using TLS 1.2+
- 24.3: Store encryption keys in AWS KMS with automatic rotation
- 24.4: Enforce HTTPS for all API endpoints
- 24.5: Implement IAM-based access control
- 24.6: Encrypt S3 buckets using server-side encryption
- 24.7: Encrypt DynamoDB tables using AWS-managed encryption keys
"""

from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    aws_kms as kms,
    aws_secretsmanager as secretsmanager,
    aws_iam as iam,
    CfnOutput,
)
from constructs import Construct


class EncryptionStack(Stack):
    """
    Centralized encryption and secrets management stack.
    
    This stack creates:
    - KMS keys for different service categories with automatic rotation
    - Secrets Manager configuration for API credentials
    - IAM policies for encryption key access
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create KMS keys for different service categories
        self._create_kms_keys()
        
        # Create secrets for API credentials
        self._create_api_secrets()
        
        # Output key ARNs for reference
        self._create_outputs()

    def _create_kms_keys(self) -> None:
        """
        Create KMS keys with automatic rotation enabled.
        
        Validates: Requirements 24.1, 24.3
        """
        
        # Master key for database encryption (DynamoDB, RDS)
        self.database_key = kms.Key(
            self,
            "DatabaseEncryptionKey",
            description="Master encryption key for database resources (DynamoDB, RDS)",
            enable_key_rotation=True,  # Automatic annual rotation
            removal_policy=RemovalPolicy.RETAIN,
            pending_window=Duration.days(30)
        )
        
        # Add alias for easier reference
        kms.Alias(
            self,
            "DatabaseKeyAlias",
            alias_name="alias/ai-sw-pm/database",
            target_key=self.database_key
        )
        
        # Key for storage encryption (S3 buckets)
        self.storage_key = kms.Key(
            self,
            "StorageEncryptionKey",
            description="Master encryption key for storage resources (S3)",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN,
            pending_window=Duration.days(30)
        )
        
        kms.Alias(
            self,
            "StorageKeyAlias",
            alias_name="alias/ai-sw-pm/storage",
            target_key=self.storage_key
        )
        
        # Key for OpenSearch encryption
        self.opensearch_key = kms.Key(
            self,
            "OpenSearchEncryptionKey",
            description="Encryption key for OpenSearch domain",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN,
            pending_window=Duration.days(30)
        )
        
        kms.Alias(
            self,
            "OpenSearchKeyAlias",
            alias_name="alias/ai-sw-pm/opensearch",
            target_key=self.opensearch_key
        )
        
        # Key for Secrets Manager encryption
        self.secrets_key = kms.Key(
            self,
            "SecretsEncryptionKey",
            description="Encryption key for Secrets Manager secrets",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN,
            pending_window=Duration.days(30)
        )
        
        kms.Alias(
            self,
            "SecretsKeyAlias",
            alias_name="alias/ai-sw-pm/secrets",
            target_key=self.secrets_key
        )
        
        # Key for SQS queue encryption
        self.queue_key = kms.Key(
            self,
            "QueueEncryptionKey",
            description="Encryption key for SQS queues",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN,
            pending_window=Duration.days(30)
        )
        
        kms.Alias(
            self,
            "QueueKeyAlias",
            alias_name="alias/ai-sw-pm/queue",
            target_key=self.queue_key
        )

    def _create_api_secrets(self) -> None:
        """
        Create placeholder secrets for API credentials.
        
        These secrets will be populated with actual credentials during deployment.
        Automatic rotation is configured where supported by the service.
        
        Validates: Requirements 24.1, 24.3
        """
        
        # Bedrock API configuration (if using custom endpoints)
        self.bedrock_config_secret = secretsmanager.Secret(
            self,
            "BedrockConfigSecret",
            description="Amazon Bedrock API configuration",
            secret_name="ai-sw-pm/bedrock/config",
            encryption_key=self.secrets_key,
            removal_policy=RemovalPolicy.RETAIN,
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"region": "us-east-1"}',
                generate_string_key="api_key",
                exclude_punctuation=True,
                password_length=32
            )
        )
        
        # SageMaker endpoint configuration
        self.sagemaker_config_secret = secretsmanager.Secret(
            self,
            "SageMakerConfigSecret",
            description="SageMaker endpoint configuration",
            secret_name="ai-sw-pm/sagemaker/config",
            encryption_key=self.secrets_key,
            removal_policy=RemovalPolicy.RETAIN,
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"endpoint_name": "delay-prediction"}',
                generate_string_key="access_key",
                exclude_punctuation=True,
                password_length=32
            )
        )
        
        # SES SMTP credentials (for email distribution)
        self.ses_smtp_secret = secretsmanager.Secret(
            self,
            "SESSmtpSecret",
            description="Amazon SES SMTP credentials for email distribution",
            secret_name="ai-sw-pm/ses/smtp",
            encryption_key=self.secrets_key,
            removal_policy=RemovalPolicy.RETAIN,
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "AKIAIOSFODNN7EXAMPLE"}',
                generate_string_key="password",
                exclude_punctuation=True,
                password_length=40
            )
        )
        
        # Note: Jira and Azure DevOps secrets are created dynamically
        # when integrations are configured via the API
        # (see jira_integration/handler.py and azure_devops_integration/handler.py)

    def _create_outputs(self) -> None:
        """Create CloudFormation outputs for key ARNs."""
        
        CfnOutput(
            self,
            "DatabaseKeyArn",
            value=self.database_key.key_arn,
            description="ARN of the database encryption key",
            export_name="ai-sw-pm-database-key-arn"
        )
        
        CfnOutput(
            self,
            "StorageKeyArn",
            value=self.storage_key.key_arn,
            description="ARN of the storage encryption key",
            export_name="ai-sw-pm-storage-key-arn"
        )
        
        CfnOutput(
            self,
            "OpenSearchKeyArn",
            value=self.opensearch_key.key_arn,
            description="ARN of the OpenSearch encryption key",
            export_name="ai-sw-pm-opensearch-key-arn"
        )
        
        CfnOutput(
            self,
            "SecretsKeyArn",
            value=self.secrets_key.key_arn,
            description="ARN of the Secrets Manager encryption key",
            export_name="ai-sw-pm-secrets-key-arn"
        )
        
        CfnOutput(
            self,
            "QueueKeyArn",
            value=self.queue_key.key_arn,
            description="ARN of the SQS queue encryption key",
            export_name="ai-sw-pm-queue-key-arn"
        )

    def grant_decrypt_to_service(self, service_principal: str) -> None:
        """
        Grant decrypt permissions to an AWS service.
        
        Args:
            service_principal: Service principal (e.g., 'lambda.amazonaws.com')
        """
        for key in [
            self.database_key,
            self.storage_key,
            self.opensearch_key,
            self.secrets_key,
            self.queue_key
        ]:
            key.grant_decrypt(iam.ServicePrincipal(service_principal))

    def grant_encrypt_decrypt_to_role(self, role: iam.IRole) -> None:
        """
        Grant encrypt and decrypt permissions to an IAM role.
        
        Args:
            role: IAM role to grant permissions to
        """
        for key in [
            self.database_key,
            self.storage_key,
            self.opensearch_key,
            self.secrets_key,
            self.queue_key
        ]:
            key.grant_encrypt_decrypt(role)
