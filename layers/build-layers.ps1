# PowerShell script to build Lambda layers
# This script builds all Lambda layers for the AI SW Program Manager

$ErrorActionPreference = "Stop"

Write-Host "Building Lambda layers..." -ForegroundColor Green

function Build-Layer {
    param(
        [string]$LayerName,
        [string]$LayerDir
    )
    
    Write-Host "Building $LayerName layer..." -ForegroundColor Cyan
    
    Push-Location $LayerDir
    
    # Clean previous build
    if (Test-Path "python/lib") { Remove-Item -Recurse -Force "python/lib" }
    if (Test-Path "python/bin") { Remove-Item -Recurse -Force "python/bin" }
    if (Test-Path "$LayerName-layer.zip") { Remove-Item -Force "$LayerName-layer.zip" }
    
    # Install dependencies
    pip install -r python/requirements.txt -t python/ --upgrade
    
    # Create zip file
    Compress-Archive -Path python/* -DestinationPath "$LayerName-layer.zip" -Force
    
    Write-Host "$LayerName layer built successfully: $LayerDir/$LayerName-layer.zip" -ForegroundColor Green
    
    Pop-Location
}

# Build common layer
Build-Layer -LayerName "common" -LayerDir "layers/common"

# Build data processing layer
Build-Layer -LayerName "data-processing" -LayerDir "layers/data_processing"

# Build AI/ML layer
Build-Layer -LayerName "ai-ml" -LayerDir "layers/ai_ml"

Write-Host ""
Write-Host "All layers built successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "To deploy layers, run:" -ForegroundColor Yellow
Write-Host "  cdk deploy LambdaLayersStack" -ForegroundColor Yellow
