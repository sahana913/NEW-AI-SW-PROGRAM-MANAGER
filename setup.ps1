# AI SW Program Manager - Setup Script (Windows PowerShell)
# This script sets up the development environment

Write-Host "=== AI SW Program Manager Setup ===" -ForegroundColor Green
Write-Host ""

# Check Python version
Write-Host "Checking Python version..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
Write-Host "Python version: $pythonVersion"

$versionMatch = $pythonVersion -match "Python (\d+)\.(\d+)"
if ($versionMatch) {
    $major = [int]$matches[1]
    $minor = [int]$matches[2]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
        Write-Host "Error: Python 3.11 or higher is required" -ForegroundColor Red
        exit 1
    }
}

# Create virtual environment
Write-Host ""
Write-Host "Creating virtual environment..." -ForegroundColor Yellow
if (-not (Test-Path "venv")) {
    python -m venv venv
    Write-Host "Virtual environment created" -ForegroundColor Green
} else {
    Write-Host "Virtual environment already exists" -ForegroundColor Green
}

# Activate virtual environment
Write-Host ""
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& .\venv\Scripts\Activate.ps1

# Upgrade pip
Write-Host ""
Write-Host "Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install Python dependencies
Write-Host ""
Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install CDK dependencies
Write-Host ""
Write-Host "Installing CDK dependencies..." -ForegroundColor Yellow
Set-Location infrastructure
npm install
Set-Location ..

# Create necessary directories
Write-Host ""
Write-Host "Creating project directories..." -ForegroundColor Yellow
$directories = @(
    "src/auth",
    "src/user_management",
    "src/data_ingestion",
    "src/risk_detection",
    "src/prediction",
    "src/document_intel",
    "src/report_generation",
    "src/dashboard",
    "tests/unit",
    "tests/integration",
    "tests/property"
)

foreach ($dir in $directories) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

# Create __init__.py files
$initFiles = @(
    "src/__init__.py",
    "src/auth/__init__.py",
    "src/user_management/__init__.py",
    "src/data_ingestion/__init__.py",
    "src/risk_detection/__init__.py",
    "src/prediction/__init__.py",
    "src/document_intel/__init__.py",
    "src/report_generation/__init__.py",
    "src/dashboard/__init__.py",
    "tests/__init__.py",
    "tests/unit/__init__.py",
    "tests/integration/__init__.py",
    "tests/property/__init__.py"
)

foreach ($file in $initFiles) {
    if (-not (Test-Path $file)) {
        New-Item -ItemType File -Path $file -Force | Out-Null
    }
}

Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "To activate the virtual environment, run:" -ForegroundColor Cyan
Write-Host "  .\venv\Scripts\Activate.ps1"
Write-Host ""
Write-Host "To deploy infrastructure, run:" -ForegroundColor Cyan
Write-Host "  cd infrastructure"
Write-Host "  cdk deploy --all"
Write-Host ""
