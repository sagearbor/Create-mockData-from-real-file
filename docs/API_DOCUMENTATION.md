# API Documentation - BYOD Synthetic Data Generator

## Base URL
```
http://localhost:8201
```

## Authentication
Currently, the API does not require authentication for local usage. For production deployment, implement API key authentication.

## Endpoints

### 1. Health Check

Check if the service is running and configured properly.

**Endpoint:** `GET /health`

**Response:**
```json
{
  "status": "healthy",
  "openai_configured": true,
  "cache_enabled": true,
  "environment": "local"
}
```

### 2. Upload File

Upload a file for analysis and prepare for synthetic data generation.

**Endpoint:** `POST /upload`

**Parameters:**
- `file` (file, required): The data file to upload
- `extract_metadata_only` (boolean, optional): If true, only extract metadata without storing

**Request:**
```bash
curl -X POST "http://localhost:8201/upload" \
  -F "file=@data.csv" \
  -F "extract_metadata_only=false"
```

**Response:**
```json
{
  "status": "success",
  "filename": "data.csv",
  "metadata_key": "format_a1b2c3d4",
  "shape": {
    "rows": 1000,
    "columns": 10
  },
  "columns": 10,
  "message": "File uploaded and analyzed. Use /generate endpoint to create synthetic data."
}
```

### 3. Extract Metadata

Extract and return metadata from a file without generating synthetic data.

**Endpoint:** `POST /metadata`

**Parameters:**
- `file` (file, required): The data file to analyze

**Request:**
```bash
curl -X POST "http://localhost:8201/metadata" \
  -F "file=@data.csv"
```

**Response:**
```json
{
  "status": "success",
  "filename": "data.csv",
  "metadata": {
    "structure": {
      "shape": {"rows": 100, "columns": 5},
      "columns": [
        {
          "name": "id",
          "dtype": "int64",
          "python_type": "int",
          "nullable": false,
          "unique_count": 100,
          "null_count": 0
        }
      ]
    },
    "statistics": {
      "id": {
        "type": "numeric",
        "mean": 50.5,
        "std": 28.87,
        "min": 1,
        "max": 100
      }
    },
    "patterns": {},
    "correlations": {},
    "data_quality": {
      "completeness": 1.0,
      "duplicate_rows": 0
    }
  }
}
```

### 4. Generate Synthetic Data

Generate synthetic data based on uploaded file or metadata.

**Endpoint:** `POST /generate`

**Parameters:**
- `file` (file, optional): The data file to use as template
- `metadata_json` (string, optional): Pre-extracted metadata JSON
- `num_rows` (integer, optional): Number of rows to generate
- `match_threshold` (float, optional): Statistical matching threshold (0-1, default: 0.8)
- `output_format` (string, optional): Output format - "csv", "json", or "excel" (default: "csv")
- `use_cache` (boolean, optional): Use cached generation scripts (default: true)

**Request:**
```bash
curl -X POST "http://localhost:8201/generate" \
  -F "file=@data.csv" \
  -F "num_rows=5000" \
  -F "match_threshold=0.85" \
  -F "output_format=csv" \
  -F "use_cache=true" \
  --output synthetic_data.csv
```

**Response (JSON format):**
```json
{
  "status": "success",
  "data": [...],
  "shape": [5000, 10],
  "columns": ["id", "name", "value", ...]
}
```

**Response (CSV/Excel format):**
Binary file download

### 5. Batch Generation

Generate synthetic data for multiple files.

**Endpoint:** `POST /generate/batch`

**Parameters:**
- `files` (files, required): Multiple files to process
- `match_threshold` (float, optional): Statistical matching threshold (default: 0.8)

**Request:**
```bash
curl -X POST "http://localhost:8201/generate/batch" \
  -F "files=@file1.csv" \
  -F "files=@file2.csv" \
  -F "match_threshold=0.8"
```

**Response:**
```json
{
  "status": "processing",
  "batch_id": "batch_20240115_143022",
  "file_count": 2,
  "message": "Batch processing started. Check status at /batch/batch_20240115_143022"
}
```

### 6. Check Batch Status

Check the status of batch processing.

**Endpoint:** `GET /batch/{batch_id}`

