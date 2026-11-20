# BYOD Synthetic Data Generator

Upload a data file and/or a data dictionary. The server builds a description of the data, an Azure OpenAI model hosted by the organisation writes a Python script from that description, the server runs the script, and made-up data comes back.

**What is sent where.** Your file is sent to this server and analysed there. Rows are not sent to the AI model. The model receives column names, data types, counts and summary statistics. For text columns it receives lengths and formats, plus the labels of repeated categories (such as M / F) in Balanced and Permissive modes; in Strict mode it receives no text values. Other text values, such as IDs, emails, phone numbers and free text, are replaced with placeholders. Details: [What the AI model receives](#what-the-ai-model-receives).

**Do not upload real study data or patient identifiers.** This release has not been approved for them. No compliance assessment has been done.

## 🚀 Quick Start

### Prerequisites
- Python 3.11 or higher
- 4GB RAM minimum
- 1GB free disk space

### Installation & Setup

1. **Clone the repository**
```bash
git clone https://github.com/your-org/Create-mockData-from-real-file.git
cd Create-mockData-from-real-file
```

2. **Create and activate virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables**
```bash
cp .env.example .env
# Edit .env: AZURE_OPENAI_ENDPOINT is required. Without it every generation request fails.
```

5. **Start the application**
```bash
python main.py
```

The application will start at `http://localhost:8201`

### Verify Installation

Check the server status:
```bash
curl http://localhost:8201/health
```

You should see something like this (`ai_ready` is `false`, with a reason, until the AI model is configured):
```json
{
  "status": "healthy",
  "openai_configured": true,
  "ai_ready": true,
  "ai_not_ready_reason": null,
  "cache_enabled": true,
  "environment": "local",
  "a2a_backend": "shim"
}
```

`GET /ready` answers 200 only when the AI model is configured, otherwise 503.

## 📊 Features

### ✅ In this release
- **Description, not rows**: The AI model receives a description of the data, never the rows. See [What the AI model receives](#what-the-ai-model-receives)
- **Input formats**: CSV, JSON, Excel, Parquet, TSV
- **Output formats**: CSV, JSON, Excel
- **Data dictionary**: Generate from a dictionary file (JSON, YAML, CSV, Excel, PDF), with or without a data file. The dictionary's content is sent to the AI model
- **Web Interface**: Drag-and-drop page, an About page and a usage dashboard
- **Multi-File Generation**: 1-20 files at once, returned as a ZIP
- **REST API**: Form upload routes and a JSON API under `/api/v1`
- **Choice of AI model**: A request can name a model from the server's allow-list (`GET /api/models`). Without a name the server default is used
- **Pattern detection**: The description notes
  - ID shapes (for example `MRN-<7 digits>`), never a real ID as an example
  - Email and phone formats
  - Currency values and their decimal places
  - Datetime formats including timestamps
- **Safety modes**: Three levels that control which text values the AI model may see:
  - **Strict**: No text value is sent. Numbers are rounded and ranges widened
  - **Balanced** (default): Repeated short category labels are sent for columns with up to 10 distinct values
  - **Permissive**: The same rule, for columns with up to 50 distinct values
- **Script cache**: The generated script is saved on the server's disk with the description it was written for, and reused for a later request with a similar description and the same number of rows
  - Cache hit indicators: ✓ for hit, − for miss
  - A cache hit skips the call to the AI model
- **Progress display**: Extract Metadata → Check Cache → AI Response → Execute → Validate, with the time each step took
- **Usage log**: One line per generation in `logs/usage/` with the time, method (AI model or cached), row and column counts and timings. `rotate_logs.py` archives log files older than 2 days

### Not in this release
- **Approval for real data**: Not approved for real study data or patient identifiers
- **Sign-in**: There is none. Anyone who can reach the site on the organisation network (VPN) can use it
- **Isolation of generated scripts**: Scripts are screened before running (only data libraries; no file, network or process access) but they run on the same server as the application. This is not full isolation
- **Batch generation**: Switched off. `POST /generate/batch` and `GET /batch/{batch_id}` answer 501
- **A generator without the AI model**: There is none. If the AI model is unavailable, generation fails with a clear error
- **A production environment**: There is none yet
- **Advanced statistics**: Basic distributions are described; relationships across several columns are not fully kept

## What the AI model receives

Rows are never sent. The model receives a description built in `src/core/metadata_extractor.py`:

- **Column names**: Always sent, exactly as they are in the file.
- **Every column**: Data type, number of values, empty values and distinct values.
- **Number columns**: Average, spread and similar summary numbers. In Balanced and Permissive modes, for a column with 20 or more values, this includes the real smallest, largest, middle and quartile values. In Strict mode, and for a column with fewer than 20 values, the numbers are rounded and the range is widened. A column whose name looks like an identifier (`patient_id`, `mrn`, `zip`, ...) sends no smallest, largest, middle or quartile value.
- **Date columns**: The range widened to whole months, or to whole years for columns named like a date of birth, in Strict mode, and for columns with fewer than 20 values. The exact earliest and latest dates are not sent.
- **Text columns**: Lengths, formats and how often the most common values occur. The values are replaced with placeholders (`value_0`, `value_1`, ...) unless they are repeated short category labels: 30 characters or fewer, occurring at least 5 times, in a column with 20 or more values and a name that does not look like an identifier, with no value that looks like an email, phone number, date or long number. Balanced mode allows up to 10 distinct labels, Permissive up to 50, Strict none.
- **A limit of this rule**: It cannot tell a category from a name. A person's name that occurs 5 or more times in a column with an ordinary name is treated as a category label and is sent in Balanced and Permissive modes.
- **Shared beginnings and endings**: Outside Strict mode, for a column with 20 or more values, a beginning or ending of up to 6 characters with no digits that many values share can be sent.
- **ID-shaped columns**: Described by shape (for example `MRN-<7 digits>`), never by a real example.
- **Relationships**: How strongly columns move together.
- **A data dictionary, if uploaded**: Its column names, types, descriptions, allowed values, ranges and patterns, cut to a size limit.

What is stored on the server:

- The description and the generated script are saved in the cache folder (`data/cache` by default) until the cache is cleared. A request with `use_cache=false` does not read or write the cache.
- The uploaded file is not written to the cache. While a request is processed it is held in memory, and the web framework may also keep it in a temporary file.
- An uploaded data dictionary, and a preview made from one, are kept in memory for up to 30 minutes after their last use.
- Column names from cached descriptions are returned by `GET /api/cache-info` and shown on the usage dashboard.

## 🖥️ Using the Web Interface

1. Open your browser to `http://localhost:8201`
2. Drag and drop your data file (CSV, JSON, Excel, etc.)
3. Adjust generation settings:
   - **Number of rows**: How many synthetic records to generate
   - **Match strictness**: How closely to match statistical properties (70-85% recommended)
   - **Number of files**: Generate 1-20 synthetic files at once
   - **Safety mode**: Strict, Balanced or Permissive (which text values the AI model may see)
   - **AI model**: Leave the server default or choose another model from the list
4. Click "Generate Synthetic Data"
5. Download your synthetic dataset (single file or ZIP for multiple)

## Calling this service (REST / MCP / A2A)

The service exposes one shared generation pipeline over **three interfaces**.
See [docs/INTEGRATION.md](docs/INTEGRATION.md) for full details.

| Interface | How to call |
|-----------|-------------|
| **REST** | `POST /generate`, `POST /metadata`, `POST /api/v1/generate` (JSON), etc. (FastAPI, default port 8201). See [docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md) |
| **MCP** | `python -m src.mcp_server` — tools: `generate_synthetic_data`, `extract_metadata` |
| **A2A** | `POST /a2a/mock-data-generator` with an encoded A2A Message envelope; AgentCard at `GET /.well-known/agent.json` |

### Quick MCP example

```bash
# Launch the MCP stdio server (connect via Claude Desktop or any MCP host)
python -m src.mcp_server
```

### Quick A2A example

```python
import asyncio, base64, pathlib
from a2a_runtime import A2AClient

csv_bytes = pathlib.Path("data.csv").read_bytes()
client = A2AClient()  # in-process dispatch

result = asyncio.run(client.call(
    "mock-data-generator",
    {"operation": "generate", "data_content": base64.b64encode(csv_bytes).decode(),
     "file_name": "data.csv", "num_rows": 100},
    correlation_id="req-001",
))
print(result["status"])  # "success"
```

---

## REST API Usage

### Generate synthetic data via API

```bash
# Single file generation
curl -X POST "http://localhost:8201/generate" \
  -F "file=@your_data.csv" \
  -F "num_rows=1000" \
  -F "match_threshold=0.8" \
  -F "output_format=csv" \
  -F "safety_mode=balanced" \
  --output synthetic_data.csv

# Multiple file generation (returns ZIP)
curl -X POST "http://localhost:8201/generate" \
  -F "file=@your_data.csv" \
  -F "file_count=5" \
  -F "output_format=csv" \
  -F "safety_mode=permissive" \
  --output synthetic_data.zip
```

### Choose the AI model

```bash
# Names a request may use
curl "http://localhost:8201/api/models"

# JSON API: "model" is optional; leave it out for the server default.
# A name that is not on the list is refused with 400.
curl -X POST "http://localhost:8201/api/v1/generate" \
  -H "Content-Type: application/json" \
  -d '{"csv_text": "widget_id,colour\nW001,red\nW002,blue\n", "num_rows": 20, "model": "gpt-5-nano"}'
```

### Extract metadata only

```bash
curl -X POST "http://localhost:8201/metadata" \
  -F "file=@your_data.csv" \
  -o metadata.json
```

### API Documentation

View interactive API docs at: `http://localhost:8201/docs`

## 🎯 Common Use Cases

This release is not approved for real study data or patient identifiers. Use it with data you are allowed to send to this server.

### 1. Create Test Data for Development
Upload a small sample and generate a larger test dataset with the same columns and similar statistics.

### 2. Generate From a Data Dictionary
Upload a dictionary and generate data that follows its column definitions. No data file is needed.

### 3. Fixtures for Automated Tests
Call `POST /api/v1/generate` from a script and save the rows it returns.

## ⚙️ Configuration

### Environment Variables

Key settings in `.env`:

```env
# Azure OpenAI (required: unset = /ready answers 503 and every generation request fails)
AZURE_OPENAI_ENDPOINT=https://<your-foundry>.openai.azure.com/
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=gpt-5-nano
SOLUTION_NAME=mock-data-generator
# Keyless by default (src/dcri_llm.py): `az login` locally, managed identity on ACA.
LLM_AUTH=identity
# LLM_AUTH=key + AZURE_OPENAI_API_KEY only for people without an Azure identity
# Optional: the models a request may choose (comma-separated deployment names).
# Unset = the built-in list in src/core/models.py. The default above is always allowed.
# LLM_ALLOWED_MODELS=<deployment-name-1>,<deployment-name-2>

# Application Settings
LOG_LEVEL=INFO
APP_PORT=8201

# Local Storage
USE_LOCAL_STORAGE=true
LOCAL_STORAGE_PATH=./data/local_storage
LOCAL_CACHE_PATH=./data/cache
```

### Running on Different Port

```bash
# Edit .env file
APP_PORT=8202

# Or override when running
APP_PORT=8080 python main.py
```

## 📁 Project Structure

```
Create-mockData-from-real-file/
├── src/
│   ├── core/           # Core modules (data loader, metadata, generation)
│   ├── api/            # API endpoints
│   ├── web/            # Web interface (HTML/JS/CSS)
│   └── utils/          # Utilities (config, logging)
├── data/
│   ├── samples/        # Sample data files
│   ├── cache/          # Cached generation scripts
│   └── local_storage/  # Created at start-up; not used by the current code
├── tests/              # Unit tests
├── infrastructure/     # Terraform/Bicep templates from an earlier plan (not the deployed route)
├── deploy/aca/         # Container Apps manifest (the deployed route)
├── docs/               # Documentation
├── main.py             # Application entry point
├── requirements.txt    # Python dependencies
└── .env.example        # Environment variables template
```

## 🧪 Testing

Run unit tests:
```bash
pytest tests/
```

Test with sample data:
```bash
# Sales data example
curl -X POST "http://localhost:8201/generate" \
  -F "file=@data/samples/sales_data.csv" \
  -F "match_threshold=0.85" \
  --output test_output.csv
```

## 🚢 Deployment

### Docker Deployment
```bash
docker build -t byod-synthetic:latest .
docker run -p 8201:8201 --env-file .env byod-synthetic:latest
```

### Azure Deployment
The service runs as a container on Azure Container Apps, built from `Dockerfile.aca` with the manifest in `deploy/aca/containerapp.yaml`. It is deployed through the organisation's guarded Container Apps procedure. There is no production environment yet.

The Terraform and Bicep templates in `infrastructure/` and the Cloud Run script in `deploy/cloudrun.sh` are kept for reference only. They are not the approved route.

See [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md).

## 📚 Documentation

- [Architecture Overview](docs/architecture-diagram.md) - System design and data flow
- [Developer Task List](docs/developer_tasklist.md) - Open work
- [Completed Tasks](archived/developer_tasklist_ARCHIVED.md) - Finished work archive
- [About Page](http://localhost:8201/about) - What is sent to the AI model, API examples and a diagram

## ⚠️ Known Limitations

- **Large Files**: The whole file is read into memory. Uploads are limited to 50 MB by default (`MOCKDATA_MAX_UPLOAD_BYTES`)
- **Complex Relationships**: Multi-column correlations not fully preserved yet
- **Azure OpenAI is required**: If the AI model is not configured or not reachable, generation fails with a clear error. There is no other generator
- **No sign-in, no per-user limits**
- **Batch generation**: Switched off in this release

## 🛠️ Troubleshooting

### Port already in use
```bash
# Kill process on port 8201
kill -9 $(lsof -t -i:8201)
```

### Import errors
```bash
# Reinstall dependencies
pip install --upgrade -r requirements.txt
```

### AI model not configured
`GET /ready` answers 503 and gives the reason. Set `AZURE_OPENAI_ENDPOINT` in `.env` and sign in with `az login` (or use `LLM_AUTH=key` with `AZURE_OPENAI_API_KEY`). Generation does not work without the AI model.

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is proprietary and confidential.

## 🆘 Support

- Check the [documentation](docs/)
- Submit issues on GitHub
- Contact the development team

## 🔍 Status Endpoints

- **Health Check**: `http://localhost:8201/health`
- **API Info**: `http://localhost:8201/api`
- **Interactive Docs**: `http://localhost:8201/docs`
- **Web Interface**: `http://localhost:8201`

## 🏗️ Current Development Status

Release 1.0 work is tracked in Jira epic ADP-40. Open items are listed in [docs/developer_tasklist.md](docs/developer_tasklist.md); completed items are in [archived/developer_tasklist_ARCHIVED.md](archived/developer_tasklist_ARCHIVED.md).

---

**Data note**: Your uploaded file is sent to this server and analysed there. Rows are not sent to the AI model; a description of the data is (see [What the AI model receives](#what-the-ai-model-receives)). The description and the generated script are stored in the server's cache folder. This release has not been approved for real study data or patient identifiers.
