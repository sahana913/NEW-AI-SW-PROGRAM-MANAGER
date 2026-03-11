# AI SW Program Manager - Setup Guide

## Quick Start

This guide will help you set up the AI SW Program Manager development environment and deploy the infrastructure.

## Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.11+**: [Download Python](https://www.python.org/downloads/)
- **Node.js 18+**: [Download Node.js](https://nodejs.org/)
- **AWS CLI**: [Install AWS CLI](https://aws.amazon.com/cli/)
- **AWS CDK CLI**: Install via npm: `npm install -g aws-cdk`
- **Git**: [Download Git](https://git-scm.com/downloads/)

## Step 1: Clone and Setup

### On Linux/macOS:

```bash
# Navigate to project directory
cd AI-SW-Program-Manager

# Run setup script
chmod +x setup.sh
./setup.sh

# Activate virtual environment
source venv/bin/activate
```

### On Windows (PowerShell):

```powershell
# Navigate to project directory
cd AI-SW-Program-Manager

# Run setup script
.\setup.ps1

# Activate virtual environment
.\venv\Scripts\Activate.ps1
```

## Step 2: Configure AWS Credentials

```bash
# Configure AWS CLI with your credentials
aws configure

# Verify configuration
aws sts get-caller-identity
```

Set environment variables:

```bash
# Linux/macOS
export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export CDK_DEFAULT_REGION=us-east-1

# Windows PowerShell
$env:CDK_DEFAULT_ACCOUNT = (aws sts get-caller-identity --query Account --output text)
$env:CDK_DEFAULT_REGION = "us-east-1"
```

## Step 3: Bootstrap CDK (First Time Only)

```bash
cd infrastructure
cdk bootstrap aws://$CDK_DEFAULT_ACCOUNT/$CDK_DEFAULT_REGION
```

## Step 4: Deploy Infrastructure

### Deploy All Stacks:

```bash
cdk deploy --all
```

### Or Deploy Individual Stacks:

```bash
# Deploy database resources
cdk deploy AISWProgramManager-Database

# Deploy storage resources
cdk deploy AISWProgramManager-Storage

# Deploy monitoring resources
cdk deploy AISWProgramManager-Monitoring
```

## Step 5: Initialize Database Schema

After the database stack is deployed:

1. Get the RDS endpoint and credentials:

```bash
# Get database endpoint
aws rds describe-db-instances \
  --query "DBInstances[?DBName=='ai_sw_program_manager'].Endpoint.Address" \
  --output text

# Get database credentials from Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id <SECRET_ARN_FROM_STACK_OUTPUT> \
  --query SecretString \
  --output text
```

2. Connect to the database and run the schema:

```bash
# From a bastion host or Lambda function with VPC access
psql -h <RDS_ENDPOINT> -U postgres -d ai_sw_program_manager -f infrastructure/database/schema.sql
```

## Step 6: Verify Deployment

Check that all resources were created:

```bash
# List CloudFormation stacks
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE

# List DynamoDB tables
aws dynamodb list-tables

# List S3 buckets
aws s3 ls | grep ai-sw-pm

# Check RDS instances
aws rds describe-db-instances --query "DBInstances[].DBInstanceIdentifier"
```

## Project Structure

```
AI-SW-Program-Manager/
├── infrastructure/          # AWS CDK infrastructure code
│   ├── app.py              # CDK app entry point
│   ├── stacks/             # Stack definitions
│   │   ├── database_stack.py
│   │   ├── storage_stack.py
│   │   └── monitoring_stack.py
│   └── database/
│       └── schema.sql      # PostgreSQL schema
├── src/                    # Lambda function source code
│   ├── shared/             # Shared utilities
│   │   ├── logger.py       # Logging utilities
│   │   ├── errors.py       # Custom exceptions
│   │   ├── decorators.py   # Function decorators
│   │   ├── validators.py   # Input validation
│   │   └── constants.py    # Application constants
│   ├── auth/               # Authentication service
│   ├── user_management/    # User management service
│   ├── data_ingestion/     # Data ingestion service
│   ├── risk_detection/     # Risk detection service
│   ├── prediction/         # Prediction service
│   ├── document_intel/     # Document intelligence service
│   ├── report_generation/  # Report generation service
│   └── dashboard/          # Dashboard service
├── tests/                  # Test files
│   ├── unit/              # Unit tests
│   ├── integration/       # Integration tests
│   └── property/          # Property-based tests
├── requirements.txt        # Python dependencies
├── requirements-dev.txt    # Development dependencies
├── pytest.ini             # Pytest configuration
├── README.md              # Project overview
├── ARCHITECTURE.md        # Architecture documentation
└── SETUP_GUIDE.md         # This file
```

## Development Workflow

### Running Tests

```bash
# Run all tests
pytest

# Run unit tests only
pytest tests/unit -m unit

# Run property-based tests
pytest tests/property -m property

# Run with coverage
pytest --cov=src --cov-report=html
```

### Code Quality

```bash
# Format code with black
black src/ tests/

# Lint with flake8
flake8 src/ tests/

# Type checking with mypy
mypy src/

# Lint with pylint
pylint src/
```

### Local Development

Each service can be developed and tested locally:

```bash
# Example: Test a Lambda function locally
python -m src.auth.handler
```

## Infrastructure Management

### View Changes Before Deployment

```bash
cd infrastructure
cdk diff
```

### Update Infrastructure

```bash
# After making changes to CDK code
cdk deploy --all
```

### Destroy Infrastructure

```bash
# WARNING: This will delete all resources
cdk destroy --all
```

## Troubleshooting

### Issue: CDK Bootstrap Fails

**Solution**: Ensure AWS credentials are configured correctly and you have sufficient permissions.

```bash
aws sts get-caller-identity
```

### Issue: RDS Connection Timeout

**Solution**: Ensure you're connecting from within the VPC or through a bastion host. RDS is in a private subnet.

### Issue: Lambda Function Errors

**Solution**: Check CloudWatch Logs:

```bash
aws logs tail /aws/lambda/ai-sw-pm-<service-name> --follow
```

### Issue: DynamoDB Table Not Found

**Solution**: Verify the table was created:

```bash
aws dynamodb describe-table --table-name ai-sw-pm-users
```

### Issue: OpenSearch Domain Creation Timeout

**Solution**: OpenSearch domains can take 15-30 minutes to create. Check status:

```bash
aws opensearch describe-domain --domain-name <domain-name>
```

## Next Steps

After completing the infrastructure setup:

1. **Implement Lambda Functions**: Start with Task 2 (Authentication Service)
2. **Configure Cognito**: Set up user pools and identity providers
3. **Deploy API Gateway**: Create REST API endpoints
4. **Set Up CI/CD**: Configure automated deployment pipeline
5. **Configure Monitoring**: Set up CloudWatch dashboards and alarms
6. **Load Test Data**: Import sample project data for testing

## Resources

- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)
- [AWS Lambda Documentation](https://docs.aws.amazon.com/lambda/)
- [Amazon Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- [Project Requirements](.kiro/specs/ai-sw-program-manager/requirements.md)
- [Project Design](.kiro/specs/ai-sw-program-manager/design.md)
- [Implementation Tasks](.kiro/specs/ai-sw-program-manager/tasks.md)

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review CloudWatch Logs for error details
3. Consult the architecture documentation
4. Review the design document for implementation details

## Security Notes

- Never commit AWS credentials to version control
- Use AWS Secrets Manager for sensitive data
- Enable MFA for AWS accounts
- Follow principle of least privilege for IAM roles
- Regularly rotate credentials and keys
- Enable CloudTrail for audit logging
