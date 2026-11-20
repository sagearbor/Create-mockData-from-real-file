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

The BYOD (Bring Your Own Data) Synthetic Data Generator makes made-up datasets with the same columns and similar statistics as a file you upload. The server builds a description of the file, an Azure OpenAI model hosted by the organisation writes a Python script from that description, and the server runs the script.

Your file is sent to the server and analysed there. Rows are not sent to the AI model. The model receives column names, data types, counts and summary statistics. For text columns it receives lengths and formats, plus the labels of repeated categories (such as M / F) in Balanced and Permissive modes; in Strict mode it receives no text values. Other text values, such as IDs, emails, phone numbers and free text, are replaced with placeholders.

**Do not upload real study data or patient identifiers.** This release has not been approved for them. No compliance assessment has been done.

### Key Features
- **Description, not rows**: The AI model receives a description of the data, never the rows (see [What the AI model receives](#what-the-ai-model-receives))
- **Input formats**: CSV, JSON, Excel, Parquet, TSV
- **Statistics**: The description carries distributions, correlations and patterns for the model to follow
- **Script cache**: Reuses a generated script for a similar description
- **Interfaces**: Web UI, REST API, MCP and A2A (see [INTEGRATION.md](INTEGRATION.md))
- **Choice of AI model**: From the server's allow-list

## Installation

### Prerequisites
- Python 3.11 or higher
- Azure OpenAI access (required: generation does not work without the AI model)
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
# Edit .env: AZURE_OPENAI_ENDPOINT is required
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
  -F "safety_mode=balanced" \
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
  - 0% = Loose match
  - 100% = Closest match the AI model is asked for
  - Recommended: 70-85% for most use cases
- **Safety Mode**: Controls which text values the AI model may see
  - **Strict**: No text value is sent. Numbers are rounded and ranges are widened
  - **Balanced** (default): Repeated short category labels (for example M / F) are sent for columns with up to 10 distinct values
  - **Permissive**: The same rule, for columns with up to 50 distinct values
- **AI model**: Leave the server default, or choose another model from the list. The list comes from the server (`GET /api/models`)

#### Output Options
- **CSV**: Standard comma-separated values
- **JSON**: JavaScript Object Notation
- **Excel**: Microsoft Excel format

#### Demo Datasets
Try the generator with pre-loaded examples:
- Sales Data
- Customer Records
- Medical (built-in example data)
- Financial Transactions

### Advanced Features

#### Metadata Extraction
Extract and view statistical metadata without generating synthetic data:
1. Upload your file
2. Click "Extract Metadata Only"
3. Review the JSON metadata structure

#### Several files at once
Set "Number of files" (1 to 20) to get that many generated files in one ZIP archive. All are made from the one uploaded file.

Batch generation from several uploaded files is switched off in this release (`POST /generate/batch` answers 501).

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
safety_mode: balanced
model: <optional; a name from GET /api/models>
```

A `model` name that is not on the server's list is refused with status 400. There is also a JSON API under `/api/v1`; see [API_DOCUMENTATION.md](API_DOCUMENTATION.md).

#### List the AI models
```http
GET /api/models
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
            'output_format': 'csv',
            'safety_mode': 'balanced'  # or 'strict', 'permissive'
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
# Azure OpenAI (required; without the endpoint every generation request fails)
AZURE_OPENAI_ENDPOINT=https://<your-foundry>.openai.azure.com/
# identity (default): `az login` locally, managed identity when deployed. No key needed.
LLM_AUTH=identity
# Only with LLM_AUTH=key:
# AZURE_OPENAI_API_KEY=<your-key>
# The server default model
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=gpt-5-nano
# Optional: models a request may choose (comma-separated). Unset = built-in list.
# LLM_ALLOWED_MODELS=<deployment-name-1>,<deployment-name-2>

# Application Settings
# Raising this number retires every cached script.
GENERATOR_VERSION=1.1
LOG_LEVEL=INFO
ENVIRONMENT=local
APP_PORT=8201

# Local Storage (when not using cloud services)
USE_LOCAL_STORAGE=true
LOCAL_STORAGE_PATH=./data/local_storage
LOCAL_CACHE_PATH=./data/cache
```

### Cache Configuration

The generated script and the description it was written for are saved on the server's disk (`LOCAL_CACHE_PATH`):
- **Format Hash**: Matches datasets with the same columns and data types
- **Full Hash**: Matches datasets with an identical description
- **Similarity**: Compares a short list of numbers taken from the description

A script is reused only for the number of rows it was written for.

Clear cache when needed:
```bash
# Clear all cache
curl -X DELETE http://localhost:8201/cache

# Clear cache older than 7 days
curl -X DELETE "http://localhost:8201/cache?older_than_days=7"
```

## Advanced Features

### What the description carries

The AI model is asked to follow these properties. It does not see the rows.
- **Distributions**: Mean, standard deviation, range
- **Correlations**: Relationships between numeric columns
- **Categorical**: How often each category occurs
- **Temporal**: Date ranges (widened to whole months or years) and time patterns
- **Patterns**:
  - **ID shapes**: for example `INV-<4 digits>`, never a real ID
  - **Email and phone formats**
  - **Currency values**: decimal places
  - **Datetime formats**

### What the AI model receives

- **Column names**: always, exactly as they are in the file.
- **Number columns**: in Balanced and Permissive modes, for a column with 20 or more values, the real smallest, largest, middle and quartile values are sent. In Strict mode, and for a column with fewer than 20 values, numbers are rounded and the range is widened. Columns whose name looks like an identifier (`patient_id`, `mrn`, `zip`, ...) send no smallest, largest, middle or quartile value.
- **Date columns**: the range is widened to whole months, or to whole years for columns named like a date of birth, in Strict mode, and for columns with fewer than 20 values. Exact earliest and latest dates are not sent.
- **Text columns**: values are replaced with placeholders unless they are repeated short category labels in a column with 20 or more values and a name that does not look like an identifier. Balanced allows up to 10 distinct labels, Permissive up to 50, Strict none.
- **A limit of this rule**: a person's name that occurs 5 or more times in a column with an ordinary name is treated as a category label and is sent in Balanced and Permissive modes.
- **Shared beginnings and endings**: outside Strict mode, a beginning or ending of up to 6 characters with no digits that many values share can be sent.
- **A data dictionary, if uploaded**: its column definitions, cut to a size limit.

### What is stored and how scripts run

- **Cache**: The description sent to the model and the generated script are saved on the server's disk until the cache is cleared. A request with `use_cache=false` does not read or write the cache.
- **Uploaded files**: Not written to the cache. Held in memory while a request is processed; the web framework may also keep a temporary file.
- **Running the script**: The script is screened first (only data libraries; no file, network or process access) and then runs as a separate process with a time limit, on the same server as the application. This is not full isolation.
- **Sign-in**: There is none. Anyone who can reach the site on the organisation network (VPN) can use it.
- **Approval**: This release has not been approved for real study data or patient identifiers.

## Troubleshooting

### Common Issues

#### "AI is not configured" (status 503)
- Solution: Set `AZURE_OPENAI_ENDPOINT` in `.env` and sign in with `az login`, or use `LLM_AUTH=key` with `AZURE_OPENAI_API_KEY`
- There is no other generator: without the AI model, generation fails with this error

#### "Unsupported file format"
- Solution: Ensure file extension matches content
- Supported: .csv, .json, .xlsx, .xls, .parquet, .tsv

#### "Generation timeout"
- A generated script may run for at most 30 seconds. Reduce the number of rows and try again

#### "Request body is larger than the limit" (status 413)
- Uploads are limited to 50 MB by default (`MOCKDATA_MAX_UPLOAD_BYTES`). Upload a smaller sample of the file

#### "Model ... is not available on this server" (status 400)
- Use a name from `GET /api/models`, or leave `model` out

### Performance Tips

1. **Use Caching**: Keep `use_cache=true` for repeated similar datasets
2. **Start small**: Check the result on a few rows before asking for many

### Getting Help

- **API Documentation**: http://localhost:8201/docs
- **GitHub Issues**: Report bugs and request features
- **Logs**: Check `./logs/` directory for detailed error information

## Examples

Use data you are allowed to send to this server. This release is not approved for real study data or patient identifiers.

### Example 1: A larger test set from a small sample
```bash
curl -X POST "http://localhost:8201/generate" \
  -F "file=@sample_100_rows.csv" \
  -F "num_rows=10000" \
  -F "match_threshold=0.85" \
  -F "output_format=csv" \
  --output test_data.csv
```

### Example 2: Strict mode
```bash
# No text value is sent to the AI model; numbers are rounded and ranges widened.
curl -X POST "http://localhost:8201/generate" \
  -F "file=@your_data.csv" \
  -F "safety_mode=strict" \
  -F "output_format=csv" \
  --output test_data.csv
```

### Example 3: From a data dictionary only
```bash
curl -X POST "http://localhost:8201/generate-with-dictionary" \
  -F "dictionary_file=@dictionary.json" \
  -F "num_rows=1000" \
  -F "output_format=csv" \
  --output test_data.csv
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
- Check [developer_tasklist.md](developer_tasklist.md) for open work
- Submit issues on GitHub
- Contact the development team