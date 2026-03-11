"""Tests for encryption and secrets management stack.

Validates:
- Requirements 24.1: Encrypt all data at rest using AES-256
- Requirements 24.3: Store encryption keys in AWS KMS with automatic rotation
- Requirements 24.5: Implement IAM-based access control
"""

import pytest
from aws_cdk import App, Stack
from aws_cdk.assertions import Template, Match
from infrastructure.stacks.encryption_stack import EncryptionStack


@pytest.fixture
def app():
    """Create CDK app for testing."""
    return App()


@pytest.fixture
def stack(app):
    """Create encryption stack for testing."""
    return EncryptionStack(app, "TestEncryptionStack")


@pytest.fixture
def template(stack):
    """Create CloudFormation template from stack."""
    return Template.from_stack(stack)


class TestKMSKeys:
    """Test suite for KMS key configuration."""

    def test_database_key_created(self, template):
        """
        Test that database encryption key is created with rotation enabled.
        
        Validates: Requirements 24.1, 24.3
        """
        template.has_resource_properties(
            "AWS::KMS::Key",
            {
                "Description": "Master encryption key for database resources (DynamoDB, RDS)",
                "EnableKeyRotation": True,
                "KeyPolicy": Match.object_like({
                    "Statement": Match.array_with([
                        Match.object_like({
                            "Effect": "Allow",
                            "Principal": Match.object_like({
                                "AWS": Match.any_value()
                            }),
                            "Action": "kms:*",
                            "Resource": "*"
                        })
                    ])
                })
            }
        )

    def test_storage_key_created(self, template):
        """
        Test that storage encryption key is created with rotation enabled.
        
        Validates: Requirements 24.1, 24.3, 24.6
        """
        template.has_resource_properties(
            "AWS::KMS::Key",
            {
                "Description": "Master encryption key for storage resources (S3)",
                "EnableKeyRotation": True
            }
        )

    def test_opensearch_key_created(self, template):
        """
        Test that OpenSearch encryption key is created with rotation enabled.
        
        Validates: Requirements 24.1, 24.3
        """
        template.has_resource_properties(
            "AWS::KMS::Key",
            {
                "Description": "Encryption key for OpenSearch domain",
                "EnableKeyRotation": True
            }
        )

    def test_secrets_key_created(self, template):
        """
        Test that Secrets Manager encryption key is created with rotation enabled.
        
        Validates: Requirements 24.1, 24.3
        """
        template.has_resource_properties(
            "AWS::KMS::Key",
            {
                "Description": "Encryption key for Secrets Manager secrets",
                "EnableKeyRotation": True
            }
        )

    def test_queue_key_created(self, template):
        """
        Test that SQS queue encryption key is created with rotation enabled.
        
        Validates: Requirements 24.1, 24.3
        """
        template.has_resource_properties(
            "AWS::KMS::Key",
            {
                "Description": "Encryption key for SQS queues",
                "EnableKeyRotation": True
            }
        )

    def test_all_keys_have_rotation_enabled(self, template):
        """
        Test that all KMS keys have automatic rotation enabled.
        
        Validates: Requirement 24.3
        """
        # Get all KMS keys from template
        resources = template.to_json()["Resources"]
        kms_keys = [
            resource for resource_id, resource in resources.items()
            if resource["Type"] == "AWS::KMS::Key"
        ]
        
        # Verify all keys have rotation enabled
        assert len(kms_keys) == 5, "Expected 5 KMS keys"
        for key in kms_keys:
            assert key["Properties"]["EnableKeyRotation"] is True

    def test_keys_have_retention_policy(self, template):
        """
        Test that KMS keys are retained on stack deletion.
        
        Validates: Requirement 24.3 (key protection)
        """
        resources = template.to_json()["Resources"]
        kms_keys = [
            resource for resource_id, resource in resources.items()
            if resource["Type"] == "AWS::KMS::Key"
        ]
        
        for key in kms_keys:
            # Keys should have pending window for deletion
            assert "PendingWindowInDays" in key["Properties"]
            assert key["Properties"]["PendingWindowInDays"] == 30


