#!/usr/bin/env python3
"""
Verify Setup Script
This script checks if the development environment is properly configured.
"""

import sys
import importlib.util

def check_module(module_name, package_name=None):
    """Check if a Python module is installed."""
    package_name = package_name or module_name
    spec = importlib.util.find_spec(module_name)
    if spec is not None:
        print(f"✅ {package_name} is installed")
        return True
    else:
        print(f"❌ {package_name} is NOT installed")
        return False

def main():
    """Main verification function."""
    print("=" * 60)
    print("AI SW Program Manager - Setup Verification")
    print("=" * 60)
    print()
    
    # Check Python version
    print(f"Python Version: {sys.version}")
    if sys.version_info >= (3, 11):
        print("✅ Python version is 3.11 or higher")
    else:
        print("❌ Python version must be 3.11 or higher")
    print()
    
    # Check required packages
    print("Checking Required Packages:")
    print("-" * 60)
    
    required_packages = [
        ("boto3", "boto3 (AWS SDK)"),
        ("botocore", "botocore"),
        ("psycopg2", "psycopg2-binary (PostgreSQL)"),
        ("opensearchpy", "opensearch-py"),
        ("requests", "requests"),
        ("jwt", "PyJWT"),
        ("cryptography", "cryptography"),
        ("PyPDF2", "PyPDF2"),
        ("docx", "python-docx"),
    ]
    
    all_installed = True
    for module, package in required_packages:
        if not check_module(module, package):
            all_installed = False
    
    print()
    print("Checking Development Packages:")
    print("-" * 60)
    
    dev_packages = [
        ("pytest", "pytest"),
        ("hypothesis", "hypothesis"),
        ("black", "black"),
        ("flake8", "flake8"),
        ("mypy", "mypy"),
        ("pylint", "pylint"),
        ("aws_cdk", "aws-cdk-lib"),
    ]
    
    for module, package in dev_packages:
        if not check_module(module, package):
            all_installed = False
    
    print()
    print("=" * 60)
    if all_installed:
        print("✅ All packages are installed correctly!")
        print("=" * 60)
        print()
        print("Next Steps:")
        print("1. Run tests: pytest tests/unit -v")
        print("2. Check code quality: black src/ && flake8 src/")
        print("3. Deploy to AWS: cd infrastructure && cdk deploy --all")
        print()
        print("For more information, see QUICK_START.md")
        return 0
    else:
        print("❌ Some packages are missing!")
        print("=" * 60)
        print()
        print("To fix, run:")
        print("  pip install -r requirements.txt")
        print("  pip install -r requirements-dev.txt")
        return 1

if __name__ == "__main__":
    sys.exit(main())
