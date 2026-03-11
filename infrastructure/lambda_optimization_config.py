"""
Lambda optimization configuration for performance tuning.

This module provides configuration for:
- Provisioned concurrency for critical functions
- Memory and timeout settings optimized per function
- Lambda layers for shared dependencies
"""

from aws_cdk import Duration

# Critical functions that need provisioned concurrency (Requirement 23.6)
PROVISIONED_CONCURRENCY_CONFIG = {
    "authorizer": 5,  # High traffic, needs fast response
    "dashboard": 3,  # Frequently accessed
    "user_management": 2,  # Moderate traffic
}

# Optimized memory settings per function type (Requirement 23.1, 23.4)
MEMORY_CONFIG = {
    # Lightweight functions (256-512 MB)
    "lightweight": {
        "memory_size": 256,
        "timeout": Duration.seconds(10),
        "functions": ["authorizer", "data_validation", "analysis_trigger"]
    },
    # Standard functions (512-1024 MB)
    "standard": {
        "memory_size": 512,
        "timeout": Duration.seconds(30),
        "functions": ["user_management", "jira_integration", "azure_devops", 
                     "document_upload", "semantic_search", "dashboard"]
    },
    # Memory-intensive functions (1024-2048 MB)
    "memory_intensive": {
        "memory_size": 1024,
        "timeout": Duration.seconds(60),
        "functions": ["risk_detection", "prediction"]
    },
    # Heavy processing functions (2048-3008 MB)
    "heavy_processing": {
        "memory_size": 2048,
        "timeout": Duration.seconds(300),
        "functions": ["document_intelligence", "report_generation", "pdf_export"]
    },
    # Data ingestion functions (512 MB, longer timeout)
    "data_ingestion": {
        "memory_size": 512,
        "timeout": Duration.minutes(5),
        "functions": ["fetch_jira", "fetch_azure_devops", "store_data"]
    }
}

# Lambda layer configuration for shared dependencies
LAMBDA_LAYERS_CONFIG = {
    "common_dependencies": {
        "description": "Common Python dependencies (boto3, requests, etc.)",
        "compatible_runtimes": ["python3.11"],
        "packages": ["boto3", "requests", "urllib3"]
    },
    "data_processing": {
        "description": "Data processing libraries (pandas, numpy)",
        "compatible_runtimes": ["python3.11"],
        "packages": ["pandas", "numpy"]
    },
    "ai_ml": {
        "description": "AI/ML libraries for Bedrock and SageMaker",
        "compatible_runtimes": ["python3.11"],
        "packages": ["anthropic", "sagemaker"]
    }
}
