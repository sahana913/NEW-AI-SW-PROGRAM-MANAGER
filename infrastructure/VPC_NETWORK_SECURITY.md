# VPC and Network Security Configuration

**Status**: ✅ Complete

**Validates**: 
- Requirement 24.2 - THE Platform SHALL encrypt all data in transit using TLS 1.2 or higher
- Requirement 24.5 - THE Platform SHALL implement IAM-based access control for all AWS resources

## Overview

This document describes the VPC and network security implementation for the AI SW Program Manager platform. The implementation follows AWS best practices for network isolation, least privilege security groups, and comprehensive network monitoring through VPC Flow Logs.

## What Was Implemented

### 1. VPC Architecture

**Multi-Tier VPC Design**:
- **Public Subnets**: Host NAT Gateway for outbound internet access
- **Private Subnets with Egress**: Host Lambda functions that need internet access
- **Isolated Subnets**: Host RDS PostgreSQL with no internet access

**Configuration**:
```python
vpc = ec2.Vpc(
    self,
    "VPC",
    max_azs=2,                    # Multi-AZ for high availability
    nat_gateways=1,               # Single NAT Gateway for cost optimization
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
```

### 2. Security Groups with Least Privilege

**RDS Security Group**:
- **Ingress**: PostgreSQL port 5432 only from Lambda security group
- **Egress**: No outbound traffic allowed
- **Purpose**: Ensures RDS can only be accessed by authorized Lambda functions

**OpenSearch Security Group**:
- **Ingress**: HTTPS port 443 only from Lambda security group
- **Egress**: No outbound traffic allowed
- **Purpose**: Ensures OpenSearch can only be accessed by authorized Lambda functions

**Lambda Security Group**:
- **Ingress**: No inbound traffic
- **Egress**: All outbound traffic allowed (for AWS service access)
- **Purpose**: Allows Lambda functions to access RDS, OpenSearch, and AWS services

### 3. VPC Flow Logs

**Dual Destination Configuration**:

**CloudWatch Logs** (Real-time monitoring):
- Retention: 30 days
- Purpose: Real-time security analysis and alerting
- Log group: `/aws/vpc/flowlogs`

**S3 Bucket** (Long-term storage):
- Lifecycle: Transition to Glacier after 90 days, delete after 365 days
- Purpose: Compliance and long-term forensic analysis
- Encryption: S3-managed encryption
- Key prefix: `vpc-flow-logs/`

**Traffic Captured**:
- ALL traffic (accepted, rejected, and all)
- Source/destination IP addresses
- Source/destination ports
- Protocol
- Packet and byte counts
- Action (ACCEPT or REJECT)

### 4. Network Isolation

**RDS PostgreSQL**:
- Deployed in **isolated subnets** (no internet access)
- Multi-AZ deployment for high availability
- Accessible only through Lambda functions in private subnets
- Encryption in transit enforced (TLS 1.2+)
- Encryption at rest with KMS

**OpenSearch**:
- Deployed in **private subnets with egress**
- Multi-AZ deployment across 2 availability zones
- Accessible only through Lambda functions
- HTTPS enforced (TLS 1.2+)
- Node-to-node encryption enabled
- Encryption at rest with KMS

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      Internet Gateway                        │
└────────────────────────────┬────────────────────────────────┘
                             │
┌─────────────────────────────────────────────────────────────┐
│                      Public Subnet                           │
│                      (NAT Gateway)                           │
└────────────────────────────┬────────────────────────────────┘
                             │
┌─────────────────────────────────────────────────────────────┐
│                   Private Subnet (with Egress)               │
│              (Lambda Functions, OpenSearch)                  │
│                                                              │
│  ┌──────────────┐         ┌──────────────┐                 │
│  │   Lambda     │────────▶│  OpenSearch  │                 │
│  │  Functions   │         │   Domain     │                 │
│  └──────┬───────┘         └──────────────┘                 │
│         │                                                    │
└─────────┼────────────────────────────────────────────────────┘
          │
          │ (PostgreSQL 5432)
          │
┌─────────▼────────────────────────────────────────────────────┐
│                   Isolated Subnet (No Internet)              │
│                      (RDS PostgreSQL)                        │
│                                                              │
│                  ┌──────────────┐                           │
│                  │     RDS      │                           │
│                  │  PostgreSQL  │                           │
│                  └──────────────┘                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘

