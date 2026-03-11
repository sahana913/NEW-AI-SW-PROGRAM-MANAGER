"""
Tests for Lambda optimization configuration.

Validates: Requirements 23.1, 23.2, 23.4, 23.6
"""

import pytest
from aws_cdk import Duration
import sys
import os

# Add infrastructure directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../infrastructure'))

from lambda_optimization_config import (
    PROVISIONED_CONCURRENCY_CONFIG,
    MEMORY_CONFIG,
    LAMBDA_LAYERS_CONFIG
)


class TestProvisionedConcurrencyConfig:
    """Test provisioned concurrency configuration."""
    
    def test_critical_functions_have_provisioned_concurrency(self):
        """Verify critical functions have provisioned concurrency configured."""
        # Requirement 23.6: Configure provisioned concurrency for critical functions
        assert "authorizer" in PROVISIONED_CONCURRENCY_CONFIG
        assert "dashboard" in PROVISIONED_CONCURRENCY_CONFIG
        assert "user_management" in PROVISIONED_CONCURRENCY_CONFIG
    
    def test_provisioned_concurrency_values_are_positive(self):
        """Verify all provisioned concurrency values are positive integers."""
        for function_name, concurrency in PROVISIONED_CONCURRENCY_CONFIG.items():
            assert isinstance(concurrency, int)
            assert concurrency > 0
            assert concurrency <= 10  # Reasonable upper limit
    
    def test_authorizer_has_highest_concurrency(self):
        """Verify authorizer has highest provisioned concurrency (highest traffic)."""
        authorizer_concurrency = PROVISIONED_CONCURRENCY_CONFIG["authorizer"]
        for function_name, concurrency in PROVISIONED_CONCURRENCY_CONFIG.items():
            if function_name != "authorizer":
                assert authorizer_concurrency >= concurrency


class TestMemoryConfig:
    """Test memory and timeout configuration."""
    
    def test_all_config_types_have_required_fields(self):
        """Verify all configuration types have memory_size, timeout, and functions."""
        for config_type, config in MEMORY_CONFIG.items():
            assert "memory_size" in config
            assert "timeout" in config
            assert "functions" in config
    
    def test_memory_sizes_are_valid(self):
        """Verify memory sizes are valid Lambda values (128-10240 MB)."""
        # Requirement 23.4: Configure appropriate memory settings
        valid_memory_sizes = [128, 256, 512, 1024, 1536, 2048, 3008, 4096, 5120, 6144, 7168, 8192, 9216, 10240]
        
        for config_type, config in MEMORY_CONFIG.items():
            memory_size = config["memory_size"]
            assert memory_size in valid_memory_sizes, f"{config_type} has invalid memory size: {memory_size}"
    
    def test_timeouts_are_valid(self):
        """Verify timeouts are valid Duration objects."""
        # Requirement 23.4: Configure appropriate timeout settings
        for config_type, config in MEMORY_CONFIG.items():
            timeout = config["timeout"]
            assert isinstance(timeout, Duration)
    
    def test_lightweight_functions_have_minimal_resources(self):
        """Verify lightweight functions have minimal memory and timeout."""
        lightweight_config = MEMORY_CONFIG["lightweight"]
        assert lightweight_config["memory_size"] == 256
        assert lightweight_config["timeout"].to_seconds() == 10
    
    def test_heavy_processing_functions_have_maximum_resources(self):
        """Verify heavy processing functions have high memory and long timeout."""
        heavy_config = MEMORY_CONFIG["heavy_processing"]
        assert heavy_config["memory_size"] >= 2048
        assert heavy_config["timeout"].to_seconds() == 300
    
    def test_no_duplicate_functions_across_configs(self):
        """Verify each function appears in only one configuration category."""
        all_functions = []
        for config_type, config in MEMORY_CONFIG.items():
            all_functions.extend(config["functions"])
        
        # Check for duplicates
        assert len(all_functions) == len(set(all_functions)), "Duplicate functions found in config"
    
    def test_critical_functions_are_configured(self):
        """Verify critical functions have memory configuration."""
        critical_functions = ["authorizer", "dashboard", "user_management", 
                            "risk_detection", "prediction", "document_intelligence"]
        
        all_configured_functions = []
        for config_type, config in MEMORY_CONFIG.items():
            all_configured_functions.extend(config["functions"])
        
        for function in critical_functions:
            assert function in all_configured_functions, f"{function} not configured"


