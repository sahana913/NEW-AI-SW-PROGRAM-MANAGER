# IAM Policies Implementation

## Overview

This document describes the least privilege IAM policies implementation for the AI SW Program Manager platform. Each Lambda function has a dedicated IAM role with only the minimum permissions required to perform its specific tasks.

**Validates: Requirement 24.5** - THE Platform SHALL implement IAM-based access control for all AWS resources

## IAM Access Analyzer

An IAM Access Analyzer has been enabled at the account level to continuously monitor IAM policies and identify potential security issues:

- **Analyzer Name**: `ai-sw-pm-access-analyzer`
- **Type**: Account-level analyzer
- **Purpose**: Identifies resources shared with external entities and validates least privilege principles

The Access Analyzer automatically:
- Detects overly permissive policies
- Identifies unused access
- Validates resource-based policies
- Generates findings for security review

## Least Privilege Principles Applied

### 1. Function-Specific Roles

Each Lambda function has its own dedicated IAM role, ensuring:
- No shared permissions between unrelated functions
- Clear audit trail of which function performed which action
- Easier security reviews and compliance validation
- Reduced blast radius in case of compromise

### 2. Resource-Level Permissions

Where AWS services support it, permissions are scoped to specific resources:
- DynamoDB: Specific table ARNs and indexes
- S3: Specific bucket and prefix patterns
- Secrets Manager: Specific secret paths
- RDS: Specific cluster ARNs
- SageMaker: Specific endpoint ARNs

### 3. Action-Level Restrictions

Only the minimum required actions are granted:
- Read-only functions get only `Get`, `Query`, `Scan` permissions
- Write functions get `Put`, `Update` in addition to read
- No wildcard (`*`) actions except where service doesn't support resource-level permissions

### 4. Condition-Based Restrictions

Additional security through IAM conditions:
- Region restrictions to prevent cross-region access
- Namespace restrictions for CloudWatch metrics
- Recovery window requirements for secret deletion
- Email address restrictions for SES sending

## IAM Roles by Function

### 1. Authorizer Role (`ai-sw-pm-authorizer-role`)

**Purpose**: Validate JWT tokens from Cognito

**Permissions**:
- `cognito-idp:GetUser` - Retrieve user details for token validation
- `cognito-idp:DescribeUserPool` - Get user pool configuration

**Resources**: Cognito User Pools in the account

**Justification**: Authorizer only needs to read user information, not modify it.

---

### 2. User Management Role (`ai-sw-pm-user-management-role`)

**Purpose**: Create and manage user accounts

**Permissions**:
- `cognito-idp:AdminCreateUser` - Create new users
- `cognito-idp:AdminDeleteUser` - Remove users
- `cognito-idp:AdminUpdateUserAttributes` - Update user attributes
- `cognito-idp:ListUsers` - List users for a tenant
- `dynamodb:GetItem`, `PutItem`, `UpdateItem`, `Query`, `Scan` - Manage user metadata

**Resources**:
- Cognito User Pools
- DynamoDB `ai-sw-pm-users` table and indexes

**Justification**: User management requires full CRUD on user records but only in Cognito and Users table.

---

### 3. Jira Integration Role (`ai-sw-pm-jira-integration-role`)

**Purpose**: Configure Jira integration and store credentials

**Permissions**:
- `dynamodb:GetItem`, `PutItem`, `UpdateItem`, `Query` - Manage integration configuration
- `secretsmanager:CreateSecret`, `GetSecretValue`, `UpdateSecret`, `TagResource` - Store Jira credentials
- `secretsmanager:DeleteSecret` - Remove credentials (with 7-day recovery window)

**Resources**:
- DynamoDB `ai-sw-pm-integrations` table
- Secrets Manager secrets under `ai-sw-pm/jira/*` path

**Justification**: Integration setup requires credential storage but scoped to Jira-specific secrets only.

---

### 4. Azure DevOps Role (`ai-sw-pm-azure-devops-role`)

**Purpose**: Configure Azure DevOps integration and store credentials

**Permissions**:
- `dynamodb:GetItem`, `PutItem`, `UpdateItem`, `Query` - Manage integration configuration
- `secretsmanager:CreateSecret`, `GetSecretValue`, `UpdateSecret`, `TagResource` - Store Azure DevOps credentials
- `secretsmanager:DeleteSecret` - Remove credentials (with 7-day recovery window)

**Resources**:
- DynamoDB `ai-sw-pm-integrations` table
- Secrets Manager secrets under `ai-sw-pm/azure-devops/*` path

**Justification**: Similar to Jira but scoped to Azure DevOps-specific secrets.

---

### 5. Data Ingestion Role (`ai-sw-pm-data-ingestion-role`)

**Purpose**: Fetch data from external APIs and store in database

