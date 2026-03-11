"""
Prediction Service Lambda Handler

Handles prediction requests for project delays and workload imbalances.
"""

import json
import logging
import os
import boto3
from datetime import datetime
from typing import Dict, Any, List
from decimal import Decimal

# Add parent directory to path for local imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.logger import setup_logger
from shared.decorators import handle_errors, validate_tenant
from shared.database import get_db_connection
from shared.errors import ValidationError, NotFoundError

logger = setup_logger(__name__)

# AWS clients
dynamodb = boto3.resource('dynamodb')
sagemaker_runtime = boto3.client('sagemaker-runtime')

# Environment variables
PREDICTIONS_TABLE = os.environ.get('PREDICTIONS_TABLE', 'Predictions')
RISKS_TABLE = os.environ.get('RISKS_TABLE', 'Risks')
DELAY_CLASSIFIER_ENDPOINT = os.environ.get('DELAY_CLASSIFIER_ENDPOINT', '')
DELAY_REGRESSOR_ENDPOINT = os.environ.get('DELAY_REGRESSOR_ENDPOINT', '')
WORKLOAD_ENDPOINT = os.environ.get('WORKLOAD_ENDPOINT', '')


class PredictionService:
    """Service for generating ML predictions"""
    
    def __init__(self):
        self.predictions_table = dynamodb.Table(PREDICTIONS_TABLE)
        self.risks_table = dynamodb.Table(RISKS_TABLE)
        self.db_connection = None
    
    def get_db_connection(self):
        """Get database connection"""
        if not self.db_connection:
            self.db_connection = get_db_connection()
        return self.db_connection
    
    def extract_features_from_project(self, project_id: str, tenant_id: str) -> Dict[str, float]:
        """
        Extract features from current project data
        
        Args:
            project_id: Project ID
            tenant_id: Tenant ID
            
        Returns:
            Dictionary of features
        """
        logger.info(f"Extracting features for project: {project_id}")
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get sprint metrics
        cursor.execute("""
            SELECT 
                velocity,
                completion_rate
            FROM sprints
            WHERE project_id = %s
            ORDER BY start_date DESC
            LIMIT 4
        """, (project_id,))
        
        sprints = cursor.fetchall()
        
        if len(sprints) >= 4:
            velocities = [float(s[0]) if s[0] else 0 for s in sprints]
            completion_rates = [float(s[1]) if s[1] else 0 for s in sprints]
            
            import numpy as np
            velocity_trend = np.polyfit(range(len(velocities)), velocities, 1)[0] if len(velocities) > 1 else 0
            avg_velocity = np.mean(velocities)
            velocity_std = np.std(velocities)
            avg_completion_rate = np.mean(completion_rates)
        else:
            velocity_trend = 0
            avg_velocity = 0
            velocity_std = 0
            avg_completion_rate = 0
        
        # Get backlog metrics
        cursor.execute("""
            SELECT 
                COUNT(*) as total_items,
                COUNT(CASE WHEN status = 'OPEN' THEN 1 END) as open_items,
                AVG(age_days) as avg_age
            FROM backlog_items
            WHERE project_id = %s
        """, (project_id,))
        
        backlog = cursor.fetchone()
        total_backlog = backlog[0] if backlog else 0
        open_backlog = backlog[1] if backlog else 0
        backlog_ratio = open_backlog / total_backlog if total_backlog > 0 else 0
        avg_age = float(backlog[2]) if backlog and backlog[2] else 0
        
        # Get milestone metrics
        cursor.execute("""
            SELECT 
                COUNT(*) as total_milestones,
                COUNT(CASE WHEN status = 'COMPLETED' THEN 1 END) as completed,
                COUNT(CASE WHEN status = 'AT_RISK' THEN 1 END) as at_risk,
                COUNT(CASE WHEN status = 'DELAYED' THEN 1 END) as delayed,
                AVG(completion_percentage) as avg_completion
            FROM milestones
            WHERE project_id = %s
        """, (project_id,))
        
        milestones = cursor.fetchone()
        total_milestones = milestones[0] if milestones else 0
        completed_milestones = milestones[1] if milestones else 0
        at_risk_milestones = milestones[2] if milestones else 0
        delayed_milestones = milestones[3] if milestones else 0
        milestone_completion_rate = completed_milestones / total_milestones if total_milestones > 0 else 0
        avg_milestone_completion = float(milestones[4]) if milestones and milestones[4] else 0
        
        # Get dependency metrics
        cursor.execute("""
            SELECT 
                COUNT(*) as total_deps,
                COUNT(CASE WHEN status = 'ACTIVE' THEN 1 END) as active_deps,
                COUNT(CASE WHEN dependency_type = 'BLOCKS' THEN 1 END) as blocking_deps
            FROM dependencies
            WHERE project_id = %s
        """, (project_id,))
        
        deps = cursor.fetchone()
        total_dependencies = deps[0] if deps else 0
        active_dependencies = deps[1] if deps else 0
        blocking_dependencies = deps[2] if deps else 0
        
        cursor.close()
        
        features = {
            'velocity_trend': velocity_trend,
            'avg_velocity': avg_velocity,
            'velocity_std': velocity_std,
            'avg_completion_rate': avg_completion_rate,
            'total_backlog': total_backlog,
            'open_backlog': open_backlog,
            'backlog_ratio': backlog_ratio,
            'avg_backlog_age': avg_age,
            'total_milestones': total_milestones,
            'completed_milestones': completed_milestones,
            'at_risk_milestones': at_risk_milestones,
            'delayed_milestones': delayed_milestones,
            'milestone_completion_rate': milestone_completion_rate,
            'avg_milestone_completion': avg_milestone_completion,
            'total_dependencies': total_dependencies,
            'active_dependencies': active_dependencies,
            'blocking_dependencies': blocking_dependencies
        }
        
        logger.info(f"Extracted features: {features}")
        
        return features
    
    def invoke_sagemaker_endpoint(self, endpoint_name: str, features: Dict[str, float]) -> Dict[str, Any]:
        """
        Invoke SageMaker endpoint for prediction
        
        Args:
            endpoint_name: Endpoint name
            features: Feature dictionary
            
        Returns:
            Prediction result
        """
        logger.info(f"Invoking endpoint: {endpoint_name}")
        
        # Prepare features as CSV (order matters - must match training order)
        feature_order = [
            'velocity_trend', 'avg_velocity', 'velocity_std', 'avg_completion_rate',
            'total_backlog', 'open_backlog', 'backlog_ratio', 'avg_backlog_age',
            'total_milestones', 'completed_milestones', 'at_risk_milestones', 'delayed_milestones',
            'milestone_completion_rate', 'avg_milestone_completion',
            'total_dependencies', 'active_dependencies', 'blocking_dependencies'
        ]
        
        feature_values = [str(features.get(f, 0)) for f in feature_order]
        payload = ','.join(feature_values)
        
        try:
            response = sagemaker_runtime.invoke_endpoint(
                EndpointName=endpoint_name,
                ContentType='text/csv',
                Body=payload
            )
            
            result = json.loads(response['Body'].read().decode())
            logger.info(f"Endpoint response: {result}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error invoking endpoint: {e}")
            raise
    
    def predict_delay(self, project_id: str, tenant_id: str) -> Dict[str, Any]:
        """
        Predict delay probability for a project
        
        Args:
            project_id: Project ID
            tenant_id: Tenant ID
            
        Returns:
            Prediction result
        """
        logger.info(f"Predicting delay for project: {project_id}")
        
        # Extract features
        features = self.extract_features_from_project(project_id, tenant_id)
        
        # Invoke classifier
        classifier_result = self.invoke_sagemaker_endpoint(DELAY_CLASSIFIER_ENDPOINT, features)
        
        # Get probability (XGBoost returns probability for positive class)
        delay_probability = float(classifier_result) * 100  # Convert to percentage
        
        # If high probability, also get delay days estimate
        predicted_delay_days = None
        if delay_probability > 60 and DELAY_REGRESSOR_ENDPOINT:
            try:
                regressor_result = self.invoke_sagemaker_endpoint(DELAY_REGRESSOR_ENDPOINT, features)
                predicted_delay_days = float(regressor_result)
            except Exception as e:
                logger.warning(f"Could not get delay days estimate: {e}")
        
        # Calculate confidence score (simplified - based on feature completeness)
        feature_completeness = sum(1 for v in features.values() if v > 0) / len(features)
        confidence_score = min(0.95, feature_completeness)
        
        # Identify key factors
        factors = self._identify_prediction_factors(features, delay_probability)
        
        prediction = {
            'project_id': project_id,
            'delay_probability': round(delay_probability, 2),
            'confidence_score': round(confidence_score, 2),
            'predicted_delay_days': round(predicted_delay_days, 1) if predicted_delay_days else None,
            'factors': factors,
            'generated_at': datetime.utcnow().isoformat()
        }
        
        # Store prediction
        self._store_prediction(tenant_id, prediction, 'DELAY')
        
        # Generate risk alert if probability > 60%
        if delay_probability > 60:
            self._generate_delay_risk_alert(tenant_id, project_id, prediction)
        
        logger.info(f"Delay prediction complete: {delay_probability}%")
        
        return prediction
    
    def _identify_prediction_factors(self, features: Dict[str, float], delay_probability: float) -> List[Dict[str, Any]]:
        """Identify key factors contributing to prediction"""
        factors = []
        
        # Velocity trend
        if features['velocity_trend'] < -2:
            factors.append({
                'factor': 'Declining Velocity',
                'impact': -0.3,
                'description': 'Team velocity is declining significantly'
            })
        
        # Backlog growth
        if features['backlog_ratio'] > 0.7:
            factors.append({
                'factor': 'High Backlog',
                'impact': -0.2,
                'description': 'Large open backlog relative to total items'
            })
        
        # Milestone delays
        if features['delayed_milestones'] > 0:
            factors.append({
                'factor': 'Delayed Milestones',
                'impact': -0.4,
                'description': f"{int(features['delayed_milestones'])} milestones already delayed"
            })
        
        # Dependencies
        if features['blocking_dependencies'] > 5:
            factors.append({
                'factor': 'Complex Dependencies',
                'impact': -0.15,
                'description': 'High number of blocking dependencies'
            })
        
        return factors
    
    def _store_prediction(self, tenant_id: str, prediction: Dict[str, Any], prediction_type: str):
        """Store prediction in DynamoDB"""
        import uuid
        
        prediction_id = str(uuid.uuid4())
        
        item = {
            'PK': f"TENANT#{tenant_id}",
            'SK': f"PREDICTION#{prediction_id}",
            'prediction_id': prediction_id,
            'project_id': prediction['project_id'],
            'prediction_type': prediction_type,
            'prediction_value': Decimal(str(prediction['delay_probability'])),
            'confidence_score': Decimal(str(prediction['confidence_score'])),
            'factors': prediction['factors'],
            'generated_at': prediction['generated_at'],
            'GSI1PK': f"PROJECT#{prediction['project_id']}#TYPE#{prediction_type}",
            'GSI1SK': f"PREDICTION#{prediction['generated_at']}"
        }
        
        if prediction.get('predicted_delay_days'):
            item['predicted_delay_days'] = Decimal(str(prediction['predicted_delay_days']))
        
        self.predictions_table.put_item(Item=item)
        logger.info(f"Stored prediction: {prediction_id}")
    
    def _generate_delay_risk_alert(self, tenant_id: str, project_id: str, prediction: Dict[str, Any]):
        """Generate risk alert for high delay probability"""
        import uuid
        
        risk_id = str(uuid.uuid4())
        
        severity = 'CRITICAL' if prediction['delay_probability'] > 80 else 'HIGH'
        
        description = f"Project has {prediction['delay_probability']}% probability of delay"
        if prediction.get('predicted_delay_days'):
            description += f" (estimated {prediction['predicted_delay_days']} days)"
        
        risk = {
            'PK': f"TENANT#{tenant_id}",
            'SK': f"RISK#{risk_id}",
            'risk_id': risk_id,
            'project_id': project_id,
            'type': 'DELAY_PREDICTION',
            'severity': severity,
            'title': 'High Delay Probability Detected',
            'description': description,
            'detected_at': datetime.utcnow().isoformat(),
            'status': 'ACTIVE',
            'metrics': {
                'delay_probability': Decimal(str(prediction['delay_probability'])),
                'confidence': Decimal(str(prediction['confidence_score']))
            },
            'GSI1PK': f"PROJECT#{project_id}",
            'GSI1SK': f"RISK#{datetime.utcnow().isoformat()}",
            'GSI2PK': f"TENANT#{tenant_id}#SEVERITY#{severity}",
            'GSI2SK': f"RISK#{datetime.utcnow().isoformat()}"
        }
        
        self.risks_table.put_item(Item=risk)
        logger.info(f"Generated delay risk alert: {risk_id}")


