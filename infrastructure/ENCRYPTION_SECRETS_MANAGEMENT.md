# Encryption and Secrets Management Implementation

## Overview

This document describes the encryption and secrets management implementation for the AI SW Program Manager platform, ensuring all data is encrypted at rest and in transit, with secure credential storage and automatic key rotation.

## Requirements Addressed

- **24.1**: Encrypt all data at rest using AES-256 encryption
- **24.2**: Encrypt all data in transit using TLS 1.2 or higher
- **24.3**: Store encryption keys in AWS KMS with automatic key rotation
- **24.4**: Enforce HTTPS for all API endpoints
- **24.5**: Implement IAM-based access control for all AWS resources
- **24.6**: Encrypt S3 buckets using server-side encryption
- **24.7**: Encrypt DynamoDB tables using AWS-managed encryption keys

## Architecture

### KMS Key Structure

The platform uses a multi-key architecture with separate KMS keys for different service categories:

1. **Database Encryption Key** (`alias/ai-sw-pm/database`)
   - Encrypts DynamoDB tables
   - Encrypts RDS PostgreSQL database
   - Automatic annual rotation enabled

2. **Storage Encryption Key** (`alias/ai-sw-pm/storage`)
   - Encrypts S3 buckets (documents, reports, model artifacts)
   - Automatic annual rotation enabled

3. **OpenSearch Encryption Key** (`alias/ai-sw-pm/opensearch`)
   - Encrypts OpenSearch domain at rest
   - Encrypts node-to-node communication
   - Automatic annual rotation enabled

4. **Secrets Encryption Key** (`alias/ai-sw-pm/secrets`)
   - Encrypts AWS Secrets Manager secrets
   - Protects API credentials and integration tokens
   - Automatic annual rotation enabled

5. **Queue Encryption Key** (`alias/ai-sw-pm/queue`)
   - Encrypts SQS queues
   - Protects messages in transit and at rest
   - Automatic annual rotation enabled

### Key Rotation

All KMS keys have automatic rotation enabled:
- **Rotation Frequency**: Annual (365 days)
- **Rotation Method**: AWS-managed automatic rotation
- **Backward Compatibility**: Old key versions remain available for decryption
- **Zero Downtime**: Rotation occurs transparently without service interruption

## Data Store Encryption

### DynamoDB Tables

All DynamoDB tables use customer-managed KMS encryption:

```python
dynamodb.Table(
    self,
    "TableName",
    encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
    encryption_key=encryption_key,
    point_in_time_recovery=True
)
```

**Encrypted Tables**:
- `ai-sw-pm-users`
- `ai-sw-pm-risks`
- `ai-sw-pm-predictions`
- `ai-sw-pm-documents`
- `ai-sw-pm-document-extractions`
- `ai-sw-pm-reports`
- `ai-sw-pm-report-schedules`
- `ai-sw-pm-integrations`
- `ai-sw-pm-email-delivery-logs`
- `ai-sw-pm-email-preferences`

**Encryption Details**:
- Algorithm: AES-256
- Key Management: Customer-managed KMS key
- Point-in-Time Recovery: Enabled (encrypted backups)
- Streams: Encrypted when enabled

### RDS PostgreSQL

RDS instance uses storage encryption with KMS:

```python
rds.DatabaseInstance(
    self,
    "PostgreSQLInstance",
    storage_encrypted=True,
    storage_encryption_key=encryption_key,
    multi_az=True,
    backup_retention=Duration.days(7)
)
```

**Encryption Details**:
- Algorithm: AES-256
- Key Management: Customer-managed KMS key
- Automated Backups: Encrypted with same key
- Snapshots: Encrypted with same key
- Multi-AZ: Both primary and standby encrypted

### S3 Buckets

All S3 buckets use KMS encryption:

```python
s3.Bucket(
    self,
    "BucketName",
    encryption=s3.BucketEncryption.KMS,
    encryption_key=encryption_key,
    enforce_ssl=True,
    versioned=True
)
```

**Encrypted Buckets**:
- Documents bucket (uploaded files)
- Reports bucket (generated reports)
- Model artifacts bucket (SageMaker models)

**Encryption Details**:
- Algorithm: AES-256
- Key Management: Customer-managed KMS key
- Versioning: All versions encrypted
- SSL/TLS: Enforced for all operations
- Bucket Policy: Denies unencrypted uploads

### OpenSearch Domain

OpenSearch domain uses encryption at rest and in transit:

```python
opensearch.Domain(
    self,
    "OpenSearchDomain",
    encryption_at_rest=opensearch.EncryptionAtRestOptions(
        enabled=True,
        kms_key=encryption_key
    ),
    node_to_node_encryption=True,
    enforce_https=True,
    tls_security_policy=opensearch.TLSSecurityPolicy.TLS_1_2
)
```

