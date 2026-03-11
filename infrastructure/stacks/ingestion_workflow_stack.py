"""Data Ingestion Workflow Stack - Step Functions orchestration for data ingestion."""

from aws_cdk import (
    Stack,
    Duration,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_apigateway as apigw,
    aws_logs as logs,
    aws_sqs as sqs,
    aws_lambda_event_sources as lambda_event_sources,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
)
from constructs import Construct
import os


class IngestionWorkflowStack(Stack):
    """Stack for data ingestion workflow orchestration."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        integrations_table_name: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.integrations_table_name = integrations_table_name

        # Create SQS queues for job buffering
        self._create_sqs_queues()

        # Create Lambda functions for workflow steps
        self._create_lambda_functions()

        # Create Step Functions state machine
        self._create_state_machine()

        # Create queue processor Lambda
        self._create_queue_processor()

        # Create EventBridge scheduled rule
        self._create_scheduled_rule()

        # Create manual trigger endpoint
        self._create_manual_trigger_endpoint()

        # Create CloudWatch alarms for DLQ
        self._create_dlq_alarms()

    def _create_sqs_queues(self) -> None:
        """
        Create SQS queues for ingestion job buffering.
        
        Validates: Requirement 3.8
        """
        # Create dead-letter queue for failed jobs
        self.ingestion_dlq = sqs.Queue(
            self,
            "IngestionDLQ",
            queue_name="ai-sw-pm-ingestion-dlq",
            retention_period=Duration.days(14),  # Retain failed messages for 14 days
            encryption=sqs.QueueEncryption.KMS_MANAGED,
            enforce_ssl=True
        )

        # Create main ingestion queue with DLQ configuration
        self.ingestion_queue = sqs.Queue(
            self,
            "IngestionQueue",
            queue_name="ai-sw-pm-ingestion-queue",
            visibility_timeout=Duration.minutes(35),  # Longer than state machine timeout (30 min)
            retention_period=Duration.days(4),  # Retain messages for 4 days
            receive_message_wait_time=Duration.seconds(20),  # Long polling
            encryption=sqs.QueueEncryption.KMS_MANAGED,
            enforce_ssl=True,
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,  # Retry up to 3 times before moving to DLQ
                queue=self.ingestion_dlq
            )
        )

    def _create_lambda_functions(self) -> None:
        """Create Lambda functions for each workflow step."""

        # Common Lambda execution role
        lambda_role = iam.Role(
            self,
            "IngestionLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                )
            ]
        )

        # Grant permissions to access DynamoDB, Secrets Manager, and RDS
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Query",
                    "dynamodb:Scan"
                ],
                resources=[f"arn:aws:dynamodb:{self.region}:{self.account}:table/*"]
            )
        )

        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:DescribeSecret"
                ],
                resources=[f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:*"]
            )
        )

        # Fetch Jira Data Lambda
        self.fetch_jira_lambda = lambda_.Function(
            self,
            "FetchJiraDataFunction",
            function_name="ai-sw-pm-fetch-jira-data",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="data_fetcher.fetch_jira_data",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/jira_integration")
            ),
            environment={
                "INTEGRATIONS_TABLE_NAME": self.integrations_table_name
            },
            timeout=Duration.minutes(5),
            memory_size=512,
            role=lambda_role,
            description="Fetch project data from Jira API"
        )

        # Fetch Azure DevOps Data Lambda
        self.fetch_azure_devops_lambda = lambda_.Function(
            self,
            "FetchAzureDevOpsDataFunction",
            function_name="ai-sw-pm-fetch-azure-devops-data",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="data_fetcher.fetch_azure_devops_data",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/azure_devops_integration")
            ),
            environment={
                "INTEGRATIONS_TABLE_NAME": self.integrations_table_name
            },
            timeout=Duration.minutes(5),
            memory_size=512,
            role=lambda_role,
            description="Fetch project data from Azure DevOps API"
        )

        # Validate Data Lambda
        self.validate_data_lambda = lambda_.Function(
            self,
            "ValidateDataFunction",
            function_name="ai-sw-pm-validate-data",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/data_validation")
            ),
            timeout=Duration.minutes(2),
            memory_size=256,
            role=lambda_role,
            description="Validate ingested data against schema"
        )

        # Store Data Lambda
        self.store_data_lambda = lambda_.Function(
            self,
            "StoreDataFunction",
            function_name="ai-sw-pm-store-data",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/data_storage")
            ),
            timeout=Duration.minutes(5),
            memory_size=512,
            role=lambda_role,
            description="Store validated data in RDS and DynamoDB"
        )

        # Trigger Analysis Lambda
        self.trigger_analysis_lambda = lambda_.Function(
            self,
            "TriggerAnalysisFunction",
            function_name="ai-sw-pm-trigger-analysis",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/analysis_trigger")
            ),
            timeout=Duration.minutes(2),
            memory_size=256,
            role=lambda_role,
            description="Trigger risk detection and prediction analysis"
        )

    def _create_state_machine(self) -> None:
        """Create Step Functions state machine for data ingestion workflow."""

        # Define workflow states
        
        # Fetch Jira Data task
        fetch_jira_task = tasks.LambdaInvoke(
            self,
            "FetchJiraData",
            lambda_function=self.fetch_jira_lambda,
            output_path="$.Payload",
            retry_on_service_exceptions=True,
            result_selector={
                "statusCode.$": "$.statusCode",
                "body.$": "$.body",
                "source": "JIRA"
            }
        )

        # Fetch Azure DevOps Data task
        fetch_azure_devops_task = tasks.LambdaInvoke(
            self,
            "FetchAzureDevOpsData",
            lambda_function=self.fetch_azure_devops_lambda,
            output_path="$.Payload",
            retry_on_service_exceptions=True,
            result_selector={
                "statusCode.$": "$.statusCode",
                "body.$": "$.body",
                "source": "AZURE_DEVOPS"
            }
        )

        # Parallel fetch from both sources
        parallel_fetch = sfn.Parallel(
            self,
            "ParallelFetch",
            result_path="$.fetchResults"
        )
        parallel_fetch.branch(fetch_jira_task)
        parallel_fetch.branch(fetch_azure_devops_task)

        # Validate Data task
        validate_data_task = tasks.LambdaInvoke(
            self,
            "ValidateData",
            lambda_function=self.validate_data_lambda,
            payload=sfn.TaskInput.from_object({
                "fetchResults.$": "$.fetchResults"
            }),
            output_path="$.Payload",
            retry_on_service_exceptions=True
        )

        # Store Data task
        store_data_task = tasks.LambdaInvoke(
            self,
            "StoreData",
            lambda_function=self.store_data_lambda,
            output_path="$.Payload",
            retry_on_service_exceptions=True
        )

        # Trigger Analysis task
        trigger_analysis_task = tasks.LambdaInvoke(
            self,
            "TriggerAnalysis",
            lambda_function=self.trigger_analysis_lambda,
            output_path="$.Payload",
            retry_on_service_exceptions=True
        )

        # Success state
        success_state = sfn.Succeed(
            self,
            "IngestionSuccess",
            comment="Data ingestion workflow completed successfully"
        )

        # Failure state
        failure_state = sfn.Fail(
            self,
            "IngestionFailure",
            comment="Data ingestion workflow failed",
            cause="Workflow execution failed",
            error="WorkflowError"
        )

        # Define workflow chain
        definition = parallel_fetch \
            .next(validate_data_task) \
            .next(store_data_task) \
            .next(trigger_analysis_task) \
            .next(success_state)

        # Add error handling
        parallel_fetch.add_catch(
            failure_state,
            errors=["States.ALL"],
            result_path="$.error"
        )
        validate_data_task.add_catch(
            failure_state,
            errors=["States.ALL"],
            result_path="$.error"
        )
        store_data_task.add_catch(
            failure_state,
            errors=["States.ALL"],
            result_path="$.error"
        )
        trigger_analysis_task.add_catch(
            failure_state,
            errors=["States.ALL"],
            result_path="$.error"
        )

        # Create CloudWatch log group for state machine
        log_group = logs.LogGroup(
            self,
            "IngestionWorkflowLogGroup",
            log_group_name="/aws/stepfunctions/ai-sw-pm-ingestion-workflow",
            retention=logs.RetentionDays.ONE_MONTH
        )

        # Create state machine
        self.state_machine = sfn.StateMachine(
            self,
            "IngestionWorkflowStateMachine",
            state_machine_name="ai-sw-pm-ingestion-workflow",
            definition=definition,
            timeout=Duration.minutes(30),
            tracing_enabled=True,
            logs=sfn.LogOptions(
                destination=log_group,
                level=sfn.LogLevel.ALL,
                include_execution_data=True
            )
        )

    def _create_queue_processor(self) -> None:
        """
        Create Lambda function to process messages from SQS queue and trigger state machine.
        
        Validates: Requirement 3.8
        """
        # Create Lambda function for queue processing
        self.queue_processor_lambda = lambda_.Function(
            self,
            "QueueProcessorFunction",
            function_name="ai-sw-pm-queue-processor",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_inline(f"""