# Lambda handler functions
prediction_service = PredictionService()


@handle_errors
@validate_tenant
def predict_delay_handler(event, context):
    """
    Lambda handler for delay prediction
    
    POST /predictions/delay-probability
    """
    logger.info("Handling delay prediction request")
    
    # Parse request
    body = json.loads(event.get('body', '{}'))
    project_id = body.get('project_id')
    
    if not project_id:
        raise ValidationError("project_id is required")
    
    # Get tenant ID from authorizer context
    tenant_id = event['requestContext']['authorizer']['tenantId']
    
    # Generate prediction
    prediction = prediction_service.predict_delay(project_id, tenant_id)
    
    return {
        'statusCode': 200,
        'body': json.dumps(prediction, default=str)
    }


@handle_errors
@validate_tenant
def get_prediction_history_handler(event, context):
    """
    Lambda handler for getting prediction history
    
    GET /predictions/history
    """
    logger.info("Handling get prediction history request")
    
    # Get parameters
    params = event.get('queryStringParameters', {}) or {}
    project_id = params.get('project_id')
    prediction_type = params.get('prediction_type', 'DELAY')
    
    if not project_id:
        raise ValidationError("project_id is required")
    
    # Get tenant ID from authorizer context
    tenant_id = event['requestContext']['authorizer']['tenantId']
    
    # Query predictions
    response = prediction_service.predictions_table.query(
        IndexName='GSI1',
        KeyConditionExpression='GSI1PK = :pk',
        ExpressionAttributeValues={
            ':pk': f"PROJECT#{project_id}#TYPE#{prediction_type}"
        },
        ScanIndexForward=False,
        Limit=100
    )
    
    predictions = response.get('Items', [])
    
    # Convert Decimal to float
    for pred in predictions:
        if 'prediction_value' in pred:
            pred['prediction_value'] = float(pred['prediction_value'])
        if 'confidence_score' in pred:
            pred['confidence_score'] = float(pred['confidence_score'])
        if 'predicted_delay_days' in pred:
            pred['predicted_delay_days'] = float(pred['predicted_delay_days'])
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'predictions': predictions,
            'count': len(predictions)
        }, default=str)
    }



