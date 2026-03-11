#!/bin/bash

# AI SW Program Manager - Setup Script
# This script sets up the development environment

set -e

echo "=== AI SW Program Manager Setup ==="
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $python_version"

if ! python3 -c 'import sys; exit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo "Error: Python 3.11 or higher is required"
    exit 1
fi

# Create virtual environment
echo ""
echo "Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "Virtual environment created"
else
    echo "Virtual environment already exists"
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip

# Install Python dependencies
echo ""
echo "Installing Python dependencies..."
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install CDK dependencies
echo ""
echo "Installing CDK dependencies..."
cd infrastructure
npm install
cd ..

# Create necessary directories
echo ""
echo "Creating project directories..."
mkdir -p src/auth
mkdir -p src/user_management
mkdir -p src/data_ingestion
mkdir -p src/risk_detection
mkdir -p src/prediction
mkdir -p src/document_intel
mkdir -p src/report_generation
mkdir -p src/dashboard
mkdir -p tests/unit
mkdir -p tests/integration
mkdir -p tests/property

# Create __init__.py files
touch src/__init__.py
touch src/auth/__init__.py
touch src/user_management/__init__.py
touch src/data_ingestion/__init__.py
touch src/risk_detection/__init__.py
touch src/prediction/__init__.py
touch src/document_intel/__init__.py
touch src/report_generation/__init__.py
touch src/dashboard/__init__.py
touch tests/__init__.py
touch tests/unit/__init__.py
touch tests/integration/__init__.py
touch tests/property/__init__.py

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To activate the virtual environment, run:"
echo "  source venv/bin/activate"
echo ""
echo "To deploy infrastructure, run:"
echo "  cd infrastructure"
echo "  cdk deploy --all"
echo ""
