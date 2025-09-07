# BYOD Synthetic Data Generator

Generate privacy-safe synthetic data that preserves the statistical properties of your original data without exposing sensitive information.

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
# Edit .env to add your Azure OpenAI credentials (optional)
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

You should see:
```json
{
  "status": "healthy",
  "openai_configured": false,
  "cache_enabled": true,
  "environment": "local"
}
```

## 📊 Features

- **Privacy-First**: LLM never sees actual data values, only statistical metadata
- **Multiple Formats**: Supports CSV, JSON, Excel, Parquet, TSV
- **Statistical Preservation**: Maintains distributions, correlations, and patterns
- **Intelligent Caching**: Reuses generation scripts for similar datasets
- **Web Interface**: User-friendly drag-and-drop interface
- **REST API**: Programmatic access for automation
- **Local-First**: Works without cloud services

## 🖥️ Using the Web Interface

1. Open your browser to `http://localhost:8201`
2. Drag and drop your data file (CSV, JSON, Excel, etc.)
3. Adjust generation settings:
   - **Number of rows**: How many synthetic records to generate
   - **Match strictness**: How closely to match statistical properties (70-85% recommended)
4. Click "Generate Synthetic Data"
5. Download your synthetic dataset

## 🔌 API Usage

### Generate synthetic data via API

```bash
curl -X POST "http://localhost:8201/generate" \
  -F "file=@your_data.csv" \
  -F "num_rows=1000" \
  -F "match_threshold=0.8" \
  -F "output_format=csv" \
  --output synthetic_data.csv
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

### 1. Remove PHI from Medical Data
```python
# Upload medical records with patient information
# Get back statistically similar data without any real patient details
```

### 2. Create Test Data for Development
```python
# Upload small production sample
# Generate large test dataset maintaining relationships and patterns
```

### 3. Share Data Safely
```python
# Upload sensitive financial data
# Generate shareable synthetic version for vendors or partners
```

## ⚙️ Configuration

### Environment Variables

Key settings in `.env`:

```env
# Azure OpenAI (optional - enables LLM generation)
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-key-here

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
│   └── local_storage/  # Temporary storage
├── tests/              # Unit tests
├── infrastructure/     # IaC scripts (Terraform/Bicep)
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
```bash
cd infrastructure/terraform
terraform init
terraform apply
```

See [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) for detailed instructions.

## 📚 Documentation

- [User Guide](docs/USER_GUIDE.md) - Detailed usage instructions
- [API Documentation](docs/API_DOCUMENTATION.md) - Complete API reference
- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md) - Production deployment
- [Task List](TASK_LIST.md) - Development roadmap

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

### No OpenAI credentials
The system works without Azure OpenAI using template-based generation. For enhanced AI generation, add credentials to `.env`.

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

---

**Note**: This tool ensures that sensitive data never leaves your environment. Only statistical metadata is used for generation, making it safe for PHI, PII, and other confidential information.