VPC Flow Logs ──────┬──────▶ CloudWatch Logs (30 days)
                    └──────▶ S3 Bucket (365 days)
```

## Security Features

### 1. Network Segmentation
- **Three-tier architecture**: Public, Private, and Isolated subnets
- **Least privilege access**: Each tier has minimal required connectivity
- **No direct internet access**: RDS in isolated subnet, OpenSearch in private subnet

### 2. Security Group Rules
- **Stateful firewall**: Automatic return traffic handling
- **Explicit allow rules**: Only required ports and protocols allowed
- **Source-based restrictions**: Access limited to specific security groups
- **No broad CIDR ranges**: No 0.0.0.0/0 rules for sensitive resources

### 3. Encryption in Transit
- **RDS**: TLS 1.2+ enforced for all connections
- **OpenSearch**: HTTPS enforced, TLS 1.2+ security policy
- **Lambda to RDS**: Encrypted PostgreSQL connections
- **Lambda to OpenSearch**: HTTPS API calls

### 4. Network Monitoring
- **VPC Flow Logs**: Capture all network traffic metadata
- **CloudWatch integration**: Real-time log analysis
- **S3 archival**: Long-term compliance storage
- **Anomaly detection**: Can be integrated with CloudWatch Insights

## Deployment

### Prerequisites
1. AWS CDK installed and configured
2. Appropriate AWS permissions for VPC, EC2, and CloudWatch
3. Existing encryption keys (created by encryption stack)

### Stack Dependencies
```
VpcNetworkSecurityStack (base)
    ├── DatabaseStack (depends on VPC and RDS security group)
    ├── StorageStack (depends on VPC and OpenSearch security group)
    └── CacheStack (depends on VPC)
```

### Deployment Order
1. Deploy VpcNetworkSecurityStack first
2. Deploy DatabaseStack and StorageStack (can be parallel)
3. Deploy remaining stacks

### CDK Commands
```bash
# Synthesize CloudFormation template
cdk synth AISWProgramManager-VPCNetworkSecurity

# Deploy VPC and network security
cdk deploy AISWProgramManager-VPCNetworkSecurity

# Deploy dependent stacks
cdk deploy AISWProgramManager-Database
cdk deploy AISWProgramManager-Storage
```

## Configuration

### Environment Variables
No environment variables required for VPC stack.

### Customization Options

**NAT Gateway Count**:
```python
# For high availability (higher cost)
nat_gateways=2  # One per AZ

# For cost optimization (current)
nat_gateways=1  # Single NAT Gateway
```

**VPC Flow Logs Retention**:
```python
# CloudWatch retention
retention=logs.RetentionDays.ONE_MONTH  # Current: 30 days