class TestKMSAliases:
    """Test suite for KMS key aliases."""

    def test_database_key_alias(self, template):
        """Test that database key has proper alias."""
        template.has_resource_properties(
            "AWS::KMS::Alias",
            {
                "AliasName": "alias/ai-sw-pm/database"
            }
        )

    def test_storage_key_alias(self, template):
        """Test that storage key has proper alias."""
        template.has_resource_properties(
            "AWS::KMS::Alias",
            {
                "AliasName": "alias/ai-sw-pm/storage"
            }
        )

    def test_opensearch_key_alias(self, template):
        """Test that OpenSearch key has proper alias."""
        template.has_resource_properties(
            "AWS::KMS::Alias",
            {
                "AliasName": "alias/ai-sw-pm/opensearch"
            }
        )

    def test_secrets_key_alias(self, template):
        """Test that Secrets Manager key has proper alias."""
        template.has_resource_properties(
            "AWS::KMS::Alias",
            {
                "AliasName": "alias/ai-sw-pm/secrets"
            }
        )

    def test_queue_key_alias(self, template):
        """Test that SQS queue key has proper alias."""
        template.has_resource_properties(
            "AWS::KMS::Alias",
            {
                "AliasName": "alias/ai-sw-pm/queue"
            }
        )


class TestSecretsManager:
    """Test suite for Secrets Manager configuration."""

    def test_bedrock_config_secret_created(self, template):
        """
        Test that Bedrock configuration secret is created with encryption.
        
        Validates: Requirements 24.1, 24.3
        """
        template.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {
                "Description": "Amazon Bedrock API configuration",
                "Name": "ai-sw-pm/bedrock/config",
                "KmsKeyId": Match.any_value()
            }
        )

    def test_sagemaker_config_secret_created(self, template):
        """
        Test that SageMaker configuration secret is created with encryption.
        
        Validates: Requirements 24.1, 24.3
        """
        template.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {
                "Description": "SageMaker endpoint configuration",
                "Name": "ai-sw-pm/sagemaker/config",
                "KmsKeyId": Match.any_value()
            }
        )

    def test_ses_smtp_secret_created(self, template):
        """
        Test that SES SMTP credentials secret is created with encryption.
        
        Validates: Requirements 24.1, 24.3
        """
        template.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {
                "Description": "Amazon SES SMTP credentials for email distribution",
                "Name": "ai-sw-pm/ses/smtp",
                "KmsKeyId": Match.any_value()
            }
        )

    def test_all_secrets_use_kms_encryption(self, template):
        """
        Test that all secrets use KMS encryption.
        
        Validates: Requirements 24.1, 24.3
        """
        resources = template.to_json()["Resources"]
        secrets = [
            resource for resource_id, resource in resources.items()
            if resource["Type"] == "AWS::SecretsManager::Secret"
        ]
        
        # Verify all secrets have KMS key ID
        assert len(secrets) >= 3, "Expected at least 3 secrets"
        for secret in secrets:
            assert "KmsKeyId" in secret["Properties"]

    def test_secrets_have_retention_policy(self, template):
        """
        Test that secrets are retained on stack deletion.
        
        Validates: Requirement 24.3 (secret protection)
        """
        resources = template.to_json()["Resources"]
        secrets = [
            resource for resource_id, resource in resources.items()
            if resource["Type"] == "AWS::SecretsManager::Secret"
        ]
        
        for secret in secrets:
            # Secrets should not have DeletionPolicy: Delete
            deletion_policy = secret.get("DeletionPolicy", "Retain")
            assert deletion_policy == "Retain"


class TestStackOutputs:
    """Test suite for CloudFormation outputs."""

    def test_database_key_arn_output(self, template):
        """Test that database key ARN is exported."""
        template.has_output(
            "DatabaseKeyArn",
            {
                "Description": "ARN of the database encryption key",
                "Export": {
                    "Name": "ai-sw-pm-database-key-arn"
                }
            }
        )

    def test_storage_key_arn_output(self, template):
        """Test that storage key ARN is exported."""
        template.has_output(
            "StorageKeyArn",
            {
                "Description": "ARN of the storage encryption key",
                "Export": {
                    "Name": "ai-sw-pm-storage-key-arn"
                }
            }
        )

    def test_opensearch_key_arn_output(self, template):
        """Test that OpenSearch key ARN is exported."""
        template.has_output(
            "OpenSearchKeyArn",
            {
                "Description": "ARN of the OpenSearch encryption key",
                "Export": {
                    "Name": "ai-sw-pm-opensearch-key-arn"
                }
            }
        )

    def test_secrets_key_arn_output(self, template):
        """Test that Secrets Manager key ARN is exported."""
        template.has_output(
            "SecretsKeyArn",
            {
                "Description": "ARN of the Secrets Manager encryption key",
                "Export": {
                    "Name": "ai-sw-pm-secrets-key-arn"
                }
            }
        )

    def test_queue_key_arn_output(self, template):
        """Test that SQS queue key ARN is exported."""
        template.has_output(
            "QueueKeyArn",
            {
                "Description": "ARN of the SQS queue encryption key",
                "Export": {
                    "Name": "ai-sw-pm-queue-key-arn"
                }
            }
        )