**Permissions**:
- `dynamodb:GetItem`, `PutItem`, `UpdateItem`, `Query`, `BatchWriteItem` - Store ingested data
- `secretsmanager:GetSecretValue`, `DescribeSecret` - Read integration credentials
- `rds-data:ExecuteStatement`, `BatchExecuteStatement` - Write to RDS database
- `sqs:SendMessage`, `ReceiveMessage`, `DeleteMessage`, `GetQueueAttributes` - Queue management
- `states:StartExecution` - Trigger Step Functions workflow

**Resources**:
- DynamoDB `ai-sw-pm-integrations` and `ai-sw-pm-projects` tables
- Secrets Manager secrets under `ai-sw-pm/*`
- RDS cluster `ai-sw-pm-*`
- SQS queue `ai-sw-pm-ingestion-queue`
- Step Functions state machine `ai-sw-pm-ingestion-workflow`

**Justification**: Ingestion requires reading credentials, writing data, and orchestrating workflow.

---

### 6. Risk Detection Role (`ai-sw-pm-risk-detection-role`)

**Purpose**: Analyze project data and detect risks

**Permissions**:
- `dynamodb:GetItem`, `PutItem`, `UpdateItem`, `Query`, `Scan` - Manage risk records
- `rds-data:ExecuteStatement` - Read project metrics from RDS
- `bedrock:InvokeModel` - Generate AI explanations
- `events:PutEvents` - Publish risk events

**Resources**:
- DynamoDB `ai-sw-pm-risks` table
- RDS cluster `ai-sw-pm-*` (read-only)
- Bedrock models: Claude and Titan
- EventBridge default event bus

**Justification**: Risk detection needs to read project data, write risks, and generate AI explanations.

---

### 7. Prediction Role (`ai-sw-pm-prediction-role`)

**Purpose**: Generate ML-based predictions

**Permissions**:
- `dynamodb:GetItem`, `PutItem`, `UpdateItem`, `Query`, `Scan` - Manage predictions
- `rds-data:ExecuteStatement` - Read historical data
- `sagemaker:InvokeEndpoint` - Invoke ML models

**Resources**:
- DynamoDB `ai-sw-pm-predictions` and `ai-sw-pm-risks` tables
- RDS cluster `ai-sw-pm-*` (read-only)
- SageMaker endpoints `ai-sw-pm-*`

**Justification**: Predictions require reading historical data and invoking ML models.

---

### 8. Document Upload Role (`ai-sw-pm-document-upload-role`)

**Purpose**: Generate pre-signed URLs for document uploads

**Permissions**:
- `s3:PutObject`, `PutObjectAcl`, `GetObject` - Upload and retrieve documents
- `dynamodb:PutItem`, `GetItem`, `UpdateItem` - Track document metadata

**Resources**:
- S3 bucket `ai-sw-pm-documents-{account}`
- DynamoDB `ai-sw-pm-documents` table

**Justification**: Document upload only needs S3 write access and metadata tracking.

---

### 9. Document Intelligence Role (`ai-sw-pm-document-intelligence-role`)

**Purpose**: Extract information from documents using AI

**Permissions**:
- `s3:GetObject` - Read uploaded documents
- `textract:AnalyzeDocument`, `DetectDocumentText` - Extract text
- `bedrock:InvokeModel` - Extract entities with AI
- `dynamodb:PutItem`, `GetItem`, `UpdateItem`, `Query` - Store extractions
- `sqs:SendMessage`, `ReceiveMessage`, `DeleteMessage` - Process document queue

**Resources**:
- S3 bucket `ai-sw-pm-documents-{account}` (read-only)
- Textract (no resource-level permissions)
- Bedrock models: Claude and Titan
- DynamoDB `ai-sw-pm-document-extractions` table
- SQS queue `ai-sw-pm-document-processing-queue`

**Justification**: Document processing requires reading documents, AI analysis, and storing results.

---

### 10. Semantic Search Role (`ai-sw-pm-semantic-search-role`)

**Purpose**: Search documents using vector embeddings

**Permissions**:
- `es:ESHttpGet`, `ESHttpPost` - Query OpenSearch
- `bedrock:InvokeModel` - Generate query embeddings

**Resources**:
- OpenSearch domain `ai-sw-pm-documents`
- Bedrock Titan embedding models

**Justification**: Search only needs to query OpenSearch and generate embeddings.

---

### 11. Report Generation Role (`ai-sw-pm-report-generation-role`)

**Purpose**: Generate automated reports

**Permissions**:
- `dynamodb:GetItem`, `PutItem`, `UpdateItem`, `Query` - Manage reports
- `dynamodb:GetItem`, `Query`, `Scan` - Read risks and predictions (read-only)
- `rds-data:ExecuteStatement` - Read project data
- `bedrock:InvokeModel` - Generate narratives
- `s3:PutObject`, `GetObject` - Store reports
- `ses:SendEmail`, `SendRawEmail` - Distribute reports

