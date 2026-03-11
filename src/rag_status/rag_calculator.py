"""RAG status calculation logic."""

import sys
import os
from typing import Dict, Any, Optional
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logger import get_logger
from shared.errors import DataError

logger = get_logger()

# Default RAG thresholds
DEFAULT_THRESHOLDS = {
    'green': 80,
    'amber': 60
}


def get_tenant_thresholds(tenant_id: str) -> Dict[str, int]:
    """
    Get custom RAG thresholds for a tenant if configured, otherwise return defaults.
    
    Validates: Property 61 - Custom Threshold Application
    
    Args:
        tenant_id: Tenant ID
        
    Returns:
        Dictionary with RAG thresholds (green, amber)
    """
    # TODO: Query tenant configuration from DynamoDB
    # For now, return default thresholds
    # In production, this would query a tenant_config table or DynamoDB
    return DEFAULT_THRESHOLDS.copy()


def determine_rag_status(
    health_score: int,
    custom_thresholds: Optional[Dict[str, int]] = None
) -> str:
    """
    Determine RAG status based on health score and thresholds.
    
    Validates: Property 60 - RAG Status Determination
    
    Args:
        health_score: Health score (0-100)
        custom_thresholds: Optional custom thresholds (if None, uses defaults)
        
    Returns:
        RAG status: 'GREEN', 'AMBER', or 'RED'
    """
    thresholds = custom_thresholds or DEFAULT_THRESHOLDS
    
    if health_score >= thresholds['green']:
        return 'GREEN'
    elif health_score >= thresholds['amber']:
        return 'AMBER'
    else:
        return 'RED'


def calculate_rag_status(
    project_id: str,
    tenant_id: str,
    health_score: int,
    custom_thresholds: Optional[Dict[str, int]] = None
) -> Dict[str, Any]:
    """
    Calculate RAG status for a project based on health score.
    
    Validates:
    - Property 60: RAG Status Determination
    - Property 61: Custom Threshold Application
    
    Args:
        project_id: Project ID
        tenant_id: Tenant ID
        health_score: Health score (0-100)
        custom_thresholds: Optional custom thresholds (if None, uses tenant or default thresholds)
        
    Returns:
        Dictionary with:
        - rag_status: 'GREEN', 'AMBER', or 'RED'
        - health_score: Health score used
        - thresholds: Thresholds applied
        - calculated_at: Timestamp
    """
    logger.info(
        f"Calculating RAG status",
        extra={
            "project_id": project_id,
            "tenant_id": tenant_id,
            "health_score": health_score
        }
    )
    
    # Get thresholds
    if custom_thresholds:
        thresholds = custom_thresholds
    else:
        thresholds = get_tenant_thresholds(tenant_id)
    
    # Determine RAG status
    rag_status = determine_rag_status(health_score, thresholds)
    
    result = {
        'rag_status': rag_status,
        'health_score': health_score,
        'thresholds': thresholds,
        'calculated_at': datetime.utcnow().isoformat()
    }
    
    logger.info(
        f"RAG status calculated",
        extra={
            "project_id": project_id,
            "rag_status": rag_status,
            "health_score": health_score
        }
    )
    
    return result