import json
import boto3
import os
from datetime import datetime

stepfunctions = boto3.client('stepfunctions')

STATE_MACHINE_ARN = '{self.state_machine.state_machine_arn}'

def lambda_handler(event, context):
    \"\"\"
    Process ingestion jobs from SQS queue and trigger state machine.
    
    Validates: Requirement 3.8
    \"\"\"
    print(f"Processing {{len(event.get('Records', []))}} messages from queue")
    
    failed_messages = []
    
    for record in event.get('Records', []):
        try:
            # Parse message body
            message_body = json.loads(record['body'])
            
            tenant_id = message_body.get('tenantId')
            source = message_body.get('source', 'queue')
            triggered_by = message_body.get('triggeredBy', 'system')
            
            if not tenant_id:
                print(f"Error: Missing tenantId in message: {{record['messageId']}}")
                failed_messages.append(record['messageId'])
                continue
            
            # Create unique execution name
            execution_name = f"queue-{{tenant_id}}-{{int(datetime.utcnow().timestamp())}}"
            
            # Start state machine execution
            response = stepfunctions.start_execution(
                stateMachineArn=STATE_MACHINE_ARN,
                name=execution_name,
                input=json.dumps({{
                    'source': source,
                    'tenantId': tenant_id,
                    'triggeredBy': triggered_by,
                    'timestamp': datetime.utcnow().isoformat() + 'Z',
                    'messageId': record['messageId']
                }})
            )
            
            print(f"Started execution: {{execution_name}} for tenant: {{tenant_id}}")
            
        except Exception as e:
            print(f"Error processing message {{record['messageId']}}: {{str(e)}}")
            failed_messages.append(record['messageId'])
    
    # If any messages failed, raise exception to trigger retry
    if failed_messages:
        raise Exception(f"Failed to process {{len(failed_messages)}} messages: {{failed_messages}}")
    
    return {{
        'statusCode': 200,
        'body': json.dumps({{
            'message': f"Successfully processed {{len(event.get('Records', []))}} messages"
        }})
    }}
