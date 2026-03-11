# AI SW Program Manager

An AI-powered software program management copilot platform built on AWS serverless architecture.

## Project Structure

```
.
├── infrastructure/          # AWS CDK infrastructure code
│   ├── stacks/             # CDK stack definitions
│   └── constructs/         # Reusable CDK constructs
├── src/                    # Lambda function source code
│   ├── auth/              # Authentication and authorization
│   ├── user_management/   # User management service
│   ├── data_ingestion/    # Data ingestion from external APIs
│   ├── risk_detection/    # Risk detection service
│   ├── prediction/        # ML prediction service
│   ├── document_intel/    # Document intelligence service
│   ├── report_generation/ # Report generation service
│   ├── dashboard/         # Dashboard API service
│   └── shared/            # Shared utilities and libraries
├── tests/                 # Test files
│   ├── unit/             # Unit tests
│   ├── integration/      # Integration tests
│   └── property/         # Property-based tests
└── requirements.txt       # Python dependencies
```

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+ (for AWS CDK)
- AWS CLI configured with appropriate credentials

### Installation

1. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

3. Install CDK dependencies:
```bash
cd infrastructure
npm install
```

### Deployment

```bash
cd infrastructure
cdk deploy --all
```

## Development

### Running Tests

```bash
# Unit tests
pytest tests/unit

# Property-based tests
pytest tests/property

# Integration tests
pytest tests/integration
```

### Local Development

See individual service READMEs in `src/` directories for local development instructions.

## Architecture

This platform uses AWS serverless architecture with the following key components:

- **API Gateway**: REST API endpoints
- **Lambda**: Serverless compute for all services
- **Cognito**: User authentication and authorization
- **DynamoDB**: NoSQL database for metadata
- **RDS PostgreSQL**: Relational database for project data
- **S3**: Document and report storage
- **OpenSearch**: Vector search for semantic document queries
- **Bedrock**: AI/ML for text generation and extraction
- **SageMaker**: Custom ML models for predictions
- **EventBridge**: Event routing and scheduling
- **Step Functions**: Workflow orchestration

## License

Proprietary - All rights reserved