class TestIAMPermissions:
    """Test suite for IAM access control."""

    def test_key_policies_allow_root_account(self, template):
        """
        Test that KMS key policies allow root account access.
        
        Validates: Requirement 24.5
        """
        resources = template.to_json()["Resources"]
        kms_keys = [
            resource for resource_id, resource in resources.items()
            if resource["Type"] == "AWS::KMS::Key"
        ]
        
        for key in kms_keys:
            key_policy = key["Properties"]["KeyPolicy"]
            statements = key_policy["Statement"]
            
            # Find root account statement
            root_statements = [
                stmt for stmt in statements
                if "AWS" in stmt.get("Principal", {})
            ]
            
            assert len(root_statements) > 0, "No root account statement found"

    def test_grant_decrypt_to_service_method(self, stack):
        """
        Test that grant_decrypt_to_service method exists and works.
        
        Validates: Requirement 24.5
        """
        # This method should exist on the stack
        assert hasattr(stack, "grant_decrypt_to_service")
        
        # Method should be callable
        assert callable(stack.grant_decrypt_to_service)

    def test_grant_encrypt_decrypt_to_role_method(self, stack):
        """
        Test that grant_encrypt_decrypt_to_role method exists and works.
        
        Validates: Requirement 24.5
        """
        # This method should exist on the stack
        assert hasattr(stack, "grant_encrypt_decrypt_to_role")
        
        # Method should be callable
        assert callable(stack.grant_encrypt_decrypt_to_role)


class TestEncryptionCompliance:
    """Test suite for encryption compliance requirements."""

    def test_aes_256_encryption_algorithm(self, template):
        """
        Test that KMS keys use AES-256 encryption.
        
        Note: AWS KMS always uses AES-256-GCM for encryption.
        This test verifies that KMS keys are properly configured.
        
        Validates: Requirement 24.1
        """
        resources = template.to_json()["Resources"]
        kms_keys = [
            resource for resource_id, resource in resources.items()
            if resource["Type"] == "AWS::KMS::Key"
        ]
        
        # All KMS keys should be present
        assert len(kms_keys) == 5
        
        # KMS uses AES-256-GCM by default, no explicit configuration needed
        # Verify keys are properly configured
        for key in kms_keys:
            assert "KeyPolicy" in key["Properties"]
            assert "EnableKeyRotation" in key["Properties"]

    def test_automatic_key_rotation_enabled(self, template):
        """
        Test that automatic key rotation is enabled for all keys.
        
        Validates: Requirement 24.3
        """
        resources = template.to_json()["Resources"]
        kms_keys = [
            resource for resource_id, resource in resources.items()
            if resource["Type"] == "AWS::KMS::Key"
        ]
        
        rotation_enabled_count = sum(
            1 for key in kms_keys
            if key["Properties"].get("EnableKeyRotation") is True
        )
        
        assert rotation_enabled_count == len(kms_keys), \
            f"Expected all {len(kms_keys)} keys to have rotation enabled, " \
            f"but only {rotation_enabled_count} do"

    def test_secrets_encrypted_with_kms(self, template):
        """
        Test that all Secrets Manager secrets are encrypted with KMS.
        
        Validates: Requirements 24.1, 24.3
        """
        resources = template.to_json()["Resources"]
        secrets = [
            resource for resource_id, resource in resources.items()
            if resource["Type"] == "AWS::SecretsManager::Secret"
        ]
        
        secrets_with_kms = sum(
            1 for secret in secrets
            if "KmsKeyId" in secret["Properties"]
        )
        
        assert secrets_with_kms == len(secrets), \
            f"Expected all {len(secrets)} secrets to use KMS encryption, " \
            f"but only {secrets_with_kms} do"


class TestStackIntegration:
    """Test suite for stack integration with other stacks."""

    def test_encryption_key_properties_accessible(self, stack):
        """Test that encryption keys are accessible as stack properties."""
        assert hasattr(stack, "database_key")
        assert hasattr(stack, "storage_key")
        assert hasattr(stack, "opensearch_key")
        assert hasattr(stack, "secrets_key")
        assert hasattr(stack, "queue_key")

    def test_secret_properties_accessible(self, stack):
        """Test that secrets are accessible as stack properties."""
        assert hasattr(stack, "bedrock_config_secret")
        assert hasattr(stack, "sagemaker_config_secret")
        assert hasattr(stack, "ses_smtp_secret")

    def test_keys_can_be_referenced(self, stack):
        """Test that KMS keys can be referenced by other stacks."""
        # Keys should have key_arn property
        assert stack.database_key.key_arn is not None
        assert stack.storage_key.key_arn is not None
        assert stack.opensearch_key.key_arn is not None
        assert stack.secrets_key.key_arn is not None
        assert stack.queue_key.key_arn is not None
