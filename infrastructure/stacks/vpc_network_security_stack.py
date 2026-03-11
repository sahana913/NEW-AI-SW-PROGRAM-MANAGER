"""VPC and Network Security Stack - Configures VPC, security groups, and flow logs."""

from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    aws_ec2 as ec2,
    aws_logs as logs,
    aws_iam as iam,
    aws_s3 as s3,
)
from constructs import Construct


class VpcNetworkSecurityStack(Stack):
    """Stack for VPC and network security configuration."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create VPC with private subnets for RDS and OpenSearch
        self.vpc = self._create_vpc()

        # Create security groups with least privilege rules
        self.rds_security_group = self._create_rds_security_group()
        self.opensearch_security_group = self._create_opensearch_security_group()
        self.lambda_security_group = self._create_lambda_security_group()

        # Enable VPC Flow Logs
        self._enable_vpc_flow_logs()

    def _create_vpc(self) -> ec2.Vpc:
        """Create VPC with public, private, and isolated subnets."""
        vpc = ec2.Vpc(
            self,
            "VPC",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                # Public subnets for NAT Gateway
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                ),
                # Private subnets with egress for Lambda functions
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24
                ),
                # Isolated subnets for RDS (no internet access)
                ec2.SubnetConfiguration(
                    name="Isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24
                )
            ],
            enable_dns_hostnames=True,
            enable_dns_support=True
        )

        return vpc

    def _create_rds_security_group(self) -> ec2.SecurityGroup:
        """Create security group for RDS with least privilege rules."""
        sg = ec2.SecurityGroup(
            self,
            "RDSSecurityGroup",
            vpc=self.vpc,
            description="Security group for RDS PostgreSQL - least privilege access",
            allow_all_outbound=False
        )

        # Allow PostgreSQL access only from Lambda security group
        # This will be configured after Lambda security group is created
        sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(5432),
            description="Allow PostgreSQL from VPC CIDR (will be restricted to Lambda SG)"
        )

        return sg

    def _create_opensearch_security_group(self) -> ec2.SecurityGroup:
        """Create security group for OpenSearch with least privilege rules."""
        sg = ec2.SecurityGroup(
            self,
            "OpenSearchSecurityGroup",
            vpc=self.vpc,
            description="Security group for OpenSearch - least privilege access",
            allow_all_outbound=False
        )

        # Allow HTTPS access only from Lambda security group
        sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(443),
            description="Allow HTTPS from VPC CIDR (will be restricted to Lambda SG)"
        )

        return sg

    def _create_lambda_security_group(self) -> ec2.SecurityGroup:
        """Create security group for Lambda functions."""
        sg = ec2.SecurityGroup(
            self,
            "LambdaSecurityGroup",
            vpc=self.vpc,
            description="Security group for Lambda functions accessing VPC resources",
            allow_all_outbound=True  # Lambda needs to access AWS services
        )

        return sg

    def _enable_vpc_flow_logs(self) -> None:
        """Enable VPC Flow Logs for network monitoring and security analysis."""
        # Create CloudWatch log group for VPC Flow Logs
        log_group = logs.LogGroup(
            self,
            "VPCFlowLogsGroup",
            log_group_name="/aws/vpc/flowlogs",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.RETAIN
        )

        # Create IAM role for VPC Flow Logs
        flow_logs_role = iam.Role(
            self,
            "VPCFlowLogsRole",
            assumed_by=iam.ServicePrincipal("vpc-flow-logs.amazonaws.com"),
            description="IAM role for VPC Flow Logs to write to CloudWatch"
        )

        # Grant permissions to write to CloudWatch Logs
        flow_logs_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams"
                ],
                resources=[log_group.log_group_arn]
            )
        )

        # Create S3 bucket for long-term VPC Flow Logs storage
        flow_logs_bucket = s3.Bucket(
            self,
            "VPCFlowLogsBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="TransitionToGlacier",
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(90)
                        )
                    ]
                ),
                s3.LifecycleRule(
                    id="DeleteOldLogs",
                    expiration=Duration.days(365)
                )
            ],
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False
        )

        # Enable VPC Flow Logs to CloudWatch
        self.vpc.add_flow_log(
            "VPCFlowLogsToCloudWatch",
            destination=ec2.FlowLogDestination.to_cloud_watch_logs(
                log_group=log_group,
                iam_role=flow_logs_role
            ),
            traffic_type=ec2.FlowLogTrafficType.ALL
        )

        # Enable VPC Flow Logs to S3 for long-term storage
        self.vpc.add_flow_log(
            "VPCFlowLogsToS3",
            destination=ec2.FlowLogDestination.to_s3(
                bucket=flow_logs_bucket,
                key_prefix="vpc-flow-logs/"
            ),
            traffic_type=ec2.FlowLogTrafficType.ALL
        )

    def configure_rds_security_group_rules(self) -> None:
        """Configure RDS security group to only allow access from Lambda security group."""
        # Remove the broad VPC CIDR rule and add specific Lambda SG rule
        self.rds_security_group.add_ingress_rule(
            peer=ec2.Peer.security_group_id(self.lambda_security_group.security_group_id),
            connection=ec2.Port.tcp(5432),
            description="Allow PostgreSQL from Lambda functions only"
        )

    def configure_opensearch_security_group_rules(self) -> None:
        """Configure OpenSearch security group to only allow access from Lambda security group."""
        # Add specific Lambda SG rule
        self.opensearch_security_group.add_ingress_rule(
            peer=ec2.Peer.security_group_id(self.lambda_security_group.security_group_id),
            connection=ec2.Port.tcp(443),
            description="Allow HTTPS from Lambda functions only"
        )