**Encryption Details**:
- At Rest: AES-256 with KMS
- Node-to-Node: TLS 1.2
- Client Communication: HTTPS only
- Index Data: Encrypted
- Automated Snapshots: Encrypted

### SQS Queues

SQS queues use KMS encryption:

```python
sqs.Queue(
    self,
    "QueueName",
    encryption=sqs.QueueEncryption.KMS,
    encryption_master_key=encryption_key
)
```

**Encryption Details**:
- Algorithm: AES-256
- Key Management: Customer-managed KMS key
- Messages: Encrypted at rest
- Data Key Reuse: 5 minutes (default)

## Secrets Management

### AWS Secrets Manager

API credentials and integration tokens are stored in AWS Secrets Manager:

#### Managed Secrets

1. **Bedrock Configuration** (`ai-sw-pm/bedrock/config`)
   - Amazon Bedrock API configuration
   - Region and endpoint settings
   - Encrypted with secrets KMS key

2. **SageMaker Configuration** (`ai-sw-pm/sagemaker/config`)
   - SageMaker endpoint names
   - Model version information
   - Encrypted with secrets KMS key

3. **SES SMTP Credentials** (`ai-sw-pm/ses/smtp`)
   - SMTP username and password
   - Used for email distribution
   - Encrypted with secrets KMS key

4. **RDS Credentials** (`ai-sw-pm/rds/credentials`)
   - PostgreSQL username and password
   - Auto-generated during deployment
   - Encrypted with secrets KMS key

#### Dynamic Secrets

Created via API when integrations are configured:

1. **Jira Integration Secrets** (`ai-sw-pm/jira/{tenant_id}/{integration_id}`)
   - OAuth tokens or API tokens
   - Jira instance URL
   - Project keys
   - Created by: `jira_integration/handler.py`

2. **Azure DevOps Secrets** (`ai-sw-pm/azure-devops/{tenant_id}/{integration_id}`)
   - Personal Access Tokens (PAT)
   - Organization URL
   - Project names
   - Created by: `azure_devops_integration/handler.py`

### Secret Rotation

#### Automatic Rotation

Secrets Manager supports automatic rotation for:
- RDS database credentials (30-day rotation)
- Custom rotation Lambda functions can be added for other secrets

#### Manual Rotation

For API tokens (Jira, Azure DevOps):
- Users must update tokens via the API when they expire
- Platform validates token expiration and alerts users
- Rotation is triggered by re-configuring the integration

### Secret Access Control

IAM policies restrict secret access:

```python
iam.PolicyStatement(
    effect=iam.Effect.ALLOW,
    actions=[
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
    ],
    resources=[
        f"arn:aws:secretsmanager:{region}:{account}:secret:ai-sw-pm/*"
    ],
    conditions={
        "StringEquals": {
            "aws:RequestedRegion": region
        }
    }
)
```

## Data in Transit Encryption

### API Gateway

All API endpoints enforce HTTPS:

```python
apigateway.RestApi(
    self,
    "API",
    endpoint_configuration=apigateway.EndpointConfiguration(
        types=[apigateway.EndpointType.REGIONAL]
    ),
    disable_execute_api_endpoint=False,
    # HTTPS is enforced by default
)
```

**TLS Configuration**:
- Minimum TLS Version: 1.2
- Cipher Suites: AWS-managed secure ciphers
- Certificate: AWS-managed certificate
- HTTP: Automatically redirected to HTTPS

### Lambda to AWS Services

All Lambda function communication with AWS services uses TLS:
- DynamoDB: HTTPS endpoints
- RDS: SSL/TLS connections
- S3: HTTPS endpoints
- Secrets Manager: HTTPS endpoints
- SageMaker: HTTPS endpoints
- Bedrock: HTTPS endpoints

### External API Calls

All external API calls (Jira, Azure DevOps) use HTTPS:
- TLS 1.2 or higher required
- Certificate validation enabled
- Timeout and retry logic implemented

## IAM Access Control

### Principle of Least Privilege

Each Lambda function has a dedicated IAM role with minimal permissions:

1. **Service-Specific Permissions**
   - Only access to required DynamoDB tables
   - Only access to required S3 buckets
   - Only access to required secrets

2. **KMS Key Permissions**
   - Decrypt only (no encrypt for read-only operations)
   - Scoped to specific key aliases

3. **Cross-Service Permissions**
   - Explicit allow for required service integrations
   - Deny by default for all other services

### Example IAM Policy

```python
iam.PolicyStatement(
    effect=iam.Effect.ALLOW,
    actions=[
        "kms:Decrypt",
        "kms:DescribeKey"
    ],
    resources=[database_key.key_arn],
    conditions={
        "StringEquals": {
            "kms:ViaService": f"dynamodb.{region}.amazonaws.com"
        }
    }
)
```

## Compliance and Auditing

### CloudTrail Logging

