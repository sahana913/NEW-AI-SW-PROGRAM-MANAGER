"""Storage stack - S3 buckets and OpenSearch domain."""

from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    aws_s3 as s3,
    aws_opensearchservice as opensearch,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_kms as kms,
)
from constructs import Construct


class StorageStack(Stack):
    """Stack for storage resources."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc = None,
        opensearch_security_group: ec2.ISecurityGroup = None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.vpc = vpc
        self.opensearch_security_group = opensearch_security_group

        # Create KMS key for encryption
        self.encryption_key = kms.Key(
            self,
            "StorageEncryptionKey",
            description="Encryption key for storage resources",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN
        )

        # Create S3 buckets
        self._create_s3_buckets()

        # Create OpenSearch domain if VPC is provided
        if self.vpc and self.opensearch_security_group:
            self._create_opensearch_domain()

    def _create_s3_buckets(self) -> None:
        """Create S3 buckets for documents and reports."""

        # Documents bucket
        self.documents_bucket = s3.Bucket(
            self,
            "DocumentsBucket",
            bucket_name=None,  # Auto-generate unique name
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.encryption_key,
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldVersions",
                    noncurrent_version_expiration=Duration.days(90)
                )
            ],
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False
        )

        # Enable server access logging
        self.documents_access_logs_bucket = s3.Bucket(
            self,
            "DocumentsAccessLogsBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldLogs",
                    expiration=Duration.days(90)
                )
            ],
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )

        self.documents_bucket.add_lifecycle_rule(
            id="TransitionToIA",
            transitions=[
                s3.Transition(
                    storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                    transition_after=Duration.days(30)
                )
            ]
        )

        # Reports bucket
        self.reports_bucket = s3.Bucket(
            self,
            "ReportsBucket",
            bucket_name=None,  # Auto-generate unique name
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.encryption_key,
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldReports",
                    expiration=Duration.days(365)
                ),
                s3.LifecycleRule(
                    id="TransitionToIA",
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(30)
                        )
                    ]
                )
            ],
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False
        )

        # Model artifacts bucket (for SageMaker)
        self.model_artifacts_bucket = s3.Bucket(
            self,
            "ModelArtifactsBucket",
            bucket_name=None,  # Auto-generate unique name
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.encryption_key,
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False
        )

    def _create_opensearch_domain(self) -> None:
        """Create OpenSearch domain for vector search in private subnet."""

        # Create OpenSearch domain in private subnet with provided security group
        self.opensearch_domain = opensearch.Domain(
            self,
            "OpenSearchDomain",
            version=opensearch.EngineVersion.OPENSEARCH_2_11,
            capacity=opensearch.CapacityConfig(
                data_node_instance_type="r6g.large.search",
                data_nodes=2,
                multi_az_with_standby_enabled=False
            ),
            ebs=opensearch.EbsOptions(
                volume_size=100,
                volume_type=ec2.EbsDeviceVolumeType.GP3,
                iops=3000,
                throughput=125
            ),
            zone_awareness=opensearch.ZoneAwarenessConfig(
                enabled=True,
                availability_zone_count=2
            ),
            vpc=self.vpc,
            vpc_subnets=[ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            )],
            security_groups=[self.opensearch_security_group],
            encryption_at_rest=opensearch.EncryptionAtRestOptions(
                enabled=True,
                kms_key=self.encryption_key
            ),
            node_to_node_encryption=True,
            enforce_https=True,
            tls_security_policy=opensearch.TLSSecurityPolicy.TLS_1_2,
            automated_snapshot_start_hour=2,
            removal_policy=RemovalPolicy.RETAIN
        )

        # Grant access to Lambda functions (will be configured later)
        self.opensearch_domain.add_access_policies(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("lambda.amazonaws.com")],
                actions=[
                    "es:ESHttpGet",
                    "es:ESHttpPut",
                    "es:ESHttpPost",
                    "es:ESHttpDelete"
                ],
                resources=[
                    f"{self.opensearch_domain.domain_arn}/*"
                ]
            )
        )
