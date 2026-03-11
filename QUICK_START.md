# Quick Start Guide - AI SW Program Manager

## ✅ What's Already Done

Your development environment is now set up with:
- ✅ Python 3.13.5 installed
- ✅ Node.js v22.14.0 installed
- ✅ Virtual environment created (`venv/`)
- ✅ Python dependencies installed
- ✅ CDK dependencies installed (in `infrastructure/`)
- ✅ AWS CDK CLI installed globally (v2.1108.0)

## 🎯 What You Can Do Now

### 1. Run Tests Locally (No AWS Required)

```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Run unit tests
pytest tests/unit -v

# Run specific test file
pytest tests/test_authorizer.py -v

# Run with coverage
pytest --cov=src --cov-report=html
```

### 2. Code Quality Checks

```powershell
# Activate virtual environment first
.\venv\Scripts\Activate.ps1

# Format code
black src/ tests/

# Lint code
flake8 src/ tests/

# Type checking
mypy src/

# Full lint
pylint src/
```

### 3. View Test Coverage Report

After running tests with coverage, open:
```
htmlcov/index.html
```

## 🚀 To Deploy to AWS (Requires AWS Setup)

### Prerequisites

1. **Install AWS CLI**
   - Download from: https://aws.amazon.com/cli/
   - Or use: `winget install Amazon.AWSCLI`

2. **Configure AWS Credentials**
   ```powershell
   aws configure
   ```
   You'll need:
   - AWS Access Key ID
   - AWS Secret Access Key
   - Default region (e.g., us-east-1)
   - Output format (json)

3. **Set Environment Variables**
   ```powershell
   $env:CDK_DEFAULT_ACCOUNT = (aws sts get-caller-identity --query Account --output text)
   $env:CDK_DEFAULT_REGION = "us-east-1"
   ```

### Deploy Infrastructure

```powershell
# Navigate to infrastructure directory
cd infrastructure

# Bootstrap CDK (first time only)
cdk bootstrap aws://$env:CDK_DEFAULT_ACCOUNT/$env:CDK_DEFAULT_REGION

# View what will be deployed
cdk diff

# Deploy all stacks
cdk deploy --all

# Or deploy specific stacks
cdk deploy AISWProgramManager-Database
cdk deploy AISWProgramManager-Storage
cdk deploy AISWProgramManager-Monitoring
```

## 📁 Project Structure

```
AI-SW-Program-Manager/
├── src/                    # Lambda function source code
│   ├── authorizer/        # Authentication
│   ├── user_management/   # User management
│   ├── jira_integration/  # Jira integration
│   ├── azure_devops_integration/  # Azure DevOps
│   ├── risk_detection/    # Risk detection
│   ├── prediction/        # ML predictions
│   ├── document_intelligence/  # Document processing
│   ├── report_generation/ # Report generation
│   ├── dashboard/         # Dashboard API
│   └── shared/            # Shared utilities
├── infrastructure/        # AWS CDK infrastructure
│   ├── stacks/           # CDK stack definitions
│   └── database/         # Database schemas
├── tests/                # Test files
│   ├── unit/            # Unit tests
│   ├── integration/     # Integration tests
│   └── property/        # Property-based tests
└── venv/                # Python virtual environment
```

## 🔧 Development Workflow

### 1. Make Code Changes
Edit files in `src/` directory

### 2. Run Tests
```powershell
.\venv\Scripts\Activate.ps1
pytest tests/unit -v
```

### 3. Check Code Quality
```powershell
black src/
flake8 src/
```

### 4. Deploy Changes (if AWS configured)
```powershell
cd infrastructure
cdk deploy --all
```

## 📊 Available Services

The platform includes these services:
- **Authentication** - Cognito-based auth with JWT
- **User Management** - User profiles and permissions
- **Data Ingestion** - Jira and Azure DevOps integration
- **Risk Detection** - AI-powered risk analysis
- **Predictions** - ML-based workload predictions
- **Document Intelligence** - Extract data from SOWs/SLAs
- **Report Generation** - Automated report creation
- **Dashboard** - Real-time project metrics
- **Audit Logging** - Comprehensive audit trails
- **Security Monitoring** - Security violation detection

## 🐛 Troubleshooting

### Virtual Environment Not Activated
```powershell
.\venv\Scripts\Activate.ps1
```

### Module Not Found Errors
```powershell
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### CDK Command Not Found
```powershell
npm install -g aws-cdk
```

### AWS Credentials Not Configured
```powershell
aws configure
```

### Tests Taking Too Long
Run specific test files instead of all tests:
```powershell
pytest tests/test_authorizer.py -v
```

## 📚 Additional Resources

- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)
- [AWS Lambda Documentation](https://docs.aws.amazon.com/lambda/)
- [Project Architecture](ARCHITECTURE.md)
- [Setup Guide](SETUP_GUIDE.md)
- [Requirements](.kiro/specs/ai-sw-program-manager/requirements.md)
- [Design](.kiro/specs/ai-sw-program-manager/design.md)
- [Tasks](.kiro/specs/ai-sw-program-manager/tasks.md)

## 🎉 Next Steps

1. **Without AWS**: Run unit tests and develop Lambda functions locally
2. **With AWS**: Install AWS CLI, configure credentials, and deploy infrastructure
3. **Review**: Check the spec files in `.kiro/specs/ai-sw-program-manager/`

## 💡 Tips

- Use `pytest -k "test_name"` to run specific tests
- Use `pytest -m unit` to run only unit tests
- Use `pytest --lf` to run only last failed tests
- Use `cdk diff` before deploying to see changes
- Use `cdk destroy` to tear down infrastructure (careful!)

---

**Current Status**: ✅ Development environment ready!
**Next**: Run tests or configure AWS for deployment
