# API Documentation - BYOD Synthetic Data Generator

## Base URL
```
http://localhost:8201
```

## Authentication
The JSON API under `/api/v1` has an optional API key. When the server has the
environment variable `MOCKDATA_API_KEY` set, every `/api/v1` request must send the
same value in the `X-API-Key` header, otherwise it gets `401`. When the variable is
unset or empty the check is off (local use). The older routes (`/generate`,
`/metadata`, ...) do not check the key.

## JSON API for other programs (`/api/v1`)

Use these routes to call the generator from another program: JSON in, JSON out, no
file upload form. They are also described, with their request and response models,
in `/openapi.json` and the interactive page at `/docs`. A small ready-to-copy client
is in `scripts/api_client_example.py` (standard library only).

### Version

**Endpoint:** `GET /api/v1/version`

```bash
curl -s "http://localhost:8201/api/v1/version"
```

```json
{"service": "BYOD Synthetic Data Generator", "version": "1.0.0", "api_version": "v1"}
```

### Generate synthetic data from JSON

**Endpoint:** `POST /api/v1/generate` (`Content-Type: application/json`)

**Body:** send exactly one of `csv_text` or `data_content`.
- `csv_text` (string): the source data as plain CSV text, header row first
- `data_content` (string): the source file's bytes, base64-encoded
- `format` (string, optional): format of `data_content` - "csv", "tsv", "json", "excel" or "parquet" (default: "csv")
- `num_rows` (integer, optional): rows to generate, 1-100000 (default: same as the source)
- `match_threshold` (float, optional): statistical matching threshold, 0-1 (default: 0.8)
- `safety_mode` (string, optional): "strict", "balanced" or "permissive" (default: "balanced")
- `use_cache` (boolean, optional): reuse a cached generation script (default: true)

Unknown field names are rejected with `422`, so a typo is not silently ignored.

**Request (CSV text):**
```bash
curl -s -X POST "http://localhost:8201/api/v1/generate" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $MOCKDATA_API_KEY" \
  -d '{"csv_text": "widget_id,colour,weight_g\nW001,red,12.5\nW002,blue,14.1\n", "num_rows": 3}'
```

**Request (base64 file):**
```bash
curl -s -X POST "http://localhost:8201/api/v1/generate" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $MOCKDATA_API_KEY" \
  -d "{\"data_content\": \"$(base64 < data.csv | tr -d '\n')\", \"format\": \"csv\", \"num_rows\": 100}"
```

Leave the `X-API-Key` line out when the server has no key set.

**Response (`200`):**
```json
{
  "status": "success",
  "data": [
    {"widget_id": "W104", "colour": "blue", "weight_g": 13.4},
    {"widget_id": "W221", "colour": "red", "weight_g": 12.1},
    {"widget_id": "W087", "colour": "red", "weight_g": 14.0}
  ],
  "shape": [3, 3],
  "columns": ["widget_id", "colour", "weight_g"],
  "generation_info": {"method": "llm", "num_rows": 3}
}
```

Generation calls an AI model and can take a minute or more: set the client timeout
to several minutes.

### Request size limit

A `/api/v1` request body larger than the limit is refused with `413`. The limit is
10 MB (10485760 bytes) by default; change it with the environment variable
`MOCKDATA_API_MAX_BYTES` (bytes). Base64 makes a file about one third larger.

### Errors on `/api/v1`

Every failure on `/api/v1` has the same JSON shape:

```json
{"status": "error", "error": "what went wrong, in words", "error_class": "ShortName"}
```

| Status | `error_class` | Meaning |
|--------|---------------|---------|
| `400` | `GenerationError` | The source data could not be read or used |
| `401` | `InvalidApiKey` | `X-API-Key` missing or wrong (only when the server has a key set) |
| `404` / `405` | `HTTPException` | No such `/api/v1` route, or wrong method |
| `413` | `RequestTooLarge` | Body larger than the size limit |
| `422` | `RequestValidationError` | Body is not valid JSON, or a field is missing or out of range |
| `500` | `InternalError` | Unexpected server error |
| `502` | `AIGenerationError` or a more specific name | The AI call failed. No data was generated (there is no template fallback) |
| `503` | `AINotConfiguredError` | The server has no AI configured. No data was generated |

```bash
curl -s -X POST "http://localhost:8201/api/v1/generate" -H "Content-Type: application/json" -d '{}'
```

