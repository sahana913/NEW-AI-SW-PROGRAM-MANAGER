# Infrastructure Setup

This directory contains AWS CDK infrastructure code for the AI SW Program Manager platform.

## Prerequisites

- AWS CLI configured with appropriate credentials
- Node.js 18+ installed
- Python 3.11+ installed
- AWS CDK CLI installed: `npm install -g aws-cdk`

## Project Structure

```
infrastructure/
├── app.py                  # CDK app entry point
├── cdk.json               # CDK configuration
├── stacks/                # CDK stack definitions
│   ├── database_stack.py  # DynamoDB and RDS resources
│   ├── storage_stack.py   # S3 and OpenSearch resources
│   └── monitoring_stack.py # CloudWatch and X-Ray resources
└── database/
    └── schema.sql         # PostgreSQL database schema
```

## Setup Instructions

### 1. Install Dependencies

```bash
# Install Node.js dependencies
npm install

# Install Python dependencies (from project root)
cd ..
pip install -r requirements-dev.txt
cd infrastructure
```

### 2. Bootstrap CDK (First Time Only)

```bash
cdk bootstrap aws://ACCOUNT-ID/REGION
```

### 3. Deploy Infrastructure

Deploy all stacks:

```bash
cdk deploy --all
```

Or deploy individual stacks:

```bash
cdk deploy AISWProgramManager-Database
cdk deploy AISWProgramManager-Storage
cdk deploy AISWProgramManager-Monitoring
```

### 4. Initialize Database Schema

After deploying the database stack, connect to the RDS instance and run the schema:

```bash
# Get database credentials from Secrets Manager
aws secretsmanager get-secret-value --secret-id <SECRET_ARN> --query SecretString --output text

# Connect to RDS (from a bastion host or Lambda)
psql -h <RDS_ENDPOINT> -U postgres -d ai_sw_program_manager -f database/schema.sql
```

## Resources Created

### Database Stack

- **DynamoDB Tables**:
  - `ai-sw-pm-users` - User profiles and metadata
  - `ai-sw-pm-risks` - Risk alerts
  - `ai-sw-pm-predictions` - ML predictions
  - `ai-sw-pm-documents` - Document metadata
  - `ai-sw-pm-document-extractions` - Extracted entities
  - `ai-sw-pm-reports` - Generated reports
  - `ai-sw-pm-report-schedules` - Report schedules
  - `ai-sw-pm-integrations` - External integrations

- **RDS PostgreSQL**:
  - Instance: db.t3.medium
  - Multi-AZ: Yes
  - Storage: 100GB (auto-scaling to 500GB)
  - Encryption: KMS
  - Backup retention: 7 days

### Storage Stack

- **S3 Buckets**:
  - Documents bucket (versioned, encrypted)
  - Reports bucket (versioned, encrypted)
  - Model artifacts bucket (for SageMaker)

- **OpenSearch Domain**:
  - Version: 2.11
  - Instance type: r6g.large.search
  - Data nodes: 2
  - Storage: 100GB EBS (GP3)
  - Encryption: KMS
  - VPC deployment

### Monitoring Stack

- **CloudWatch Log Groups**:
  - Lambda function logs (90-day retention)
  - API Gateway logs
  - Step Functions logs

- **CloudWatch Alarms**:
  - API error rate > 5%
  - API latency > 2 seconds
  - Lambda errors and throttles

- **CloudWatch Dashboard**:
  - API Gateway metrics
  - Lambda metrics
  - Error rates and latency

## Configuration

### Environment Variables

Set these environment variables before deployment:

```bash
export CDK_DEFAULT_ACCOUNT=<your-aws-account-id>
export CDK_DEFAULT_REGION=<your-aws-region>
```

### Custom Configuration

Modify stack parameters in `app.py` or pass context values:

```bash
cdk deploy --context environment=production
```

## Useful CDK Commands

- `cdk ls` - List all stacks
- `cdk synth` - Synthesize CloudFormation templates
- `cdk diff` - Compare deployed stack with current state
- `cdk deploy` - Deploy stacks
- `cdk destroy` - Destroy stacks
- `cdk docs` - Open CDK documentation

## Security Considerations

1. **Encryption**: All data is encrypted at rest using KMS with automatic key rotation
2. **Network**: RDS and OpenSearch are deployed in private subnets
3. **Access Control**: IAM policies follow least privilege principle
4. **Secrets**: Database credentials stored in Secrets Manager
5. **Logging**: All API calls logged to CloudTrail
6. **SSL/TLS**: All data in transit encrypted using TLS 1.2+

## Cost Optimization

- DynamoDB uses on-demand billing mode
- S3 lifecycle policies transition old data to Infrequent Access
- RDS uses burstable instances (can be upgraded for production)
- OpenSearch uses right-sized instances for workload

## Troubleshooting

### Stack Deployment Fails

Check CloudFormation events:
```bash
aws cloudformation describe-stack-events --stack-name AISWProgramManager-Database
```

### Cannot Connect to RDS

Ensure security groups allow access from Lambda functions or bastion host.

### OpenSearch Domain Creation Timeout

OpenSearch domains can take 15-30 minutes to create. Be patient.

## Next Steps

After infrastructure deployment:

1. Deploy Lambda functions (see `../src/` directories)
2. Configure API Gateway
3. Set up Cognito User Pool
4. Deploy Step Functions workflows
5. Configure EventBridge rules for scheduled tasks