All KMS key usage is logged to CloudTrail:
- Key creation and deletion
- Key rotation events
- Encrypt and decrypt operations
- Key policy changes

### CloudWatch Metrics

KMS key metrics are monitored:
- Number of decrypt operations
- Number of encrypt operations
- Key age
- Rotation status

### Audit Requirements

The implementation satisfies:
- **SOC 2 Type II**: Encryption at rest and in transit
- **HIPAA**: KMS key management and rotation
- **PCI DSS**: Strong cryptography and key management
- **GDPR**: Data protection and encryption

## Deployment

### Prerequisites

1. AWS account with KMS permissions
2. AWS CDK installed and configured
3. Appropriate IAM permissions for stack deployment

### Deployment Steps

1. **Deploy Encryption Stack**
   ```bash
   cd infrastructure
   cdk deploy EncryptionStack
   ```

2. **Deploy Database Stack** (uses encryption keys)
   ```bash
   cdk deploy DatabaseStack
   ```

3. **Deploy Storage Stack** (uses encryption keys)
   ```bash
   cdk deploy StorageStack
   ```

4. **Verify Encryption**
   ```bash
   # Check KMS keys
   aws kms list-keys
   aws kms describe-key --key-id alias/ai-sw-pm/database
   
   # Check rotation status
   aws kms get-key-rotation-status --key-id alias/ai-sw-pm/database
   ```

### Post-Deployment Configuration

1. **Populate Secrets**
   ```bash
   # Update SES SMTP credentials
   aws secretsmanager update-secret \
     --secret-id ai-sw-pm/ses/smtp \
     --secret-string '{"username":"AKIAIOSFODNN7EXAMPLE","password":"actual-password"}'
   ```

2. **Configure Secret Rotation** (for RDS)
   ```bash
   aws secretsmanager rotate-secret \
     --secret-id ai-sw-pm/rds/credentials \
     --rotation-lambda-arn <rotation-lambda-arn> \
     --rotation-rules AutomaticallyAfterDays=30
   ```

## Monitoring and Alerts

### CloudWatch Alarms

Alarms are configured for:
- KMS key deletion attempts
- Unusual encryption/decryption patterns
- Failed secret access attempts
- Key rotation failures

### Security Hub

Integration with AWS Security Hub for:
- Encryption compliance checks
- Key rotation status
- Secret access patterns
- IAM policy violations

## Disaster Recovery

### Key Backup

KMS keys are:
- Retained on stack deletion (RemovalPolicy.RETAIN)
- Backed up automatically by AWS
- Recoverable within 30-day pending deletion window

### Secret Recovery

Secrets Manager secrets:
- Retained on stack deletion
- Recoverable within 7-30 day recovery window
- Versioned for rollback capability

### Encryption Key Loss

In case of key loss:
1. Contact AWS Support immediately
2. Use backup key versions if available
3. Restore from encrypted backups using old key versions
4. Create new key and re-encrypt data if necessary

## Best Practices

1. **Never Store Credentials in Code**
   - Always use Secrets Manager
   - Never commit secrets to version control
   - Use environment variables for secret ARNs only

2. **Rotate Secrets Regularly**
   - Enable automatic rotation where possible
   - Manual rotation at least every 90 days
   - Immediate rotation on suspected compromise

3. **Monitor Key Usage**
   - Review CloudTrail logs regularly
   - Set up alerts for unusual patterns
   - Audit key access permissions quarterly

4. **Test Encryption**
   - Verify encryption at rest for all data stores
   - Test TLS connections to all endpoints
   - Validate secret access in all environments

5. **Document Key Purposes**
   - Maintain key inventory
   - Document which services use which keys
   - Update documentation on key changes

## Troubleshooting

### Common Issues

1. **Access Denied Errors**
   - Check IAM role has KMS decrypt permissions
   - Verify key policy allows the service principal
   - Ensure ViaService condition matches the service

2. **Secret Not Found**
   - Verify secret name matches exactly
   - Check secret is in the correct region
   - Ensure IAM role has GetSecretValue permission

3. **Encryption Failures**
   - Check KMS key is enabled
   - Verify key rotation hasn't caused issues
   - Ensure sufficient KMS API quota

### Support

For encryption and secrets management issues:
1. Check CloudWatch Logs for error details
2. Review CloudTrail for KMS operations
3. Contact AWS Support for KMS-specific issues
4. Refer to AWS KMS and Secrets Manager documentation

## References

- [AWS KMS Developer Guide](https://docs.aws.amazon.com/kms/latest/developerguide/)
- [AWS Secrets Manager User Guide](https://docs.aws.amazon.com/secretsmanager/latest/userguide/)
- [AWS Encryption SDK](https://docs.aws.amazon.com/encryption-sdk/latest/developer-guide/)
- [AWS Security Best Practices](https://docs.aws.amazon.com/security/latest/userguide/)