class TestLambdaLayersConfig:
    """Test Lambda layers configuration."""
    
    def test_all_layers_have_required_fields(self):
        """Verify all layers have description, compatible_runtimes, and packages."""
        # Requirement 23.2: Use Lambda layers to reduce package size
        for layer_name, layer_config in LAMBDA_LAYERS_CONFIG.items():
            assert "description" in layer_config
            assert "compatible_runtimes" in layer_config
            assert "packages" in layer_config
    
    def test_layers_use_python_311(self):
        """Verify all layers are compatible with Python 3.11."""
        for layer_name, layer_config in LAMBDA_LAYERS_CONFIG.items():
            assert "python3.11" in layer_config["compatible_runtimes"]
    
    def test_common_layer_exists(self):
        """Verify common dependencies layer exists."""
        assert "common_dependencies" in LAMBDA_LAYERS_CONFIG
    
    def test_layers_have_packages(self):
        """Verify all layers have at least one package."""
        for layer_name, layer_config in LAMBDA_LAYERS_CONFIG.items():
            assert len(layer_config["packages"]) > 0


class TestPerformanceRequirements:
    """Test that configuration meets performance requirements."""
    
    def test_authorizer_optimized_for_low_latency(self):
        """Verify authorizer is configured for low latency."""
        # Requirement 23.1: API responds within 2 seconds
        # Authorizer must be fast as it's called on every request
        
        # Find authorizer config
        authorizer_config = None
        for config_type, config in MEMORY_CONFIG.items():
            if "authorizer" in config["functions"]:
                authorizer_config = config
                break
        
        assert authorizer_config is not None
        assert authorizer_config["memory_size"] >= 256  # Sufficient for JWT validation
        assert authorizer_config["timeout"].to_seconds() == 10  # Quick timeout
    
    def test_dashboard_optimized_for_aggregation(self):
        """Verify dashboard is configured for data aggregation."""
        # Requirement 23.1: Dashboard loads within 3 seconds
        
        # Find dashboard config
        dashboard_config = None
        for config_type, config in MEMORY_CONFIG.items():
            if "dashboard" in config["functions"]:
                dashboard_config = config
                break
        
        assert dashboard_config is not None
        assert dashboard_config["memory_size"] >= 512  # Sufficient for aggregation
    
    def test_ai_functions_have_sufficient_memory(self):
        """Verify AI-powered functions have sufficient memory for ML operations."""
        ai_functions = ["document_intelligence", "report_generation", "risk_detection"]
        
        for function_name in ai_functions:
            # Find function config
            function_config = None
            for config_type, config in MEMORY_CONFIG.items():
                if function_name in config["functions"]:
                    function_config = config
                    break
            
            assert function_config is not None
            assert function_config["memory_size"] >= 1024  # AI operations need memory


class TestCostOptimization:
    """Test that configuration balances performance and cost."""
    
    def test_provisioned_concurrency_is_limited(self):
        """Verify provisioned concurrency is used sparingly (cost consideration)."""
        # Provisioned concurrency adds fixed cost
        total_provisioned = sum(PROVISIONED_CONCURRENCY_CONFIG.values())
        assert total_provisioned <= 15  # Reasonable limit for cost control
    
    def test_lightweight_functions_use_minimal_memory(self):
        """Verify lightweight functions don't over-provision memory."""
        lightweight_config = MEMORY_CONFIG["lightweight"]
        assert lightweight_config["memory_size"] <= 512
    
    def test_timeout_values_are_reasonable(self):
        """Verify timeout values are not excessively long."""
        for config_type, config in MEMORY_CONFIG.items():
            timeout_seconds = config["timeout"].to_seconds()
            # Most functions should complete within 5 minutes
            assert timeout_seconds <= 300


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