```json
{"status": "error", "error": "Invalid request: body: Value error, provide exactly one of csv_text or data_content", "error_class": "RequestValidationError"}
```

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
- `safety_mode` (string, optional): Privacy level for categorical data - "strict", "balanced", or "permissive" (default: "balanced")

**Request:**
```bash
curl -X POST "http://localhost:8201/generate" \
  -F "file=@data.csv" \
  -F "num_rows=5000" \
  -F "match_threshold=0.85" \
  -F "output_format=csv" \
  -F "use_cache=true" \
  -F "safety_mode=balanced" \
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

### 8. Data dictionaries

`POST /dictionary/upload` (form: `file`, optional `format`, optional `table`),
`POST /dictionary/table` (form: `table`), `POST /dictionary/validate` and
`POST /generate-with-dictionary` (both take an optional `table`).

Recognised shapes: CSV/Excel with one row per column; JSON/YAML `{"columns": {...}}`;
a list of `{"name": ...}` objects; a `{column: type-or-definition}` mapping; JSON Schema
(`properties`, or several tables in `$defs`/`definitions`); Frictionless Table Schema
(`fields`); a FHIR StructureDefinition; a FHIR Bundle of StructureDefinitions (one table
per resource). For FHIR, each element of the snapshot (or the differential when there is
no snapshot) becomes a column: nested backbone elements are flattened with dotted names
(`contact.name`), `[x]` choice elements become one column (`deceased`, first type,
all types in the description), `meta`/`text`/extensions/slices are skipped, `min >= 1`
means required, and a required code binding with a `a | b | c` short gives allowed values.

Several tables and no `table`: the upload answers `200` with `"status": "choose_table"`
and `"tables": [...]` (then call `/dictionary/table`, no re-upload); generation answers
`400` `DictionaryTableRequired` listing the names. Anything that is not a dictionary is
refused with `400` `UnrecognizedDictionary`.

Limits (environment variables):

- `MOCKDATA_DICTIONARY_MAX_BYTES` (default 64 MB): largest dictionary file; above it `413`
  `DictionaryTooLarge`.
- `MOCKDATA_DICTIONARY_PROMPT_MAX_CHARS` (default 60000): dictionary text sent to the AI.
  Over it, a copy is trimmed (value lists to 20, descriptions to 160/60/none, value lists
  to 5, then optional columns, then required ones, from the end) and the response says so in
  `dictionary_trimming` (header `X-Dictionary-Trimmed` on downloads).

If the AI model still refuses the request as too large, the answer is `413`
`AIRequestTooLargeError` with a plain message (no provider text).

## Error Responses

The `/api/v1` routes use the single error shape described under "Errors on `/api/v1`"
above. The older routes return errors in the following format (and, when the AI call
fails, `{"status": "error", "error": "...", "error_class": "..."}` with `502`, `503` or
`413`; data dictionary problems use the same shape with `400` or `413`):

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

## Client Examples

There is no installable SDK package. Call the HTTP API directly, or copy the small
client in `scripts/api_client_example.py`.

### Python
```python
# from the repo root; standard library only
from scripts.api_client_example import MockDataClient

client = MockDataClient(base_url="http://localhost:8201", api_key=None)  # or MOCKDATA_API_URL / MOCKDATA_API_KEY

print(client.health())    # (200, {...})
print(client.version())   # (200, {"version": "1.0.0", ...})

status, body = client.generate(csv_text="widget_id,colour\nW001,red\nW002,blue\n", num_rows=10)
if status == 200:
    rows = body["data"]            # list of dicts, one per row
else:
    print(body["error_class"], body["error"])
```

Run the demo: `python scripts/api_client_example.py --base-url http://localhost:8201`

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
  -F "safety_mode=permissive" \
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
6. **Safety Mode Selection**:
   - Use `strict` for highly sensitive data (medical, financial PII)
   - Use `balanced` for general business data (default)
   - Use `permissive` for non-sensitive test data requiring maximum realism

## Versioning

The service version is returned by `GET /api/v1/version` (and in `/openapi.json`).
The `v1` in the path is the API version; there is no version response header.

## Support

For API issues or questions:
- Check the [User Guide](USER_GUIDE.md)
- Review [OpenAPI documentation](http://localhost:8201/docs)
- Submit issues on GitHub