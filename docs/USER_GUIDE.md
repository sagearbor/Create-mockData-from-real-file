# BYOD Synthetic Data Generator - User Guide

## Table of Contents
1. [Overview](#overview)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [Using the Web Interface](#using-the-web-interface)
5. [Using the API](#using-the-api)
6. [Configuration](#configuration)
7. [Advanced Features](#advanced-features)
8. [Troubleshooting](#troubleshooting)

## Overview

The BYOD (Bring Your Own Data) Synthetic Data Generator is a privacy-preserving tool that creates realistic synthetic datasets based on the statistical properties of your original data. It ensures that sensitive information (like PHI) never leaves your environment while generating high-quality test data for development and testing.

### Key Features
- **Privacy-First**: Original data never touches the LLM - only statistical metadata
- **Format Agnostic**: Supports CSV, JSON, Excel, Parquet, and more
- **Statistical Fidelity**: Preserves distributions, correlations, and patterns
- **Intelligent Caching**: Reuses generation scripts for similar datasets
- **Multiple Interfaces**: Web UI, REST API, and programmatic access

## Installation

### Prerequisites
- Python 3.11 or higher
- Azure OpenAI API access (optional, for enhanced generation)
- 4GB RAM minimum
- 1GB free disk space

### Local Installation

1. **Clone the repository:**
```bash
git clone https://github.com/your-org/Create-mockData-from-real-file.git
cd Create-mockData-from-real-file
```

2. **Create virtual environment:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your Azure OpenAI credentials (if available)
```

5. **Run the application:**
```bash
python main.py
```

The application will start at `http://localhost:8201`

## Quick Start

### Generate synthetic data in 3 steps:

1. **Upload your data file** (CSV, JSON, Excel, etc.)
2. **Configure generation settings** (number of rows, match strictness)
3. **Download the synthetic dataset**

### Example using the Web Interface:
1. Navigate to `http://localhost:8201`
2. Drag and drop your data file
3. Adjust the "Match Strictness" slider (80% recommended)
4. Click "Generate Synthetic Data"
5. Download the result

### Example using curl:
```bash
curl -X POST "http://localhost:8201/generate" \
  -F "file=@your_data.csv" \
  -F "match_threshold=0.8" \
  -F "output_format=csv" \
  --output synthetic_data.csv
```

## Using the Web Interface

### Main Features

#### File Upload Area
- **Drag & Drop**: Simply drag your file onto the upload area
- **Browse**: Click to select files from your computer
- **Supported Formats**: CSV, JSON, Excel (.xlsx, .xls), Parquet, TSV

#### Generation Settings
- **Number of Rows**: Specify how many rows to generate (leave empty to match original)
- **Match Strictness**: Control how closely the synthetic data matches statistical properties
  - 0% = Loose match (faster, less accurate)
  - 100% = Exact match (slower, highly accurate)
  - Recommended: 70-85% for most use cases

#### Output Options
- **CSV**: Standard comma-separated values
- **JSON**: JavaScript Object Notation
- **Excel**: Microsoft Excel format

#### Demo Datasets
Try the generator with pre-loaded examples:
- Sales Data
- Customer Records
- Medical Records (with PHI)
- Financial Transactions

### Advanced Features

#### Metadata Extraction
Extract and view statistical metadata without generating synthetic data:
1. Upload your file
2. Click "Extract Metadata Only"
3. Review the JSON metadata structure

#### Batch Processing
Process multiple files at once:
1. Select multiple files in the upload dialog
2. Configure common settings
3. Download results as a ZIP archive

## Using the API

### REST API Endpoints

#### Health Check
```http
GET /health
```

#### Upload and Analyze
```http
POST /upload
Content-Type: multipart/form-data

file: <your-file>
extract_metadata_only: false
```

#### Generate Synthetic Data
```http
POST /generate
Content-Type: multipart/form-data

file: <your-file>
num_rows: 1000
match_threshold: 0.8
output_format: csv
use_cache: true
```

#### Extract Metadata Only
```http
POST /metadata
Content-Type: multipart/form-data

file: <your-file>
```

### Python Client Example
```python
import requests

# Upload and generate synthetic data
with open('data.csv', 'rb') as f:
    response = requests.post(
        'http://localhost:8201/generate',
        files={'file': f},
        data={
            'match_threshold': 0.85,
            'num_rows': 5000,
            'output_format': 'csv'
        }
    )
    
# Save the result
with open('synthetic_data.csv', 'wb') as f:
    f.write(response.content)
```

## Configuration

### Environment Variables

Create a `.env` file based on `.env.example`:

```env
# Azure OpenAI Configuration (Required for LLM generation)
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=gpt-4
AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME=text-embedding-ada-002

# Application Settings
GENERATOR_VERSION=1.0
LOG_LEVEL=INFO
ENVIRONMENT=local
APP_PORT=8201

# Local Storage (when not using cloud services)
USE_LOCAL_STORAGE=true
LOCAL_STORAGE_PATH=./data/local_storage
LOCAL_CACHE_PATH=./data/cache
```

### Cache Configuration

The system automatically caches generation scripts for performance:
- **Format Hash**: Matches datasets with identical structure
- **Full Hash**: Matches datasets with identical statistics
- **Similarity Search**: Finds similar datasets using vector embeddings

Clear cache when needed:
```bash
# Clear all cache
curl -X DELETE http://localhost:8201/cache

# Clear cache older than 7 days
curl -X DELETE "http://localhost:8201/cache?older_than_days=7"
```

## Advanced Features

### Statistical Matching

The generator preserves various statistical properties:
- **Distributions**: Mean, standard deviation, min/max values
- **Correlations**: Relationships between numeric columns
- **Patterns**: Email formats, phone numbers, IDs
- **Categorical**: Frequency distributions of categories
- **Temporal**: Date ranges and time patterns

### Security Features

- **Metadata-Only Processing**: LLM never sees actual data values
- **Secure Sandboxing**: Generated code runs in isolated environment
- **No Data Persistence**: Original data is never stored
- **Anonymized Caching**: Only statistical properties are cached

### Performance Optimization

- **Intelligent Caching**: Reuses scripts for similar datasets
- **Batch Processing**: Handle multiple files efficiently
- **Async Operations**: Non-blocking file processing
- **Vector Similarity**: Fast cache lookups using embeddings

## Troubleshooting

### Common Issues

#### "No OpenAI credentials configured"
- Solution: Add your Azure OpenAI credentials to `.env`
- Fallback: System will use template-based generation

#### "Unsupported file format"
- Solution: Ensure file extension matches content
- Supported: .csv, .json, .xlsx, .xls, .parquet, .tsv

#### "Generation timeout"
- Solution: Reduce number of rows or lower match threshold
- Alternative: Disable caching for fresh generation

#### "Memory error with large files"
- Solution: Process in batches or reduce sample size
- Use API parameter: `sample_size=10000`

### Performance Tips

1. **Use Caching**: Keep `use_cache=true` for repeated similar datasets
2. **Adjust Threshold**: Lower match_threshold for faster generation
3. **Batch Similar Files**: Process related files together
4. **Local Storage**: Use local storage for better performance in development

### Getting Help

- **API Documentation**: http://localhost:8201/docs
- **GitHub Issues**: Report bugs and request features
- **Logs**: Check `./logs/` directory for detailed error information

## Examples

### Example 1: Generate Test Data for E-commerce
```python
# Original sales data with customer PII
original_data = "orders_with_pii.csv"

# Generate safe test data
synthetic_data = generate_synthetic(
    file=original_data,
    num_rows=10000,
    match_threshold=0.85
)
# Result: Realistic sales data without actual customer information
```

### Example 2: Create Training Dataset
```python
# Small production sample
sample_data = "production_sample_100.json"

# Generate larger training set
training_data = generate_synthetic(
    file=sample_data,
    num_rows=50000,
    match_threshold=0.90
)
# Result: Large dataset maintaining statistical properties
```

### Example 3: Compliance Testing
```python
# Medical records with PHI
medical_data = "patient_records.csv"

# Generate HIPAA-compliant test data
test_data = generate_synthetic(
    file=medical_data,
    match_threshold=0.95,
    preserve_patterns=True
)
# Result: Realistic medical data without PHI exposure
```

## Best Practices

1. **Start with Default Settings**: 80% match threshold works well for most cases
2. **Test with Small Samples**: Validate generation quality before processing large files
3. **Use Appropriate Formats**: CSV for tabular data, JSON for nested structures
4. **Monitor Cache Size**: Periodically clear old cache entries
5. **Secure Your Keys**: Never commit API keys to version control

## Support

For additional help:
- Review the [README](../README.md)
- Check [TASK_LIST.md](../TASK_LIST.md) for development status
- Submit issues on GitHub
- Contact the development team