"""),
            timeout=Duration.minutes(5),
            memory_size=256,
            description="Process ingestion jobs from SQS queue",
            reserved_concurrent_executions=10  # Limit concurrency to avoid overwhelming state machine
        )

        # Grant permission to start state machine execution
        self.state_machine.grant_start_execution(self.queue_processor_lambda)

        # Add SQS event source to Lambda
        self.queue_processor_lambda.add_event_source(
            lambda_event_sources.SqsEventSource(
                self.ingestion_queue,
                batch_size=5,  # Process up to 5 messages at a time
                max_batching_window=Duration.seconds(10),  # Wait up to 10 seconds to batch messages
                report_batch_item_failures=True  # Enable partial batch failure reporting
            )
        )

    def _create_scheduled_rule(self) -> None:
        """Create EventBridge scheduled rule for periodic ingestion."""

        # Create Lambda function to send scheduled messages to queue
        self.scheduled_trigger_lambda = lambda_.Function(
            self,
            "ScheduledTriggerFunction",
            function_name="ai-sw-pm-scheduled-ingestion-trigger",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_inline(f"""
import json
import boto3
from datetime import datetime

sqs = boto3.client('sqs')

QUEUE_URL = '{self.ingestion_queue.queue_url}'

def lambda_handler(event, context):
    \"\"\"
    Send scheduled ingestion jobs to SQS queue.
    
    Validates: Requirements 3.3, 4.3, 3.8
    \"\"\"
    try:
        # For scheduled runs, we could fetch all active tenants from DynamoDB
        # For now, send a generic message that will be processed
        message_body = {{
            'source': 'scheduled',
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'triggeredBy': 'system'
        }}
        
        response = sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(message_body),
            MessageAttributes={{
                'source': {{
                    'StringValue': 'scheduled',
                    'DataType': 'String'
                }}
            }}
        )
        
        print(f"Scheduled ingestion job queued: {{response['MessageId']}}")
        
        return {{
            'statusCode': 200,
            'body': json.dumps({{
                'message': 'Scheduled ingestion job queued successfully',
                'messageId': response['MessageId']
            }})
        }}
        
    except Exception as e:
        print(f"Error queueing scheduled ingestion: {{str(e)}}")
        raise
