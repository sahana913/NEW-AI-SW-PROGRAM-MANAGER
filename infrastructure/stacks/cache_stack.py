"""Cache stack - ElastiCache Redis for dashboard and report caching."""

from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput,
    aws_elasticache as elasticache,
    aws_ec2 as ec2,
)
from constructs import Construct


class CacheStack(Stack):
    """Stack for ElastiCache Redis caching resources."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        **kwargs
    ) -> None:
        """
        Initialize cache stack.
        
        Args:
            scope: CDK scope
            construct_id: Stack ID
            vpc: VPC for ElastiCache deployment
            **kwargs: Additional stack arguments
        """
        super().__init__(scope, construct_id, **kwargs)

        self.vpc = vpc

        # Create security group for Redis
        self._create_security_group()

        # Create subnet group for Redis
        self._create_subnet_group()

        # Create Redis replication group
        self._create_redis_cluster()

    def _create_security_group(self) -> None:
        """Create security group for Redis cluster."""
        self.redis_security_group = ec2.SecurityGroup(
            self,
            "RedisSecurityGroup",
            vpc=self.vpc,
            description="Security group for ElastiCache Redis",
            allow_all_outbound=False
        )

        # Allow Redis port from within VPC
        self.redis_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(6379),
            description="Allow Redis access from VPC"
        )

    def _create_subnet_group(self) -> None:
        """Create subnet group for Redis cluster."""
        # Get private subnet IDs
        private_subnets = self.vpc.select_subnets(
            subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
        )

        self.subnet_group = elasticache.CfnSubnetGroup(
            self,
            "RedisSubnetGroup",
            description="Subnet group for ElastiCache Redis",
            subnet_ids=private_subnets.subnet_ids,
            cache_subnet_group_name="ai-sw-pm-redis-subnet-group"
        )

    def _create_redis_cluster(self) -> None:
        """
        Create ElastiCache Redis replication group.
        
        Validates: Requirements 20.3, 23.1 (caching for performance)
        """
        # Create parameter group for Redis 7.x
        self.parameter_group = elasticache.CfnParameterGroup(
            self,
            "RedisParameterGroup",
            cache_parameter_group_family="redis7",
            description="Parameter group for AI SW Program Manager Redis",
            properties={
                # Enable automatic failover
                "cluster-enabled": "no",
                # Set max memory policy to evict least recently used keys
                "maxmemory-policy": "allkeys-lru",
            }
        )

        # Create Redis replication group with automatic failover
        self.redis_replication_group = elasticache.CfnReplicationGroup(
            self,
            "RedisReplicationGroup",
            replication_group_description="Redis cluster for dashboard and report caching",
            engine="redis",
            engine_version="7.0",
            cache_node_type="cache.t3.micro",  # Start small, can scale up
            num_cache_clusters=2,  # Primary + 1 replica for HA
            automatic_failover_enabled=True,
            multi_az_enabled=True,
            cache_subnet_group_name=self.subnet_group.cache_subnet_group_name,
            security_group_ids=[self.redis_security_group.security_group_id],
            cache_parameter_group_name=self.parameter_group.ref,
            at_rest_encryption_enabled=True,
            transit_encryption_enabled=True,
            auth_token_enabled=False,  # Can enable for additional security
            snapshot_retention_limit=5,  # Keep 5 days of backups
            snapshot_window="03:00-05:00",  # UTC
            preferred_maintenance_window="sun:05:00-sun:07:00",  # UTC
            auto_minor_version_upgrade=True,
            tags=[
                {
                    "key": "Name",
                    "value": "AI-SW-PM-Redis"
                },
                {
                    "key": "Purpose",
                    "value": "Dashboard and Report Caching"
                }
            ]
        )

        # Add dependency
        self.redis_replication_group.add_dependency(self.subnet_group)
        self.redis_replication_group.add_dependency(self.parameter_group)

        # Export Redis endpoint for Lambda functions
        self.redis_endpoint = self.redis_replication_group.attr_primary_end_point_address
        self.redis_port = self.redis_replication_group.attr_primary_end_point_port

        CfnOutput(
            self,
            "RedisEndpoint",
            value=self.redis_endpoint,
            description="ElastiCache Redis primary endpoint",
            export_name="RedisEndpoint"
        )

        CfnOutput(
            self,
            "RedisPort",
            value=self.redis_port,
            description="ElastiCache Redis port",
            export_name="RedisPort"
        )