**Resources**:
- DynamoDB `ai-sw-pm-reports`, `ai-sw-pm-risks`, `ai-sw-pm-predictions` tables
- RDS cluster `ai-sw-pm-*` (read-only)
- Bedrock Claude models
- S3 bucket `ai-sw-pm-reports-{account}`
- SES identities (with from-address restriction)

**Justification**: Report generation needs to read all data sources and distribute via email.

---

### 12. Dashboard Role (`ai-sw-pm-dashboard-role`)

**Purpose**: Aggregate and serve dashboard data

**Permissions**:
- `dynamodb:GetItem`, `Query`, `Scan` - Read dashboard data (read-only)
- `rds-data:ExecuteStatement` - Read project metrics
- `elasticache:DescribeCacheClusters`, `DescribeReplicationGroups` - Access cache

**Resources**:
- DynamoDB `ai-sw-pm-risks`, `ai-sw-pm-predictions`, `ai-sw-pm-projects` tables (read-only)
- RDS cluster `ai-sw-pm-*` (read-only)
- ElastiCache clusters `ai-sw-pm-*`

**Justification**: Dashboard is read-only and uses caching for performance.

---

### 13. Database Maintenance Role (`ai-sw-pm-database-maintenance-role`)

**Purpose**: Perform database maintenance tasks

**Permissions**:
- `rds-data:ExecuteStatement`, `BatchExecuteStatement` - Execute maintenance queries
- `secretsmanager:GetSecretValue` - Read database credentials
- `cloudwatch:PutMetricData` - Publish maintenance metrics

**Resources**:
- RDS cluster `ai-sw-pm-*`
- Secrets Manager secrets under `ai-sw-pm/rds/*`
- CloudWatch namespace `AI-SW-PM/Database`

**Justification**: Maintenance requires database write access and metric publishing.

## Security Best Practices

### 1. No Wildcard Resources

Avoid `"Resource": "*"` except where AWS services don't support resource-level permissions:
- Textract (service limitation)
- Some Bedrock operations (service limitation)

### 2. Separate Secrets Paths

Credentials are organized by integration type:
- `ai-sw-pm/jira/*` - Jira credentials
- `ai-sw-pm/azure-devops/*` - Azure DevOps credentials
- `ai-sw-pm/rds/*` - Database credentials

This prevents one integration from accessing another's credentials.

### 3. Read-Only Where Possible

Functions that only need to read data (dashboard, search) have no write permissions.

### 4. Tenant Isolation

While IAM policies don't enforce tenant isolation directly, they work with application-level tenant filtering to ensure:
- S3 uses tenant-specific prefixes
- DynamoDB queries filter by tenant ID
- OpenSearch uses tenant-specific indexes

### 5. Audit and Monitoring

All IAM role usage is logged via:
- CloudTrail for API calls
- CloudWatch Logs for Lambda execution
- IAM Access Analyzer for policy validation

## Compliance and Validation

### Automated Validation

IAM Access Analyzer continuously validates:
- Unused permissions
- Overly broad policies
- External access to resources
- Cross-account access

### Manual Review Process

1. **Quarterly Reviews**: Review all IAM policies for continued necessity
2. **Change Approval**: All IAM policy changes require security team approval
3. **Least Privilege Validation**: Verify each permission is actually used
4. **Access Analyzer Findings**: Address all findings within 30 days

### Compliance Mapping

This IAM implementation supports:
- **SOC 2**: Logical access controls
- **ISO 27001**: Access control policy
- **GDPR**: Data protection by design
- **HIPAA**: Access control requirements (if applicable)

## Troubleshooting

### Access Denied Errors

If a Lambda function receives "Access Denied" errors:

1. Check CloudTrail logs for the specific denied action
2. Verify the resource ARN matches the policy
3. Check for condition restrictions (region, namespace, etc.)
4. Ensure the role is attached to the Lambda function

### IAM Access Analyzer Findings

When Access Analyzer generates findings:

1. Review the finding details in the AWS Console
2. Determine if the access is intentional
3. If unintentional, update the policy to remove the access
4. If intentional, document the justification and archive the finding

## Future Enhancements

1. **Permission Boundaries**: Add permission boundaries for additional security layer
2. **Service Control Policies**: Implement SCPs for organization-wide restrictions
3. **Automated Remediation**: Auto-remediate Access Analyzer findings where possible
4. **Just-In-Time Access**: Implement temporary elevated permissions for maintenance
5. **Cross-Account Roles**: Support multi-account deployments with cross-account roles
