"""
Model Deployment Module

Deploys trained models to SageMaker endpoints with auto-scaling.
"""

import logging
import boto3
import sagemaker
from sagemaker.model import Model
from sagemaker.predictor import Predictor
from sagemaker.serializers import CSVSerializer
from sagemaker.deserializers import JSONDeserializer
from typing import Dict, Any, Optional
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class ModelDeployment:
    """Deploys and manages SageMaker endpoints"""
    
    def __init__(self, region: str = 'us-east-1'):
        """
        Initialize model deployment
        
        Args:
            region: AWS region
        """
        self.region = region
        self.sagemaker_client = boto3.client('sagemaker', region_name=region)
        self.autoscaling_client = boto3.client('application-autoscaling', region_name=region)
        self.sagemaker_session = sagemaker.Session()
        
        logger.info(f"Initialized model deployment for region: {region}")
    
    def create_model(self,
                    model_data: str,
                    role_arn: str,
                    model_name: Optional[str] = None,
                    container_image: Optional[str] = None) -> str:
        """
        Create SageMaker model
        
        Args:
            model_data: S3 URI to model artifacts
            role_arn: IAM role ARN
            model_name: Optional model name
            container_image: Optional container image URI
            
        Returns:
            Model name
        """
        if not model_name:
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            model_name = f"delay-prediction-{timestamp}"
        
        if not container_image:
            container_image = sagemaker.image_uris.retrieve(
                framework='xgboost',
                region=self.region,
                version='1.5-1'
            )
        
        logger.info(f"Creating model: {model_name}")
        
        try:
            self.sagemaker_client.create_model(
                ModelName=model_name,
                PrimaryContainer={
                    'Image': container_image,
                    'ModelDataUrl': model_data
                },
                ExecutionRoleArn=role_arn
            )
            
            logger.info(f"Model created: {model_name}")
            return model_name
            
        except Exception as e:
            logger.error(f"Error creating model: {e}")
            raise
    
    def create_endpoint_config(self,
                              model_name: str,
                              config_name: Optional[str] = None,
                              instance_type: str = 'ml.m5.large',
                              initial_instance_count: int = 1) -> str:
        """
        Create endpoint configuration
        
        Args:
            model_name: Model name
            config_name: Optional config name
            instance_type: Instance type
            initial_instance_count: Initial instance count
            
        Returns:
            Config name
        """
        if not config_name:
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            config_name = f"delay-prediction-config-{timestamp}"
        
        logger.info(f"Creating endpoint config: {config_name}")
        
        try:
            self.sagemaker_client.create_endpoint_config(
                EndpointConfigName=config_name,
                ProductionVariants=[
                    {
                        'VariantName': 'AllTraffic',
                        'ModelName': model_name,
                        'InitialInstanceCount': initial_instance_count,
                        'InstanceType': instance_type,
                        'InitialVariantWeight': 1.0
                    }
                ]
            )
            
            logger.info(f"Endpoint config created: {config_name}")
            return config_name
            
        except Exception as e:
            logger.error(f"Error creating endpoint config: {e}")
            raise
    
    def create_endpoint(self,
                       config_name: str,
                       endpoint_name: Optional[str] = None) -> str:
        """
        Create SageMaker endpoint
        
        Args:
            config_name: Endpoint config name
            endpoint_name: Optional endpoint name
            
        Returns:
            Endpoint name
        """
        if not endpoint_name:
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            endpoint_name = f"delay-prediction-endpoint-{timestamp}"
        
        logger.info(f"Creating endpoint: {endpoint_name}")
        
        try:
            self.sagemaker_client.create_endpoint(
                EndpointName=endpoint_name,
                EndpointConfigName=config_name
            )
            
            logger.info(f"Endpoint creation initiated: {endpoint_name}")
            logger.info("Waiting for endpoint to be in service...")
            
            # Wait for endpoint to be in service
            waiter = self.sagemaker_client.get_waiter('endpoint_in_service')
            waiter.wait(EndpointName=endpoint_name)
            
            logger.info(f"Endpoint is in service: {endpoint_name}")
            return endpoint_name
            
        except Exception as e:
            logger.error(f"Error creating endpoint: {e}")
            raise
    
    def update_endpoint(self,
                       endpoint_name: str,
                       new_config_name: str):
        """
        Update existing endpoint with new configuration
        
        Args:
            endpoint_name: Endpoint name
            new_config_name: New endpoint config name
        """
        logger.info(f"Updating endpoint {endpoint_name} with config {new_config_name}")
        
        try:
            self.sagemaker_client.update_endpoint(
                EndpointName=endpoint_name,
                EndpointConfigName=new_config_name
            )
            
            logger.info("Waiting for endpoint update to complete...")
            waiter = self.sagemaker_client.get_waiter('endpoint_in_service')
            waiter.wait(EndpointName=endpoint_name)
            
            logger.info(f"Endpoint updated: {endpoint_name}")
            
        except Exception as e:
            logger.error(f"Error updating endpoint: {e}")
            raise
    
    def configure_autoscaling(self,
                             endpoint_name: str,
                             variant_name: str = 'AllTraffic',
                             min_capacity: int = 1,
                             max_capacity: int = 3,
                             target_invocations_per_instance: int = 1000):
        """
        Configure auto-scaling for endpoint
        
        Args:
            endpoint_name: Endpoint name
            variant_name: Variant name
            min_capacity: Minimum instance count
            max_capacity: Maximum instance count
            target_invocations_per_instance: Target invocations per instance
        """
        logger.info(f"Configuring auto-scaling for endpoint: {endpoint_name}")
        
        resource_id = f"endpoint/{endpoint_name}/variant/{variant_name}"
        
        try:
            # Register scalable target
            self.autoscaling_client.register_scalable_target(
                ServiceNamespace='sagemaker',
                ResourceId=resource_id,
                ScalableDimension='sagemaker:variant:DesiredInstanceCount',
                MinCapacity=min_capacity,
                MaxCapacity=max_capacity
            )
            
            logger.info(f"Registered scalable target: {resource_id}")
            
            # Define scaling policy
            self.autoscaling_client.put_scaling_policy(
                PolicyName=f"{endpoint_name}-scaling-policy",
                ServiceNamespace='sagemaker',
                ResourceId=resource_id,
                ScalableDimension='sagemaker:variant:DesiredInstanceCount',
                PolicyType='TargetTrackingScaling',
                TargetTrackingScalingPolicyConfiguration={
                    'TargetValue': float(target_invocations_per_instance),
                    'PredefinedMetricSpecification': {
                        'PredefinedMetricType': 'SageMakerVariantInvocationsPerInstance'
                    },
                    'ScaleInCooldown': 300,
                    'ScaleOutCooldown': 60
                }
            )
            
            logger.info(f"Auto-scaling configured: min={min_capacity}, max={max_capacity}")
            
        except Exception as e:
            logger.error(f"Error configuring auto-scaling: {e}")
            raise
    
    def deploy_model(self,
                    model_data: str,
                    role_arn: str,
                    endpoint_name: Optional[str] = None,
                    instance_type: str = 'ml.m5.large',
                    initial_instance_count: int = 1,
                    enable_autoscaling: bool = True,
                    min_capacity: int = 1,
                    max_capacity: int = 3) -> Dict[str, str]:
        """
        Complete deployment pipeline
        
        Args:
            model_data: S3 URI to model artifacts
            role_arn: IAM role ARN
            endpoint_name: Optional endpoint name
            instance_type: Instance type
            initial_instance_count: Initial instance count
            enable_autoscaling: Enable auto-scaling
            min_capacity: Minimum instance count for auto-scaling
            max_capacity: Maximum instance count for auto-scaling
            
        Returns:
            Dictionary with deployment details
        """
        logger.info("Starting model deployment pipeline")
        
        # Create model
        model_name = self.create_model(model_data, role_arn)
        
        # Create endpoint config
        config_name = self.create_endpoint_config(
            model_name,
            instance_type=instance_type,
            initial_instance_count=initial_instance_count
        )
        
        # Create endpoint
        if not endpoint_name:
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            endpoint_name = f"delay-prediction-endpoint-{timestamp}"
        
        endpoint_name = self.create_endpoint(config_name, endpoint_name)
        
        # Configure auto-scaling
        if enable_autoscaling:
            self.configure_autoscaling(
                endpoint_name,
                min_capacity=min_capacity,
                max_capacity=max_capacity
            )
        
        deployment_info = {
            'model_name': model_name,
            'config_name': config_name,
            'endpoint_name': endpoint_name,
            'instance_type': instance_type,
            'autoscaling_enabled': enable_autoscaling
        }
        
        logger.info(f"Deployment complete: {deployment_info}")
        
        return deployment_info
    
    def delete_endpoint(self, endpoint_name: str):
        """
        Delete endpoint
        
        Args:
            endpoint_name: Endpoint name
        """
        logger.info(f"Deleting endpoint: {endpoint_name}")
        
        try:
            self.sagemaker_client.delete_endpoint(EndpointName=endpoint_name)
            logger.info(f"Endpoint deleted: {endpoint_name}")
        except Exception as e:
            logger.error(f"Error deleting endpoint: {e}")
            raise
    
    def get_endpoint_status(self, endpoint_name: str) -> Dict[str, Any]:
        """
        Get endpoint status
        
        Args:
            endpoint_name: Endpoint name
            
        Returns:
            Dictionary with endpoint status
        """
        try:
            response = self.sagemaker_client.describe_endpoint(EndpointName=endpoint_name)
            
            return {
                'endpoint_name': response['EndpointName'],
                'endpoint_status': response['EndpointStatus'],
                'creation_time': response['CreationTime'].isoformat(),
                'last_modified_time': response['LastModifiedTime'].isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting endpoint status: {e}")
            return {'error': str(e)}