**Response:**
```json
{
  "status": "completed",
  "batch_id": "batch_20240115_143022",
  "results": [
    {
      "filename": "file1.csv",
      "status": "success",
      "output_path": "./data/local_storage/batch_20240115_143022/file1.csv_synthetic.csv"
    },
    {
      "filename": "file2.csv",
      "status": "success",
      "output_path": "./data/local_storage/batch_20240115_143022/file2.csv_synthetic.csv"
    }
  ]
}
```

### 7. Clear Cache

Clear cached generation scripts.

**Endpoint:** `DELETE /cache`

**Parameters:**
- `older_than_days` (integer, optional): Only clear entries older than specified days

**Request:**
```bash
# Clear all cache
curl -X DELETE "http://localhost:8201/cache"

# Clear cache older than 7 days
curl -X DELETE "http://localhost:8201/cache?older_than_days=7"
```

**Response:**
```json
{
  "status": "success",
  "message": "Cache cleared (older_than_days=7)"
}
```

## Error Responses

All endpoints may return error responses in the following format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

**Common HTTP Status Codes:**
- `200 OK`: Successful request
- `400 Bad Request`: Invalid parameters or file format
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error during processing

## Data Formats

### Supported Input Formats
- **CSV**: Comma-separated values
- **JSON**: JavaScript Object Notation (array of objects or nested structure)
- **Excel**: .xlsx and .xls files
- **Parquet**: Apache Parquet format
- **TSV**: Tab-separated values
- **Text**: Delimited text files

### Output Formats
- **CSV**: Standard CSV with headers
- **JSON**: Array of objects
- **Excel**: Excel workbook with single sheet

## Rate Limiting

Currently no rate limiting is implemented for local usage. For production:
- Recommended: 10 requests per minute per IP
- Batch operations: 1 request per minute

## WebSocket Support (Future)

Real-time generation status updates (planned for future release):
```javascript
const ws = new WebSocket('ws://localhost:8000/ws');
ws.onmessage = (event) => {
  const status = JSON.parse(event.data);
  console.log('Generation progress:', status.progress);
};
```

## SDK Examples

### Python SDK
```python
from byod_synthetic import SyntheticGenerator

# Initialize client
generator = SyntheticGenerator(base_url="http://localhost:8201")

# Generate synthetic data
result = generator.generate(
    file_path="data.csv",
    num_rows=10000,
    match_threshold=0.85
)

# Save result
result.to_csv("synthetic_data.csv")
```

### JavaScript/Node.js
```javascript
const FormData = require('form-data');
const fs = require('fs');
const axios = require('axios');

const form = new FormData();
form.append('file', fs.createReadStream('data.csv'));
form.append('match_threshold', '0.85');

const response = await axios.post(
  'http://localhost:8201/generate',
  form,
  { headers: form.getHeaders() }
);

fs.writeFileSync('synthetic_data.csv', response.data);
```

### cURL Examples
```bash
# Extract metadata only
curl -X POST "http://localhost:8201/metadata" \
  -F "file=@data.csv" \
  -o metadata.json

# Generate with specific settings
curl -X POST "http://localhost:8201/generate" \
  -F "file=@data.csv" \
  -F "num_rows=1000" \
  -F "match_threshold=0.9" \
  -F "output_format=json" \
  -o synthetic_data.json

# Batch processing
curl -X POST "http://localhost:8201/generate/batch" \
  -F "files=@dataset1.csv" \
  -F "files=@dataset2.csv" \
  -F "files=@dataset3.csv" \
  -F "match_threshold=0.8"
```

## Best Practices

1. **File Size**: Keep individual files under 100MB for optimal performance
2. **Batch Processing**: Use batch endpoint for multiple files
3. **Caching**: Enable caching for repeated similar datasets
4. **Error Handling**: Always check response status codes
5. **Timeouts**: Set client timeout to at least 60 seconds for large files

## Versioning

API version is included in response headers:
```
X-API-Version: 1.0.0
```

## Support

For API issues or questions:
- Check the [User Guide](USER_GUIDE.md)
- Review [OpenAPI documentation](http://localhost:8201/docs)
- Submit issues on GitHub