#!/bin/bash

# Build script for Lambda layers
# This script builds all Lambda layers for the AI SW Program Manager

set -e

echo "Building Lambda layers..."

# Function to build a layer
build_layer() {
    local layer_name=$1
    local layer_dir=$2
    
    echo "Building ${layer_name} layer..."
    
    cd "${layer_dir}"
    
    # Clean previous build
    rm -rf python/lib python/bin
    rm -f "${layer_name}-layer.zip"
    
    # Install dependencies
    pip install -r python/requirements.txt -t python/ --upgrade
    
    # Create zip file
    zip -r "${layer_name}-layer.zip" python/ -x "*.pyc" -x "*__pycache__*"
    
    echo "${layer_name} layer built successfully: ${layer_dir}/${layer_name}-layer.zip"
    
    cd - > /dev/null
}

# Build common layer
build_layer "common" "layers/common"

# Build data processing layer
build_layer "data-processing" "layers/data_processing"

# Build AI/ML layer
build_layer "ai-ml" "layers/ai_ml"

echo "All layers built successfully!"
echo ""
echo "To deploy layers, run:"
echo "  cdk deploy LambdaLayersStack"