# S3 lifecycle
expiration=Duration.days(365)  # Current: 1 year
```

**Subnet CIDR Masks**:
```python
cidr_mask=24  # Current: /24 (256 IPs per subnet)
# Adjust based on expected resource count
```

## Monitoring and Alerts

### VPC Flow Logs Analysis

**CloudWatch Insights Queries**:

1. **Top Talkers** (Most active IPs):
```
fields @timestamp, srcAddr, dstAddr, bytes
| stats sum(bytes) as totalBytes by srcAddr
| sort totalBytes desc
| limit 10
```

2. **Rejected Connections** (Security group blocks):
```
fields @timestamp, srcAddr, dstAddr, srcPort, dstPort, action
| filter action = "REJECT"
| stats count() by srcAddr, dstAddr, dstPort
| sort count desc
```

3. **Unusual Port Activity**:
```
fields @timestamp, srcAddr, dstAddr, dstPort, protocol
| filter dstPort not in [443, 5432, 6379]
| stats count() by dstPort, protocol
```

### Recommended CloudWatch Alarms

1. **High Rejected Connection Rate**:
   - Metric: VPC Flow Logs rejected connections
   - Threshold: > 100 per minute
   - Action: Alert security team

2. **Unusual Traffic Patterns**:
   - Metric: Bytes transferred
   - Threshold: > 10 GB per hour
   - Action: Investigate potential data exfiltration

3. **NAT Gateway Errors**:
   - Metric: ErrorPortAllocation
   - Threshold: > 0
   - Action: Consider scaling NAT Gateway

## Cost Optimization

### Current Configuration Costs (Estimated)

**VPC Components**:
- VPC: Free
- Subnets: Free
- Route tables: Free
- Internet Gateway: Free
- NAT Gateway: ~$32/month (single NAT Gateway)
- NAT Gateway data transfer: ~$0.045/GB

**VPC Flow Logs**:
- CloudWatch Logs ingestion: ~$0.50/GB
- CloudWatch Logs storage: ~$0.03/GB/month
- S3 storage: ~$0.023/GB/month (Standard)
- S3 Glacier: ~$0.004/GB/month (after 90 days)

**Total Estimated Monthly Cost**: ~$50-100 (depending on traffic volume)

### Cost Optimization Strategies

1. **Single NAT Gateway**: Current configuration uses 1 NAT Gateway instead of 2
2. **VPC Flow Logs Sampling**: Can enable sampling to reduce log volume
3. **S3 Lifecycle Policies**: Automatic transition to Glacier after 90 days
4. **CloudWatch Logs Retention**: 30-day retention instead of indefinite

## Security Best Practices

### ✅ Implemented
- [x] Multi-AZ deployment for high availability
- [x] Private subnets for sensitive resources (RDS, OpenSearch)
- [x] Isolated subnet for RDS (no internet access)
- [x] Least privilege security group rules
- [x] VPC Flow Logs enabled for all traffic
- [x] Encryption in transit (TLS 1.2+)
- [x] DNS resolution enabled
- [x] No public access to databases

### 🔄 Future Enhancements
- [ ] VPC Endpoints for AWS services (reduce NAT Gateway costs)
- [ ] Network ACLs for additional subnet-level security
- [ ] AWS Network Firewall for advanced threat protection
- [ ] VPC Flow Logs analysis with Amazon Detective
- [ ] Automated security group rule auditing

## Compliance Mapping

| Requirement | Implementation | Validation |
|-------------|----------------|------------|
| 24.2 - Encrypt data in transit | TLS 1.2+ enforced for RDS and OpenSearch | Stack configuration |
| 24.5 - IAM-based access control | Security groups, VPC isolation | Flow logs, security group rules |
| Network isolation | Private/isolated subnets | VPC configuration |
| Least privilege | Minimal security group rules | Security group audit |
| Monitoring | VPC Flow Logs to CloudWatch and S3 | Flow logs enabled |

## Troubleshooting

### Issue: Lambda Cannot Connect to RDS

**Symptoms**: Connection timeout errors from Lambda to RDS

**Solutions**:
1. Verify Lambda is in the same VPC as RDS
2. Check Lambda security group is allowed in RDS security group
3. Verify RDS is in isolated subnet
4. Check route tables for private subnet

### Issue: OpenSearch Connection Timeout

**Symptoms**: Lambda cannot reach OpenSearch domain

**Solutions**:
1. Verify OpenSearch is in private subnet with egress
2. Check Lambda security group is allowed in OpenSearch security group
3. Verify NAT Gateway is functioning
4. Check OpenSearch domain access policies

### Issue: High NAT Gateway Costs

**Symptoms**: Unexpected NAT Gateway data transfer charges

**Solutions**:
1. Implement VPC Endpoints for AWS services (S3, DynamoDB, etc.)
2. Review Lambda functions for unnecessary internet access
3. Consider caching to reduce external API calls
4. Monitor VPC Flow Logs for high-volume traffic sources

### Issue: VPC Flow Logs Not Appearing

**Symptoms**: No logs in CloudWatch or S3

**Solutions**:
1. Verify IAM role has correct permissions
2. Check CloudWatch log group exists
3. Verify S3 bucket policy allows VPC Flow Logs
4. Wait 10-15 minutes for initial log delivery

## Testing

### Unit Tests

Create `tests/test_vpc_network_security_stack.py`:

```python
import aws_cdk as cdk
from aws_cdk.assertions import Template, Match
from infrastructure.stacks.vpc_network_security_stack import VpcNetworkSecurityStack


