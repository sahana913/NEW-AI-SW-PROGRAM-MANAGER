# Data Ingestion Workflow

## Overview

The Data Ingestion Workflow orchestrates the automated fetching, validation, storage, and analysis triggering of project data from external systems (Jira and Azure DevOps).

## Architecture

### SQS Queue Buffering

The workflow uses SQS queues for job buffering to handle rate limits and provide reliable message processing:

```
┌─────────────────────────────────────────┐
│      Ingestion Job Sources              │
│  ┌──────────────┐  ┌─────────────────┐ │
│  │ Scheduled    │  │ Manual API      │ │
│  │ EventBridge  │  │ Trigger         │ │
│  └──────────────┘  └─────────────────┘ │
└─────────────────────────────────────────┘
                  │
                  ▼
         ┌────────────────┐
         │  SQS Queue     │
         │  (Buffering)   │
         └────────────────┘
                  │
                  ▼
         ┌────────────────┐
         │ Queue          │
         │ Processor      │
         │ Lambda         │
         └────────────────┘
                  │
                  ▼
         ┌────────────────┐
         │ Step Functions │
         │ State Machine  │
         └────────────────┘
                  │
                  ▼
         ┌────────────────┐
         │ Dead Letter    │
         │ Queue (DLQ)    │
         └────────────────┘
```

**Queue Configuration:**
- **Visibility Timeout**: 35 minutes (longer than state machine timeout)
- **Message Retention**: 4 days
- **Max Receive Count**: 3 (retry up to 3 times before moving to DLQ)
- **DLQ Retention**: 14 days
- **Encryption**: KMS-managed encryption
- **Long Polling**: 20 seconds

**Validates**: Requirement 3.8

### Step Functions State Machine

The workflow is implemented as an AWS Step Functions state machine with the following states:

```
┌─────────────────────────────────────────┐
│         Parallel Fetch                  │
│  ┌──────────────┐  ┌─────────────────┐ │
│  │ Fetch Jira   │  │ Fetch Azure     │ │
│  │ Data         │  │ DevOps Data     │ │
│  └──────────────┘  └─────────────────┘ │
└─────────────────────────────────────────┘
                  │
                  ▼
         ┌────────────────┐
         │ Validate Data  │
         └────────────────┘
                  │
                  ▼
         ┌────────────────┐
         │  Store Data    │
         └────────────────┘
                  │
                  ▼
         ┌────────────────┐
         │ Trigger        │
         │ Analysis       │
         └────────────────┘
                  │
                  ▼
         ┌────────────────┐
         │    Success     │
         └────────────────┘
```

### Workflow Steps

#### 1. Parallel Fetch
- **Fetch Jira Data**: Invokes Lambda to fetch project data from Jira API
- **Fetch Azure DevOps Data**: Invokes Lambda to fetch project data from Azure DevOps API
- Both fetches run in parallel for efficiency
- **Validates**: Requirements 3.2, 4.2

#### 2. Validate Data
- Validates fetched data against expected schema
- Rejects invalid data with error logging
- **Validates**: Requirements 3.5, 3.6, 4.5, 4.6

#### 3. Store Data
- Stores validated data in RDS PostgreSQL
- Adds timestamp and source metadata
- **Validates**: Requirements 3.7, 4.7

#### 4. Trigger Analysis
- Publishes events to EventBridge to trigger:
  - Risk detection analysis
  - Delay probability predictions
  - Workload imbalance predictions

#### 5. Success/Failure
- Success state indicates workflow completed successfully
- Failure state captures errors for monitoring

## Triggers

### 1. Scheduled Execution (EventBridge Rule)

The workflow runs automatically on a schedule:
- **Default Schedule**: Daily at 2:00 AM UTC
- **Rule Name**: `ai-sw-pm-daily-ingestion`
- **Configurable**: Schedule can be modified via EventBridge console or CDK

**Validates**: Requirements 3.3, 4.3

### 2. Manual Trigger (API Gateway Endpoint)

Users can trigger the workflow manually via API:
- **Endpoint**: `POST /sync`
- **Authentication**: Requires valid JWT token
- **Authorization**: Available to all authenticated users
- **Response**: Returns sync job ID and status

**Validates**: Requirements 3.4, 4.4

Example request:
```bash
curl -X POST https://{api-id}.execute-api.{region}.amazonaws.com/prod/sync \
  -H "Authorization: Bearer {jwt-token}" \
  -H "Content-Type: application/json"
```

Example response:
```json
{
  "syncJobId": "manual-tenant123-1234567890",
  "status": "QUEUED",
  "message": "Data ingestion workflow triggered successfully"
}
```

## Lambda Functions

### 1. Scheduled Trigger
- **Function Name**: `ai-sw-pm-scheduled-ingestion-trigger`
- **Handler**: `index.lambda_handler`
- **Timeout**: 30 seconds
- **Memory**: 256 MB
- **Purpose**: Send scheduled ingestion jobs to SQS queue