"""),
            timeout=Duration.seconds(30),
            memory_size=256,
            description="Scheduled trigger for data ingestion workflow"
        )

        # Grant permission to send messages to SQS queue
        self.ingestion_queue.grant_send_messages(self.scheduled_trigger_lambda)

        # Create EventBridge rule for daily execution at 2 AM UTC
        self.scheduled_rule = events.Rule(
            self,
            "IngestionScheduledRule",
            rule_name="ai-sw-pm-daily-ingestion",
            description="Trigger data ingestion workflow daily at 2 AM UTC",
            schedule=events.Schedule.cron(
                minute="0",
                hour="2",
                month="*",
                week_day="*",
                year="*"
            ),
            enabled=True
        )

        # Add Lambda as target instead of state machine
        self.scheduled_rule.add_target(
            targets.LambdaFunction(
                self.scheduled_trigger_lambda,
                retry_attempts=2
            )
        )

    def _create_manual_trigger_endpoint(self) -> None:
        """Create API Gateway endpoint for manual workflow trigger."""

        # Create Lambda function for manual trigger
        self.manual_trigger_lambda = lambda_.Function(
            self,
            "ManualTriggerFunction",
            function_name="ai-sw-pm-manual-ingestion-trigger",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_inline(f"""
import json
import boto3
import os
from datetime import datetime

sqs = boto3.client('sqs')

QUEUE_URL = '{self.ingestion_queue.queue_url}'

def lambda_handler(event, context):
    \"\"\"
    Trigger data ingestion workflow manually by sending message to SQS queue.
    
    Validates: Requirements 3.4, 4.4, 3.8
    \"\"\"
    try:
        # Extract tenant_id from authorizer context
        authorizer_context = event.get('requestContext', {{}}).get('authorizer', {{}})
        tenant_id = authorizer_context.get('tenantId')
        user_id = authorizer_context.get('userId')
        
        if not tenant_id:
            return {{
                'statusCode': 401,
                'headers': {{
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                }},
                'body': json.dumps({{
                    'error': {{
                        'code': 'UNAUTHORIZED',
                        'message': 'Missing tenant context'
                    }}
                }})
            }}
        
        # Send message to SQS queue for buffering
        message_body = {{
            'source': 'manual',
            'tenantId': tenant_id,
            'triggeredBy': user_id,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }}
        
        response = sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(message_body),
            MessageAttributes={{
                'tenantId': {{
                    'StringValue': tenant_id,
                    'DataType': 'String'
                }},
                'source': {{
                    'StringValue': 'manual',
                    'DataType': 'String'
                }}
            }}
        )
        
        return {{
            'statusCode': 202,
            'headers': {{
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }},
            'body': json.dumps({{
                'syncJobId': response['MessageId'],
                'status': 'QUEUED',
                'message': 'Data ingestion job queued successfully'
            }})
        }}
        
    except Exception as e:
        print(f"Error queueing ingestion job: {{str(e)}}")
        return {{
            'statusCode': 500,
            'headers': {{
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }},
            'body': json.dumps({{
                'error': {{
                    'code': 'INTERNAL_ERROR',
                    'message': 'Failed to queue data ingestion job'
                }}
            }})
        }}
