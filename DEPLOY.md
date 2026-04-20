# AI SW Program Manager - Deployment Guide

## Overview

This guide provides step-by-step instructions for deploying the AI SW Program Manager platform to AWS using AWS CDK.

## Prerequisites

### Required Software

- **Python 3.11+** - [Download](https://www.python.org/downloads/)
- **Node.js 18+** - [Download](https://nodejs.org/)
- **AWS CLI v2** - [Install Guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- **AWS CDK CLI** - Install via: `npm install -g aws-cdk`
- **Git** - [Download](https://git-scm.com/downloads/)

### AWS Account Requirements

- Active AWS account with appropriate permissions
- IAM user with Administrator access or equivalent permissions for:
  - CloudFormation
  - Lambda
  - API Gateway
  - DynamoDB
  - RDS
  - S3
  - Cognito
  - OpenSearch
  - VPC
  - IAM
  - Secrets Manager
  - CloudWatch
  - EventBridge
  - Step Functions

### Estimated Costs

- **Development Environment**: ~$50-100/month
- **Production Environment**: ~$200-500/month (varies with usage)
- Use [AWS Pricing Calculator](https://calculator.aws) for detailed estimates

---

## Deployment Steps

### Step 1: Environment Setup

#### 1.1 Clone and Navigate to Repository

```bash
cd AI-SW-Program-Manager
```

#### 1.2 Run Setup Script

**On Windows (PowerShell):**
```powershell
.\setup.ps1
```

**On Linux/macOS:**
```bash
chmod +x setup.sh
./setup.sh
```

#### 1.3 Activate Virtual Environment

**Windows:**
```powershell
.\venv\Scripts\Activate.ps1
```

**Linux/macOS:**
```bash
source venv/bin/activate
```

#### 1.4 Verify Installation

```bash
# Check Python
python --version  # Should be 3.11+

# Check Node.js
node --version    # Should be 18+

# Check AWS CLI
aws --version     # Should be 2.x

# Check CDK
cdk --version     # Should be 2.x
```

---

### Step 2: AWS Configuration

#### 2.1 Configure AWS Credentials

```bash
aws configure
```

Provide:
- **AWS Access Key ID**: Your access key
- **AWS Secret Access Key**: Your secret key
- **Default region**: `us-east-1` (or your preferred region)
- **Default output format**: `json`

#### 2.2 Verify AWS Access

```bash
aws sts get-caller-identity
```

Expected output:
```json
{
    "UserId": "AIDAXXXXXXXXXXXXXXXXX",
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:user/your-username"
}
```

#### 2.3 Set Environment Variables

**Windows (PowerShell):**
```powershell
$env:CDK_DEFAULT_ACCOUNT = (aws sts get-caller-identity --query Account --output text)
$env:CDK_DEFAULT_REGION = "us-east-1"

# Verify
echo $env:CDK_DEFAULT_ACCOUNT
echo $env:CDK_DEFAULT_REGION
```

**Linux/macOS (Bash):**
```bash
export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export CDK_DEFAULT_REGION=us-east-1

# Verify
echo $CDK_DEFAULT_ACCOUNT
echo $CDK_DEFAULT_REGION
```

---

### Step 3: CDK Bootstrap (First-Time Only)

Bootstrap CDK in your AWS account and region:

```bash
cd infrastructure
cdk bootstrap aws://$CDK_DEFAULT_ACCOUNT/$CDK_DEFAULT_REGION
```

**Expected Output:**
```
✅ Environment aws://123456789012/us-east-1 bootstrapped
```

**Note**: This only needs to be done once per account/region combination.

---

### Step 4: Review Infrastructure

#### 4.1 View Stack List

```bash
cdk list
```

**Expected Stacks:**
- `AISWProgramManager-Auth`
- `AISWProgramManager-VPCNetworkSecurity`
- `AISWProgramManager-Database`
- `AISWProgramManager-Storage`
- `AISWProgramManager-Cache`
- `AISWProgramManager-Monitoring`
- `AISWProgramManager-AuditLogging`
- `AISWProgramManager-IngestionWorkflow`
- `AISWProgramManager-APIGateway`

#### 4.2 Preview Changes

```bash
cdk diff
```

This shows what resources will be created without deploying.

---

### Step 5: Deploy Infrastructure

#### 5.1 Deploy All Stacks (Recommended)

```bash
cdk deploy --all --require-approval never
```

**Deployment Time**: 30-45 minutes (OpenSearch domain takes longest)

#### 5.2 Deploy Individual Stacks (Alternative)

Deploy in this order to respect dependencies:

```bash
# 1. Authentication
cdk deploy AISWProgramManager-Auth

# 2. VPC and Network Security
cdk deploy AISWProgramManager-VPCNetworkSecurity

# 3. Database
cdk deploy AISWProgramManager-Database

# 4. Storage
cdk deploy AISWProgramManager-Storage

# 5. Cache
cdk deploy AISWProgramManager-Cache

# 6. Monitoring
cdk deploy AISWProgramManager-Monitoring

# 7. Audit Logging
cdk deploy AISWProgramManager-AuditLogging

# 8. Ingestion Workflow
cdk deploy AISWProgramManager-IngestionWorkflow

# 9. API Gateway
cdk deploy AISWProgramManager-APIGateway
```

#### 5.3 Monitor Deployment

Watch CloudFormation console:
```bash
# Open CloudFormation in browser
aws cloudformation describe-stacks --query "Stacks[?contains(StackName, 'AISWProgramManager')].StackName"
```

Or use AWS Console: https://console.aws.amazon.com/cloudformation

---

### Step 6: Initialize Database

#### 6.1 Get RDS Endpoint

```bash
aws rds describe-db-instances \
  --query "DBInstances[?DBName=='ai_sw_program_manager'].Endpoint.Address" \
  --output text
```

#### 6.2 Get Database Credentials

```bash
# Get secret ARN from stack outputs
aws cloudformation describe-stacks \
  --stack-name AISWProgramManager-Database \
  --query "Stacks[0].Outputs[?OutputKey=='DatabaseSecretArn'].OutputValue" \
  --output text

# Retrieve credentials
aws secretsmanager get-secret-value \
  --secret-id <SECRET_ARN> \
  --query SecretString \
  --output text | jq -r '.password'
```

#### 6.3 Connect and Initialize Schema

**Option A: Using AWS Systems Manager Session Manager (Recommended)**

```bash
# Create a bastion host or use Lambda function with VPC access
# Then connect via Session Manager and run:
psql -h <RDS_ENDPOINT> -U postgres -d ai_sw_program_manager -f infrastructure/database/schema.sql
```

**Option B: Using VPN or Direct Connect**

If you have VPN/Direct Connect to your VPC:
```bash
psql -h <RDS_ENDPOINT> -U postgres -d ai_sw_program_manager -f infrastructure/database/schema.sql
```

---

### Step 7: Verify Deployment

#### 7.1 Check CloudFormation Stacks

```bash
aws cloudformation list-stacks \
  --stack-status-filter CREATE_COMPLETE \
  --query "StackSummaries[?contains(StackName, 'AISWProgramManager')].StackName"
```

#### 7.2 Verify DynamoDB Tables

```bash
aws dynamodb list-tables --query "TableNames[?contains(@, 'ai-sw-pm')]"
```

**Expected Tables:**
- `ai-sw-pm-users`
- `ai-sw-pm-integrations`
- `ai-sw-pm-risks`
- `ai-sw-pm-predictions`
- `ai-sw-pm-reports`
- `ai-sw-pm-audit-logs`

#### 7.3 Verify S3 Buckets

```bash
aws s3 ls | grep ai-sw-pm
```

**Expected Buckets:**
- `ai-sw-pm-documents-*`
- `ai-sw-pm-reports-*`
- `ai-sw-pm-audit-logs-*`

#### 7.4 Verify Lambda Functions

```bash
aws lambda list-functions \
  --query "Functions[?contains(FunctionName, 'AISWProgramManager')].FunctionName"
```

#### 7.5 Verify API Gateway

```bash
aws apigateway get-rest-apis \
  --query "items[?contains(name, 'AISWProgramManager')].{Name:name,Id:id}"
```

#### 7.6 Get API Endpoint

```bash
aws cloudformation describe-stacks \
  --stack-name AISWProgramManager-APIGateway \
  --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" \
  --output text
```

#### 7.7 Verify Cognito User Pool

```bash
aws cognito-idp list-user-pools --max-results 10 \
  --query "UserPools[?contains(Name, 'AISWProgramManager')].{Name:Name,Id:Id}"
```

---

### Step 8: Post-Deployment Configuration

#### 8.1 Create First Admin User

```bash
# Get User Pool ID
USER_POOL_ID=$(aws cloudformation describe-stacks \
  --stack-name AISWProgramManager-Auth \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
  --output text)

# Create admin user
aws cognito-idp admin-create-user \
  --user-pool-id $USER_POOL_ID \
  --username admin@example.com \
  --user-attributes Name=email,Value=admin@example.com Name=email_verified,Value=true \
  --temporary-password "TempPassword123!" \
  --message-action SUPPRESS
```

#### 8.2 Configure Cognito Domain (Optional)

```bash
aws cognito-idp create-user-pool-domain \
  --domain ai-sw-pm-<your-unique-suffix> \
  --user-pool-id $USER_POOL_ID
```

#### 8.3 Enable CloudWatch Alarms

Alarms are created automatically. Verify:
```bash
aws cloudwatch describe-alarms \
  --query "MetricAlarms[?contains(AlarmName, 'AISWProgramManager')].AlarmName"
```

#### 8.4 Configure EventBridge Rules

EventBridge rules for scheduled tasks are created automatically. Verify:
```bash
aws events list-rules \
  --query "Rules[?contains(Name, 'AISWProgramManager')].Name"
```

---

### Step 9: Test Deployment

#### 9.1 Test API Health Check

```bash
API_ENDPOINT=$(aws cloudformation describe-stacks \
  --stack-name AISWProgramManager-APIGateway \
  --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" \
  --output text)

curl $API_ENDPOINT/health
```

**Expected Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

#### 9.2 Test Authentication

```bash
# Get User Pool Client ID
CLIENT_ID=$(aws cloudformation describe-stacks \
  --stack-name AISWProgramManager-Auth \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolClientId'].OutputValue" \
  --output text)

# Authenticate (replace with your credentials)
aws cognito-idp initiate-auth \
  --auth-flow USER_PASSWORD_AUTH \
  --client-id $CLIENT_ID \
  --auth-parameters USERNAME=admin@example.com,PASSWORD=YourPassword123!
```

#### 9.3 Run Integration Tests

```bash
cd ..
pytest tests/integration -v
```

---

## Stack Details

### 1. Auth Stack
- **Resources**: Cognito User Pool, User Pool Client, Authorizer Lambda
- **Purpose**: User authentication and authorization
- **Dependencies**: None

### 2. VPC Network Security Stack
- **Resources**: VPC, Subnets, Security Groups, NAT Gateways, VPC Flow Logs
- **Purpose**: Network isolation and security
- **Dependencies**: None

### 3. Database Stack
- **Resources**: DynamoDB tables, RDS PostgreSQL, Database Proxy
- **Purpose**: Data persistence
- **Dependencies**: VPC Network Security Stack

### 4. Storage Stack
- **Resources**: S3 buckets, OpenSearch domain
- **Purpose**: Document storage and semantic search
- **Dependencies**: VPC Network Security Stack

### 5. Cache Stack
- **Resources**: ElastiCache Redis cluster
- **Purpose**: Dashboard and report caching
- **Dependencies**: VPC Network Security Stack

### 6. Monitoring Stack
- **Resources**: CloudWatch Log Groups, X-Ray, SNS Topics, CloudWatch Dashboards
- **Purpose**: Observability and alerting
- **Dependencies**: None

### 7. Audit Logging Stack
- **Resources**: CloudTrail, S3 audit bucket, Log aggregation
- **Purpose**: Compliance and audit trails
- **Dependencies**: Monitoring Stack

### 8. Ingestion Workflow Stack
- **Resources**: Step Functions, EventBridge rules, Lambda functions
- **Purpose**: Data ingestion orchestration
- **Dependencies**: Database Stack

### 9. API Gateway Stack
- **Resources**: API Gateway, Lambda functions for all services
- **Purpose**: REST API endpoints
- **Dependencies**: Auth Stack, Database Stack, Monitoring Stack

---

## Troubleshooting

### Issue: CDK Bootstrap Fails

**Error**: `Unable to resolve AWS account to use`

**Solution**:
```bash
# Verify AWS credentials
aws sts get-caller-identity

# Set environment variables explicitly
export CDK_DEFAULT_ACCOUNT=123456789012
export CDK_DEFAULT_REGION=us-east-1
```

### Issue: Stack Deployment Timeout

**Error**: `Resource creation cancelled`

**Solution**:
- OpenSearch domains take 15-30 minutes to create
- Check CloudFormation console for specific resource errors
- Increase timeout or deploy stacks individually

### Issue: RDS Connection Refused

**Error**: `Connection timed out`

**Solution**:
- RDS is in private subnet - requires VPC access
- Use bastion host or Lambda function with VPC access
- Verify security group rules allow PostgreSQL (port 5432)

### Issue: Lambda Function Errors

**Error**: `Module not found` or `Import error`

**Solution**:
```bash
# Check Lambda logs
aws logs tail /aws/lambda/AISWProgramManager-<function-name> --follow

# Verify Lambda layers are attached
aws lambda get-function --function-name <function-name>
```

### Issue: API Gateway 403 Forbidden

**Error**: `User is not authorized to access this resource`

**Solution**:
- Verify Cognito token is valid
- Check authorizer Lambda logs
- Verify user has correct role/permissions

### Issue: DynamoDB Table Not Found

**Error**: `Requested resource not found`

**Solution**:
```bash
# Verify table exists
aws dynamodb describe-table --table-name ai-sw-pm-users

# Check table name in environment variables
aws lambda get-function-configuration --function-name <function-name>
```

### Issue: OpenSearch Domain Creation Failed

**Error**: `Service linked role does not exist`

**Solution**:
```bash
# Create OpenSearch service-linked role
aws iam create-service-linked-role --aws-service-name es.amazonaws.com
```

---

## Rollback and Cleanup

### Rollback Single Stack

```bash
aws cloudformation delete-stack --stack-name AISWProgramManager-<StackName>
```

### Complete Cleanup

**Warning**: This will delete ALL resources and data!

```bash
cd infrastructure

# Delete all stacks in reverse order
cdk destroy AISWProgramManager-APIGateway
cdk destroy AISWProgramManager-IngestionWorkflow
cdk destroy AISWProgramManager-AuditLogging
cdk destroy AISWProgramManager-Monitoring
cdk destroy AISWProgramManager-Cache
cdk destroy AISWProgramManager-Storage
cdk destroy AISWProgramManager-Database
cdk destroy AISWProgramManager-VPCNetworkSecurity
cdk destroy AISWProgramManager-Auth

# Or destroy all at once
cdk destroy --all
```

### Manual Cleanup (if needed)

```bash
# Delete S3 buckets (must be empty first)
aws s3 rb s3://ai-sw-pm-documents-* --force
aws s3 rb s3://ai-sw-pm-reports-* --force
aws s3 rb s3://ai-sw-pm-audit-logs-* --force

# Delete CloudWatch log groups
aws logs describe-log-groups --query "logGroups[?contains(logGroupName, 'AISWProgramManager')].logGroupName" --output text | \
  xargs -I {} aws logs delete-log-group --log-group-name {}
```

---

## Production Deployment Checklist

- [ ] Review and adjust resource sizing (RDS, OpenSearch, Lambda memory)
- [ ] Configure custom domain for API Gateway
- [ ] Set up SSL/TLS certificates
- [ ] Configure backup retention policies
- [ ] Enable Multi-AZ for RDS and OpenSearch
- [ ] Configure CloudWatch alarms and SNS notifications
- [ ] Set up AWS WAF rules for API Gateway
- [ ] Configure VPC endpoints for AWS services
- [ ] Enable AWS Config for compliance monitoring
- [ ] Set up AWS Backup for automated backups
- [ ] Configure log retention policies
- [ ] Enable AWS GuardDuty for threat detection
- [ ] Set up AWS Systems Manager Parameter Store for configuration
- [ ] Configure cross-region replication for S3 buckets
- [ ] Enable versioning on S3 buckets
- [ ] Set up AWS Cost Explorer and budgets
- [ ] Configure AWS Organizations and SCPs (if multi-account)
- [ ] Enable AWS CloudTrail in all regions
- [ ] Set up disaster recovery procedures
- [ ] Document runbooks for common operations

---

## Next Steps

After successful deployment:

1. **Configure Integrations**: Set up Jira and Azure DevOps integrations
2. **Load Test Data**: Import sample project data
3. **Configure Monitoring**: Set up CloudWatch dashboards and alarms
4. **User Onboarding**: Create user accounts and assign roles
5. **API Documentation**: Generate and publish API documentation
6. **CI/CD Pipeline**: Set up automated deployment pipeline
7. **Security Audit**: Run security scans and penetration tests
8. **Performance Testing**: Conduct load and stress testing
9. **Backup Testing**: Verify backup and restore procedures
10. **Documentation**: Complete operational runbooks

---

## Support and Resources

- **AWS CDK Documentation**: https://docs.aws.amazon.com/cdk/
- **AWS Lambda Documentation**: https://docs.aws.amazon.com/lambda/
- **Amazon Bedrock Documentation**: https://docs.aws.amazon.com/bedrock/
- **Project Architecture**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **Setup Guide**: [SETUP_GUIDE.md](SETUP_GUIDE.md)
- **Quick Start**: [QUICK_START.md](QUICK_START.md)

---

## Deployment Summary

| Step | Description | Time | Status |
|------|-------------|------|--------|
| 1 | Environment Setup | 5-10 min | ⏳ |
| 2 | AWS Configuration | 5 min | ⏳ |
| 3 | CDK Bootstrap | 2-3 min | ⏳ |
| 4 | Review Infrastructure | 2 min | ⏳ |
| 5 | Deploy Infrastructure | 30-45 min | ⏳ |
| 6 | Initialize Database | 5 min | ⏳ |
| 7 | Verify Deployment | 5 min | ⏳ |
| 8 | Post-Deployment Config | 10 min | ⏳ |
| 9 | Test Deployment | 5 min | ⏳ |

**Total Estimated Time**: 60-90 minutes

---

**Last Updated**: 2024
**Version**: 1.0.0