### 2. Queue Processor
- **Function Name**: `ai-sw-pm-queue-processor`
- **Handler**: `index.lambda_handler`
- **Timeout**: 5 minutes
- **Memory**: 256 MB
- **Purpose**: Process messages from SQS queue and trigger state machine
- **Concurrency**: Limited to 10 concurrent executions
- **Batch Size**: 5 messages per invocation

### 3. Fetch Jira Data
- **Function Name**: `ai-sw-pm-fetch-jira-data`
- **Handler**: `data_fetcher.fetch_jira_data`
- **Timeout**: 5 minutes
- **Memory**: 512 MB
- **Purpose**: Fetch project data from Jira API

### 2. Fetch Azure DevOps Data
- **Function Name**: `ai-sw-pm-fetch-azure-devops-data`
- **Handler**: `data_fetcher.fetch_azure_devops_data`
- **Timeout**: 5 minutes
- **Memory**: 512 MB
- **Purpose**: Fetch project data from Azure DevOps API

### 3. Validate Data
- **Function Name**: `ai-sw-pm-validate-data`
- **Handler**: `handler.lambda_handler`
- **Timeout**: 2 minutes
- **Memory**: 256 MB
- **Purpose**: Validate fetched data against schema

### 4. Store Data
- **Function Name**: `ai-sw-pm-store-data`
- **Handler**: `handler.lambda_handler`
- **Timeout**: 5 minutes
- **Memory**: 512 MB
- **Purpose**: Store validated data in RDS and DynamoDB

### 5. Trigger Analysis
- **Function Name**: `ai-sw-pm-trigger-analysis`
- **Handler**: `handler.lambda_handler`
- **Timeout**: 2 minutes
- **Memory**: 256 MB
- **Purpose**: Trigger downstream analysis workflows

### 6. Manual Trigger
- **Function Name**: `ai-sw-pm-manual-ingestion-trigger`
- **Handler**: `index.lambda_handler`
- **Timeout**: 30 seconds
- **Memory**: 256 MB
- **Purpose**: API endpoint for manual workflow trigger

## Error Handling

### Retry Logic
- All Lambda invocations have automatic retry on service exceptions
- Exponential backoff for API rate limits (implemented in fetch functions)

### Error Capture
- Each state has error catching configured
- Errors are captured in `$.error` path
- Workflow transitions to Failure state on errors

### Monitoring
- CloudWatch Logs: `/aws/stepfunctions/ai-sw-pm-ingestion-workflow`
- X-Ray tracing enabled for distributed tracing
- Log level: ALL (includes execution data)

## Deployment

### Prerequisites
- AWS CDK installed
- Python 3.11 runtime
- Database stack deployed (for integrations table)

### Deploy
```bash
cd infrastructure
cdk deploy AISWProgramManager-IngestionWorkflow
```

### Verify Deployment
```bash
# Check state machine
aws stepfunctions list-state-machines --query "stateMachines[?name=='ai-sw-pm-ingestion-workflow']"

# Check EventBridge rule
aws events describe-rule --name ai-sw-pm-daily-ingestion

# Check API Gateway
aws apigateway get-rest-apis --query "items[?name=='ai-sw-pm-ingestion-trigger']"
```

## Testing

### Test SQS Queue
```bash
# Send test message to queue
QUEUE_URL=$(aws sqs get-queue-url --queue-name ai-sw-pm-ingestion-queue --query 'QueueUrl' --output text)

aws sqs send-message \
  --queue-url $QUEUE_URL \
  --message-body '{"source":"test","tenantId":"test-tenant-123","triggeredBy":"test-user","timestamp":"2024-01-01T00:00:00Z"}' \
  --message-attributes '{"tenantId":{"StringValue":"test-tenant-123","DataType":"String"}}'

# Check queue depth
aws sqs get-queue-attributes \
  --queue-url $QUEUE_URL \
  --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible

# Check DLQ
DLQ_URL=$(aws sqs get-queue-url --queue-name ai-sw-pm-ingestion-dlq --query 'QueueUrl' --output text)

aws sqs get-queue-attributes \
  --queue-url $DLQ_URL \
  --attribute-names ApproximateNumberOfMessages
```

### Test Manual Trigger
```bash
# Get API endpoint
API_ENDPOINT=$(aws apigateway get-rest-apis --query "items[?name=='ai-sw-pm-ingestion-trigger'].id" --output text)
REGION=$(aws configure get region)

# Trigger workflow
curl -X POST "https://${API_ENDPOINT}.execute-api.${REGION}.amazonaws.com/prod/sync" \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -H "Content-Type: application/json"
```

### Test State Machine Directly
```bash
# Start execution
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:REGION:ACCOUNT:stateMachine:ai-sw-pm-ingestion-workflow \
  --name test-execution-$(date +%s) \
  --input '{"source":"test","timestamp":"2024-01-01T00:00:00Z"}'

# Check execution status
aws stepfunctions describe-execution \
  --execution-arn EXECUTION_ARN
```

## Monitoring

### CloudWatch Metrics
- `ExecutionsFailed`: Number of failed executions
- `ExecutionsSucceeded`: Number of successful executions
- `ExecutionTime`: Duration of executions
- `ApproximateNumberOfMessagesVisible`: Messages in queue
- `ApproximateAgeOfOldestMessage`: Age of oldest message in queue
- `NumberOfMessagesSent`: Messages sent to queue
- `NumberOfMessagesReceived`: Messages received from queue