def test_vpc_created():
    """Test VPC is created with correct configuration."""
    app = cdk.App()
    stack = VpcNetworkSecurityStack(app, "TestStack")
    template = Template.from_stack(stack)
    
    # Verify VPC exists
    template.resource_count_is("AWS::EC2::VPC", 1)
    
    # Verify subnets
    template.resource_count_is("AWS::EC2::Subnet", 6)  # 2 AZs * 3 types
    
    # Verify NAT Gateway
    template.resource_count_is("AWS::EC2::NatGateway", 1)


def test_security_groups_created():
    """Test security groups are created with least privilege rules."""
    app = cdk.App()
    stack = VpcNetworkSecurityStack(app, "TestStack")
    template = Template.from_stack(stack)
    
    # Verify security groups
    template.resource_count_is("AWS::EC2::SecurityGroup", 3)
    
    # Verify RDS security group has no outbound rules
    template.has_resource_properties("AWS::EC2::SecurityGroup", {
        "GroupDescription": Match.string_like_regexp(".*RDS.*"),
        "SecurityGroupEgress": []
    })


def test_vpc_flow_logs_enabled():
    """Test VPC Flow Logs are enabled to CloudWatch and S3."""
    app = cdk.App()
    stack = VpcNetworkSecurityStack(app, "TestStack")
    template = Template.from_stack(stack)
    
    # Verify Flow Logs
    template.resource_count_is("AWS::EC2::FlowLog", 2)  # CloudWatch + S3
    
    # Verify CloudWatch log group
    template.has_resource_properties("AWS::Logs::LogGroup", {
        "LogGroupName": "/aws/vpc/flowlogs",
        "RetentionInDays": 30
    })
    
    # Verify S3 bucket for flow logs
    template.has_resource_properties("AWS::S3::Bucket", {
        "BucketEncryption": {
            "ServerSideEncryptionConfiguration": Match.any_value()
        }
    })


def test_rds_security_group_rules():
    """Test RDS security group has correct ingress rules."""
    app = cdk.App()
    stack = VpcNetworkSecurityStack(app, "TestStack")
    template = Template.from_stack(stack)
    
    # Verify RDS security group allows PostgreSQL from VPC
    template.has_resource_properties("AWS::EC2::SecurityGroup", {
        "GroupDescription": Match.string_like_regexp(".*RDS.*"),
        "SecurityGroupIngress": [
            {
                "IpProtocol": "tcp",
                "FromPort": 5432,
                "ToPort": 5432
            }
        ]
    })


def test_opensearch_security_group_rules():
    """Test OpenSearch security group has correct ingress rules."""
    app = cdk.App()
    stack = VpcNetworkSecurityStack(app, "TestStack")
    template = Template.from_stack(stack)
    
    # Verify OpenSearch security group allows HTTPS from VPC
    template.has_resource_properties("AWS::EC2::SecurityGroup", {
        "GroupDescription": Match.string_like_regexp(".*OpenSearch.*"),
        "SecurityGroupIngress": [
            {
                "IpProtocol": "tcp",
                "FromPort": 443,
                "ToPort": 443
            }
        ]
    })
```

### Integration Tests

1. **VPC Connectivity Test**:
   - Deploy a test Lambda function in private subnet
   - Verify it can connect to RDS
   - Verify it can connect to OpenSearch
   - Verify it can access internet through NAT Gateway

2. **Security Group Test**:
   - Attempt to connect to RDS from outside VPC (should fail)
   - Attempt to connect to OpenSearch from outside VPC (should fail)
   - Verify Lambda can connect (should succeed)

3. **VPC Flow Logs Test**:
   - Generate test traffic
   - Verify logs appear in CloudWatch within 10 minutes
   - Verify logs appear in S3 within 10 minutes
   - Query logs using CloudWatch Insights

## Summary

The VPC and network security implementation provides:

✅ **Network Isolation**: RDS in isolated subnet, OpenSearch in private subnet
✅ **Least Privilege Security Groups**: Minimal required access rules
✅ **Comprehensive Monitoring**: VPC Flow Logs to CloudWatch and S3
✅ **Encryption in Transit**: TLS 1.2+ enforced for all connections
✅ **High Availability**: Multi-AZ deployment across 2 availability zones
✅ **Cost Optimized**: Single NAT Gateway, lifecycle policies for logs
✅ **Compliance Ready**: Meets requirements 24.2 and 24.5

The platform now has a secure, monitored, and isolated network architecture that follows AWS best practices for multi-tier applications.
