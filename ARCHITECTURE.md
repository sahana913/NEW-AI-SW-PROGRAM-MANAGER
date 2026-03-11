# AI SW Program Manager - Architecture Overview

## System Architecture

The AI SW Program Manager is built on AWS serverless architecture, providing a scalable, secure, and cost-effective solution for AI-powered program management.

### High-Level Components

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Layer                             │
│                    (React SPA via CloudFront)                    │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API Gateway Layer                           │
│              (REST API + Lambda Authorizer)                      │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Application Services Layer                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │     Auth     │  │     User     │  │     Data     │         │
│  │   Service    │  │  Management  │  │  Ingestion   │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │     Risk     │  │  Prediction  │  │   Document   │         │
│  │  Detection   │  │   Service    │  │ Intelligence │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│  ┌──────────────┐  ┌──────────────┐                            │
│  │    Report    │  │  Dashboard   │                            │
│  │  Generation  │  │   Service    │                            │
│  └──────────────┘  └──────────────┘                            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Orchestration Layer                           │
│     Step Functions │ EventBridge │ SQS Queues                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      AI/ML Services Layer                        │
│         Amazon Bedrock │ SageMaker Endpoints                    │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Data Layer                                │
│  DynamoDB │ RDS PostgreSQL │ S3 │ OpenSearch                    │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Data Ingestion Flow

```
External API (Jira/Azure DevOps)
    │
    ▼
EventBridge Scheduled Rule
    │
    ▼
Data Ingestion Lambda
    │
    ├─► Fetch data from API
    ├─► Validate schema
    ├─► Transform to internal format
    │
    ▼
Step Functions Workflow
    │
    ├─► Store in RDS PostgreSQL
    ├─► Update metadata in DynamoDB
    │
    ▼
Trigger Downstream Analysis
    │
    ├─► Risk Detection Lambda
    ├─► Prediction Lambda
    └─► Health Score Calculation
```

### 2. Risk Detection Flow

```
Project Data Update
    │
    ▼
Risk Detection Lambda
    │
    ├─► Query historical data from RDS
    ├─► Calculate velocity trends
    ├─► Detect backlog growth
    ├─► Identify milestone slippage
    │
    ▼
Amazon Bedrock (Claude)
    │
    └─► Generate AI explanations
    │
    ▼
Store Risk Alerts in DynamoDB
    │
    ▼
EventBridge Event
    │
    └─► Notification Service
```

### 3. Document Intelligence Flow

```
User Upload Document
    │
    ▼
Upload Lambda (Pre-signed S3 URL)
    │
    ▼
S3 Bucket (Document Storage)
    │
    ▼
S3 Event Trigger
    │
    ▼
Document Processing Lambda
    │
    ├─► AWS Textract (Extract text)
    ├─► Amazon Bedrock (Extract entities)
    ├─► Bedrock Titan (Generate embeddings)
    │
    ▼
Store Results
    │
    ├─► Extractions → DynamoDB
    └─► Embeddings → OpenSearch
    │
    ▼
Present to User for Confirmation
```

### 4. Report Generation Flow

```
Scheduled/Manual Trigger
    │
    ▼
Report Generation Lambda
    │
    ├─► Query project data (RDS + DynamoDB)
    ├─► Calculate metrics
    ├─► Generate charts
    │
    ▼
Amazon Bedrock (Claude)
    │
    └─► Generate narrative summaries
    │
    ▼
Render HTML Report
    │
    ▼
PDF Conversion Lambda
    │
    └─► Store PDF in S3
    │
    ▼
Email Distribution Lambda (SES)
    │
    └─► Send to recipients
```

## Security Architecture

### Authentication & Authorization

```
User Login Request
    │
    ▼
AWS Cognito User Pool
    │
    ├─► Validate credentials
    ├─► Issue JWT tokens
    └─► Store tenant_id in custom attributes
    │
    ▼
API Gateway Request
    │
    ▼
Lambda Authorizer
    │
    ├─► Validate JWT signature
    ├─► Extract tenant_id and role
    └─► Return authorization context
    │
    ▼
Lambda Function
    │
    └─► Enforce tenant isolation
```

### Data Encryption

- **At Rest**: All data encrypted using AWS KMS with automatic key rotation
  - DynamoDB: Customer-managed KMS keys
  - RDS: KMS encryption
  - S3: KMS encryption
  - OpenSearch: KMS encryption

- **In Transit**: All data encrypted using TLS 1.2+
  - API Gateway: HTTPS only
  - RDS: SSL connections
  - OpenSearch: HTTPS only

### Network Security