### CloudWatch Alarms

#### 1. DLQ Messages Alarm
- **Alarm Name**: `ai-sw-pm-ingestion-dlq-messages`
- **Metric**: ApproximateNumberOfMessagesVisible (DLQ)
- **Threshold**: >= 1 message
- **Evaluation Period**: 5 minutes
- **Action**: Sends notification to SNS topic
- **Purpose**: Alert when failed messages appear in DLQ

#### 2. DLQ Age Alarm
- **Alarm Name**: `ai-sw-pm-ingestion-dlq-age`
- **Metric**: ApproximateAgeOfOldestMessage (DLQ)
- **Threshold**: >= 3600 seconds (1 hour)
- **Evaluation Period**: 2 consecutive periods of 5 minutes
- **Action**: Sends notification to SNS topic
- **Purpose**: Alert when messages in DLQ are not being processed

#### 3. Queue Processor Error Alarm
- **Alarm Name**: `ai-sw-pm-queue-processor-errors`
- **Metric**: Lambda Errors (Queue Processor)
- **Threshold**: >= 3 errors
- **Evaluation Period**: 5 minutes
- **Action**: Sends notification to SNS topic
- **Purpose**: Alert when queue processor Lambda has errors

### SNS Topic for Alarms
- **Topic Name**: `ai-sw-pm-ingestion-dlq-alarms`
- **Purpose**: Receive alarm notifications
- **Configuration**: Subscribe email addresses or other endpoints to receive alerts

Configure alarms for:
- High failure rate (> 5%)
- Long execution time (> 30 minutes)
- Lambda function errors

### CloudWatch Logs Insights Queries

**Failed Executions**:
```
fields @timestamp, @message
| filter @message like /FAILED/
| sort @timestamp desc
| limit 20
```

**Execution Duration**:
```
fields @timestamp, executionArn, duration
| filter type = "ExecutionSucceeded"
| stats avg(duration), max(duration), min(duration) by bin(5m)
```

## Configuration

### Modify Schedule
Edit `ingestion_workflow_stack.py`:
```python
schedule=events.Schedule.cron(
    minute="0",
    hour="2",  # Change hour
    month="*",
    week_day="*",
    year="*"
)
```

### Adjust Timeouts
Edit Lambda function definitions in `ingestion_workflow_stack.py`:
```python
timeout=Duration.minutes(5),  # Adjust as needed
memory_size=512,  # Adjust as needed
```

## Troubleshooting

### Messages Stuck in Queue
- Check queue processor Lambda logs for errors
- Verify state machine is not throttled
- Check queue processor concurrency limits
- Review visibility timeout settings

### Messages in DLQ
- Check CloudWatch Logs for queue processor errors
- Review state machine execution failures
- Verify message format is correct
- Check for tenant ID validation issues
- Manually inspect DLQ messages:
  ```bash
  aws sqs receive-message --queue-url $DLQ_URL --max-number-of-messages 10
  ```

### Queue Processor Lambda Errors
- Check Lambda function logs in CloudWatch
- Verify IAM permissions for state machine execution
- Check state machine ARN is correct
- Review message parsing logic

### Workflow Fails at Fetch Step
- Check integration configuration in DynamoDB
- Verify credentials in Secrets Manager
- Check external API availability
- Review Lambda function logs

### Workflow Fails at Validate Step
- Check data schema in fetched data
- Review validation errors in CloudWatch Logs
- Verify schema validator implementation

### Workflow Fails at Store Step
- Check RDS database connectivity
- Verify database schema matches expected structure
- Check for data integrity violations
- Review database connection pool settings

### Manual Trigger Returns 401
- Verify JWT token is valid and not expired
- Check API Gateway authorizer configuration
- Verify user has valid tenant context

## Security

### IAM Permissions
Lambda functions have permissions to:
- Read from DynamoDB (integrations table)
- Read from Secrets Manager (credentials)
- Write to RDS (project data)
- Publish to EventBridge (analysis triggers)

### Encryption
- All data encrypted in transit (TLS)
- Secrets encrypted at rest (KMS)
- Database encrypted at rest (KMS)

### Network
- Lambda functions can be configured to run in VPC
- RDS database in private subnet
- API Gateway with throttling enabled

## Cost Optimization

### Recommendations
1. Use provisioned concurrency only if needed
2. Adjust Lambda memory based on actual usage
3. Consider reducing log retention period
4. Use Step Functions Express workflows for high-volume scenarios
5. Implement caching for frequently accessed data

### Estimated Costs (Monthly)
- Step Functions: ~$0.025 per 1,000 state transitions
- Lambda: ~$0.20 per 1 million requests + compute time
- EventBridge: ~$1.00 per 1 million events
- API Gateway: ~$3.50 per 1 million requests
- CloudWatch Logs: ~$0.50 per GB ingested

**Total estimated cost for 1 daily execution**: < $5/month
