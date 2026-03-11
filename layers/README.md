# Lambda Layers

This directory contains Lambda layers for shared dependencies across Lambda functions.

## Structure

```
layers/
├── common/              # Common dependencies (boto3, requests, etc.)
│   └── python/
│       └── requirements.txt
├── data_processing/     # Data processing libraries (pandas, numpy)
│   └── python/
│       └── requirements.txt
└── ai_ml/              # AI/ML libraries (anthropic, sagemaker)
    └── python/
        └── requirements.txt
```

## Building Layers

### Prerequisites
- Python 3.11
- pip

### Build Script

```bash
#!/bin/bash

# Build common layer
cd layers/common
pip install -r python/requirements.txt -t python/
zip -r common-layer.zip python/
cd ../..

# Build data processing layer
cd layers/data_processing
pip install -r python/requirements.txt -t python/
zip -r data-processing-layer.zip python/
cd ../..

# Build AI/ML layer
cd layers/ai_ml
pip install -r python/requirements.txt -t python/
zip -r ai-ml-layer.zip python/
cd ../..
```

### Deployment

Layers are automatically deployed by CDK when you run:
```bash
cdk deploy LambdaLayersStack
```

## Layer Usage

Layers are automatically attached to Lambda functions based on their requirements:

- **Common Layer**: All functions
- **Data Processing Layer**: Risk detection, prediction, report generation
- **AI/ML Layer**: Document intelligence, report generation, risk detection

## Benefits

1. **Reduced Package Size**: Individual function packages are smaller
2. **Faster Cold Starts**: Less code to load and initialize
3. **Easier Dependency Management**: Update dependencies once, affects all functions
4. **Version Control**: Layer versions can be managed independently

## Layer Size Limits

- Maximum unzipped size: 250 MB
- Maximum zipped size: 50 MB per layer
- Maximum layers per function: 5

## Best Practices

1. Keep layers focused and minimal
2. Version layers appropriately
3. Test layer updates in staging first
4. Monitor layer usage and performance
5. Clean up unused layer versions

## Troubleshooting

### Import Errors
If you encounter import errors after adding a layer:
1. Verify the layer is attached to the function
2. Check the layer's Python version compatibility
3. Ensure the package is in the `python/` directory

### Size Issues
If a layer exceeds size limits:
1. Remove unnecessary dependencies
2. Use compiled/optimized packages
3. Split into multiple layers