@handle_errors
@validate_tenant
def predict_workload_handler(event, context):
    """
    Lambda handler for workload imbalance prediction
    
    POST /predictions/workload-imbalance
    """
    logger.info("Handling workload prediction request")
    
    # Parse request
    body = json.loads(event.get('body', '{}'))
    project_id = body.get('project_id')
    
    if not project_id:
        raise ValidationError("project_id is required")
    
    # Get tenant ID from authorizer context
    tenant_id = event['requestContext']['authorizer']['tenantId']
    
    # Import workload prediction service
    from prediction.workload_prediction import WorkloadPredictionService
    
    workload_endpoint = os.environ.get('WORKLOAD_ENDPOINT', '')
    if not workload_endpoint:
        raise ValidationError("Workload prediction endpoint not configured")
    
    # Generate prediction
    workload_service = WorkloadPredictionService(workload_endpoint)
    db_conn = prediction_service.get_db_connection()
    
    prediction = workload_service.predict_workload_imbalance(project_id, db_conn)
    
    # Store prediction
    prediction_service._store_prediction(tenant_id, {
        'project_id': project_id,
        'delay_probability': prediction['imbalance_score'],  # Reuse field for imbalance score
        'confidence_score': prediction['confidence_score'],
        'generated_at': prediction['generated_at']
    }, 'WORKLOAD')
    
    # Generate risk alert if imbalance > 40%
    if prediction['imbalance_score'] > 40:
        _generate_workload_risk_alert(tenant_id, project_id, prediction)
    
    return {
        'statusCode': 200,
        'body': json.dumps(prediction, default=str)
    }