```
┌─────────────────────────────────────────────────────────────┐
│                        Public Subnet                         │
│                    (NAT Gateway, ALB)                        │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                      Private Subnet                          │
│              (Lambda Functions, OpenSearch)                  │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                      Isolated Subnet                         │
│                    (RDS PostgreSQL)                          │
└─────────────────────────────────────────────────────────────┘
```

## Scalability & Performance

### Auto-Scaling Components

1. **Lambda Functions**: Automatic scaling based on concurrent requests
2. **DynamoDB**: On-demand capacity mode (auto-scales)
3. **RDS**: Read replicas for read-heavy workloads
4. **OpenSearch**: Multi-AZ deployment with data node scaling

### Caching Strategy

```
Request → ElastiCache Redis (5-min TTL)
              │
              ├─► Cache Hit → Return cached data
              │
              └─► Cache Miss
                      │
                      ▼
                  Query Database
                      │
                      ▼
                  Update Cache
                      │
                      ▼
                  Return data
```

### Performance Targets

- API Response Time: < 2 seconds (95th percentile)
- Dashboard Load Time: < 3 seconds
- Report Generation: < 10 seconds (up to 20 pages)
- Document Search: < 2 seconds (up to 10,000 documents)

## Monitoring & Observability

### Logging Hierarchy

```
Application Logs
    │
    ├─► CloudWatch Logs (90-day retention)
    │   ├─► Error logs (severity: ERROR, CRITICAL)
    │   ├─► API request logs
    │   └─► Audit logs
    │
    ├─► CloudTrail (1-year retention)
    │   └─► All AWS API calls
    │
    └─► X-Ray Traces
        └─► Distributed request tracing
```

### Metrics & Alarms

- **API Gateway**: Request count, error rate, latency
- **Lambda**: Invocations, errors, duration, throttles
- **DynamoDB**: Read/write capacity, throttles
- **RDS**: CPU, memory, connections, replication lag
- **OpenSearch**: Cluster health, search latency

### Alerting Thresholds

- API error rate > 5%
- API latency > 2 seconds
- Lambda error rate > 5%
- RDS CPU > 80%
- OpenSearch cluster status: Yellow or Red

## Disaster Recovery

### Backup Strategy

- **DynamoDB**: Point-in-time recovery enabled
- **RDS**: Automated daily backups (7-day retention)
- **S3**: Versioning enabled
- **OpenSearch**: Automated snapshots (daily)

### Recovery Objectives

- **RTO (Recovery Time Objective)**: 4 hours
- **RPO (Recovery Point Objective)**: 1 hour

### Multi-Region Considerations

For production deployment, consider:
- CloudFront for global content delivery
- Route 53 for DNS failover
- Cross-region RDS read replicas
- S3 cross-region replication

## Cost Optimization

### Cost Breakdown (Estimated Monthly)

- Lambda: $200-500 (based on invocations)
- DynamoDB: $100-300 (on-demand pricing)
- RDS: $150-400 (db.t3.medium)
- OpenSearch: $300-600 (r6g.large.search x2)
- S3: $50-150 (storage + requests)
- Data Transfer: $50-200
- **Total**: ~$850-2,150/month

### Cost Optimization Strategies

1. Use Lambda provisioned concurrency only for critical functions
2. Implement S3 lifecycle policies (transition to IA after 30 days)
3. Use RDS reserved instances for production
4. Optimize DynamoDB queries to reduce read capacity
5. Implement request caching to reduce Lambda invocations

## Deployment Strategy

### CI/CD Pipeline

```
Code Commit
    │
    ▼
GitHub Actions / CodePipeline
    │
    ├─► Run unit tests
    ├─► Run property-based tests
    ├─► Run integration tests
    ├─► Security scanning
    │
    ▼
CDK Synth
    │
    ▼
Deploy to Staging
    │
    ├─► Smoke tests
    └─► Integration tests
    │
    ▼
Manual Approval
    │
    ▼
Deploy to Production
    │
    └─► Blue/Green deployment
```

### Environment Strategy

- **Development**: Single-region, minimal resources
- **Staging**: Production-like, single-region
- **Production**: Multi-AZ, enhanced monitoring, backups

## Future Enhancements

1. **Multi-Region Deployment**: Active-active across regions
2. **Real-Time Updates**: WebSocket API for live dashboard updates
3. **Mobile App**: Native iOS/Android applications
4. **Advanced Analytics**: Custom ML models for more predictions
5. **Integration Marketplace**: Plugin system for additional integrations
6. **Collaborative Features**: Team chat, comments, annotations