"""),
            timeout=Duration.seconds(30),
            memory_size=256,
            description="Manual trigger endpoint for data ingestion workflow"
        )

        # Grant permission to send messages to SQS queue
        self.ingestion_queue.grant_send_messages(self.manual_trigger_lambda)

        # Create API Gateway REST API
        self.api = apigw.RestApi(
            self,
            "IngestionTriggerAPI",
            rest_api_name="ai-sw-pm-ingestion-trigger",
            description="API for manually triggering data ingestion workflow",
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                throttling_rate_limit=10,
                throttling_burst_limit=20,
                logging_level=apigw.MethodLoggingLevel.INFO,
                data_trace_enabled=True,
                metrics_enabled=True
            ),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization"]
            )
        )

        # Create /sync resource
        sync_resource = self.api.root.add_resource("sync")

        # Add POST method with Lambda integration
        sync_resource.add_method(
            "POST",
            apigw.LambdaIntegration(
                self.manual_trigger_lambda,
                proxy=True
            )
        )

    def _create_dlq_alarms(self) -> None:
        """
        Create CloudWatch alarms for dead-letter queue monitoring.
        
        Validates: Requirement 3.8
        """
        # Create SNS topic for DLQ alerts (optional - can be configured later)
        self.dlq_alarm_topic = sns.Topic(
            self,
            "DLQAlarmTopic",
            topic_name="ai-sw-pm-ingestion-dlq-alarms",
            display_name="AI SW PM Ingestion DLQ Alarms"
        )

        # Create CloudWatch alarm for messages in DLQ
        self.dlq_messages_alarm = cloudwatch.Alarm(
            self,
            "DLQMessagesAlarm",
            alarm_name="ai-sw-pm-ingestion-dlq-messages",
            alarm_description="Alert when messages appear in ingestion DLQ",
            metric=self.ingestion_dlq.metric_approximate_number_of_messages_visible(
                statistic="Sum",
                period=Duration.minutes(5)
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )

        # Add SNS action to alarm
        self.dlq_messages_alarm.add_alarm_action(
            cw_actions.SnsAction(self.dlq_alarm_topic)
        )

        # Create CloudWatch alarm for old messages in DLQ
        self.dlq_age_alarm = cloudwatch.Alarm(
            self,
            "DLQAgeAlarm",
            alarm_name="ai-sw-pm-ingestion-dlq-age",
            alarm_description="Alert when messages in DLQ are older than 1 hour",
            metric=self.ingestion_dlq.metric_approximate_age_of_oldest_message(
                statistic="Maximum",
                period=Duration.minutes(5)
            ),
            threshold=3600,  # 1 hour in seconds
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )

        # Add SNS action to alarm
        self.dlq_age_alarm.add_alarm_action(
            cw_actions.SnsAction(self.dlq_alarm_topic)
        )

        # Create CloudWatch alarm for queue processor errors
        self.processor_error_alarm = cloudwatch.Alarm(
            self,
            "ProcessorErrorAlarm",
            alarm_name="ai-sw-pm-queue-processor-errors",
            alarm_description="Alert when queue processor Lambda has errors",
            metric=self.queue_processor_lambda.metric_errors(
                statistic="Sum",
                period=Duration.minutes(5)
            ),
            threshold=3,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )

        # Add SNS action to alarm
        self.processor_error_alarm.add_alarm_action(
            cw_actions.SnsAction(self.dlq_alarm_topic)
        )
