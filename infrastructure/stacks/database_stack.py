"""Database stack - DynamoDB tables and RDS PostgreSQL."""

from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    aws_dynamodb as dynamodb,
    aws_rds as rds,
    aws_ec2 as ec2,
    aws_secretsmanager as secretsmanager,
    aws_kms as kms,
)
from constructs import Construct


class DatabaseStack(Stack):
    """Stack for database resources."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc = None,
        rds_security_group: ec2.ISecurityGroup = None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.vpc = vpc
        self.rds_security_group = rds_security_group

        # Create KMS key for encryption
        self.encryption_key = kms.Key(
            self,
            "DatabaseEncryptionKey",
            description="Encryption key for database resources",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN
        )

        # Create DynamoDB tables
        self._create_dynamodb_tables()

        # Create RDS PostgreSQL database if VPC is provided
        if self.vpc and self.rds_security_group:
            self._create_rds_database()

    def _create_dynamodb_tables(self) -> None:
        """Create all DynamoDB tables."""

        # Users table
        self.users_table = dynamodb.Table(
            self,
            "UsersTable",
            table_name="ai-sw-pm-users",
            partition_key=dynamodb.Attribute(
                name="PK",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="SK",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=self.encryption_key,
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.RETAIN
        )

        # GSI for email lookup
        self.users_table.add_global_secondary_index(
            index_name="EmailIndex",
            partition_key=dynamodb.Attribute(
                name="GSI1PK",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="GSI1SK",
                type=dynamodb.AttributeType.STRING
            )
        )

        # Risks table
        self.risks_table = dynamodb.Table(
            self,
            "RisksTable",
            table_name="ai-sw-pm-risks",
            partition_key=dynamodb.Attribute(
                name="PK",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="SK",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=self.encryption_key,
            point_in_time_recovery=True,
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
            removal_policy=RemovalPolicy.RETAIN
        )

        # GSI for project-specific queries
        self.risks_table.add_global_secondary_index(
            index_name="ProjectIndex",
            partition_key=dynamodb.Attribute(
                name="GSI1PK",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="GSI1SK",
                type=dynamodb.AttributeType.STRING
            )
        )

        # GSI for severity filtering
        self.risks_table.add_global_secondary_index(
            index_name="SeverityIndex",
            partition_key=dynamodb.Attribute(
                name="GSI2PK",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="GSI2SK",
                type=dynamodb.AttributeType.STRING
            )
        )

        # Predictions table
        self.predictions_table = dynamodb.Table(
            self,
            "PredictionsTable",
            table_name="ai-sw-pm-predictions",
            partition_key=dynamodb.Attribute(
                name="PK",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="SK",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=self.encryption_key,
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.RETAIN
        )

        # GSI for project and type queries
        self.predictions_table.add_global_secondary_index(
            index_name="ProjectTypeIndex",
            partition_key=dynamodb.Attribute(
                name="GSI1PK",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="GSI1SK",
                type=dynamodb.AttributeType.STRING
            )
        )

        # Documents table
        self.documents_table = dynamodb.Table(
            self,
            "DocumentsTable",
            table_name="ai-sw-pm-documents",
            partition_key=dynamodb.Attribute(
                name="PK",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="SK",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=self.encryption_key,
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.RETAIN
        )

        # GSI for project queries
        self.documents_table.add_global_secondary_index(
            index_name="ProjectIndex",
            partition_key=dynamodb.Attribute(
                name="GSI1PK",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="GSI1SK",
                type=dynamodb.AttributeType.STRING
            )
        )

        # Document Extractions table
        self.document_extractions_table = dynamodb.Table(
            self,
            "DocumentExtractionsTable",
            table_name="ai-sw-pm-document-extractions",
            partition_key=dynamodb.Attribute(
                name="PK",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="SK",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=self.encryption_key,
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.RETAIN
        )

        # Reports table
        self.reports_table = dynamodb.Table(
            self,
            "ReportsTable",
            table_name="ai-sw-pm-reports",
            partition_key=dynamodb.Attribute(
                name="PK",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="SK",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=self.encryption_key,
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.RETAIN
        )

        # GSI for report type queries
        self.reports_table.add_global_secondary_index(
            index_name="ReportTypeIndex",
            partition_key=dynamodb.Attribute(
                name="GSI1PK",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="GSI1SK",
                type=dynamodb.AttributeType.STRING
            )
        )

        # Report Schedules table
        self.report_schedules_table = dynamodb.Table(
            self,
            "ReportSchedulesTable",
            table_name="ai-sw-pm-report-schedules",
            partition_key=dynamodb.Attribute(
                name="PK",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="SK",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=self.encryption_key,
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.RETAIN
        )

        # Integrations table
        self.integrations_table = dynamodb.Table(
            self,
            "IntegrationsTable",
            table_name="ai-sw-pm-integrations",
            partition_key=dynamodb.Attribute(
                name="PK",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="SK",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=self.encryption_key,
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.RETAIN
        )

        # Email Delivery Logs table
        self.email_delivery_logs_table = dynamodb.Table(
            self,
            "EmailDeliveryLogsTable",
            table_name="ai-sw-pm-email-delivery-logs",
            partition_key=dynamodb.Attribute(
                name="PK",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="SK",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=self.encryption_key,
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.RETAIN
        )

        # GSI for recipient queries
        self.email_delivery_logs_table.add_global_secondary_index(
            index_name="RecipientIndex",
            partition_key=dynamodb.Attribute(
                name="GSI1PK",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="GSI1SK",
                type=dynamodb.AttributeType.STRING
            )
        )

        # Email Preferences table
        self.email_preferences_table = dynamodb.Table(
            self,
            "EmailPreferencesTable",
            table_name="ai-sw-pm-email-preferences",
            partition_key=dynamodb.Attribute(
                name="PK",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="SK",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=self.encryption_key,
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.RETAIN
        )

    def _create_rds_database(self) -> None:
        """Create RDS PostgreSQL database."""

        # Create database credentials secret
        self.db_credentials = secretsmanager.Secret(
            self,
            "DBCredentials",
            description="RDS PostgreSQL credentials",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "postgres"}',
                generate_string_key="password",
                exclude_punctuation=True,
                password_length=32
            )
        )

        # Create RDS PostgreSQL instance in isolated subnet with provided security group
        self.db_instance = rds.DatabaseInstance(
            self,
            "PostgreSQLInstance",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_15_4
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE3,
                ec2.InstanceSize.MEDIUM
            ),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[self.rds_security_group],
            credentials=rds.Credentials.from_secret(self.db_credentials),
            database_name="ai_sw_program_manager",
            allocated_storage=100,
            max_allocated_storage=500,
            storage_encrypted=True,
            storage_encryption_key=self.encryption_key,
            multi_az=True,
            backup_retention=Duration.days(7),
            deletion_protection=True,
            removal_policy=RemovalPolicy.RETAIN
        )