def _generate_workload_risk_alert(tenant_id: str, project_id: str, prediction: Dict[str, Any]):
    """Generate risk alert for high workload imbalance"""
    import uuid
    
    risk_id = str(uuid.uuid4())
    
    severity = 'HIGH' if prediction['imbalance_score'] > 60 else 'MEDIUM'
    
    description = f"Project has {prediction['imbalance_score']}% workload imbalance. "
    description += f"{len(prediction['overallocated_resources'])} overallocated, "
    description += f"{len(prediction['underallocated_resources'])} underallocated team members."
    
    risks_table = dynamodb.Table(RISKS_TABLE)
    
    risk = {
        'PK': f"TENANT#{tenant_id}",
        'SK': f"RISK#{risk_id}",
        'risk_id': risk_id,
        'project_id': project_id,
        'type': 'WORKLOAD_IMBALANCE',
        'severity': severity,
        'title': 'Workload Imbalance Detected',
        'description': description,
        'detected_at': datetime.utcnow().isoformat(),
        'status': 'ACTIVE',
        'metrics': {
            'imbalance_score': Decimal(str(prediction['imbalance_score'])),
            'confidence': Decimal(str(prediction['confidence_score']))
        },
        'recommendations': prediction['recommendations'],
        'GSI1PK': f"PROJECT#{project_id}",
        'GSI1SK': f"RISK#{datetime.utcnow().isoformat()}",
        'GSI2PK': f"TENANT#{tenant_id}#SEVERITY#{severity}",
        'GSI2SK': f"RISK#{datetime.utcnow().isoformat()}"
    }
    
    risks_table.put_item(Item=risk)
    logger.info(f"Generated workload risk alert: {risk_id}")
