# Deployment Guide - BYOD Synthetic Data Generator

## Table of Contents
1. [Local Development](#local-development)
2. [Azure Deployment](#azure-deployment)
3. [Docker Deployment](#docker-deployment)
4. [Production Configuration](#production-configuration)
5. [Monitoring & Maintenance](#monitoring--maintenance)

## Local Development

### Quick Start
```bash
# Clone repository
git clone https://github.com/your-org/Create-mockData-from-real-file.git
cd Create-mockData-from-real-file

# Setup Python environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run application
python main.py
```

### Development Tools
```bash
# Run tests
pytest tests/

# Format code
black src/ tests/
isort src/ tests/

# Lint code
flake8 src/
mypy src/

# Run with auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8201
```

## Azure Deployment

### Prerequisites
- Azure subscription
- Azure CLI installed
- Terraform or Bicep CLI
- Azure OpenAI resource (optional)

### Using Terraform

1. **Initialize Terraform:**
```bash
cd infrastructure/terraform
terraform init
```

2. **Create terraform.tfvars:**
```hcl
resource_group_name = "rg-byod-synthetic-prod"
location           = "East US"
environment        = "prod"
app_name          = "byod-synthetic"

# Sensitive variables
azure_openai_endpoint = "https://your-openai.openai.azure.com/"
azure_openai_api_key  = "your-api-key"
```

3. **Plan deployment:**
```bash
terraform plan
```

4. **Deploy infrastructure:**
```bash
terraform apply
```

5. **Deploy application code:**
```bash
# Using Azure CLI
az webapp deployment source config-zip \
  --resource-group rg-byod-synthetic-prod \
  --name byod-synthetic-prod-app \
  --src app.zip
```

### Using Bicep

1. **Deploy with Bicep:**
```bash
cd infrastructure/bicep

# Create resource group
az group create \
  --name rg-byod-synthetic-prod \
  --location "East US"

# Deploy infrastructure
az deployment group create \
  --resource-group rg-byod-synthetic-prod \
  --template-file main.bicep \
  --parameters environment=prod \
    azureOpenAIEndpoint="https://your-openai.openai.azure.com/" \
    azureOpenAIApiKey="your-api-key"
```

### CI/CD Pipeline (Azure DevOps)

Create `azure-pipelines.yml`:
```yaml
trigger:
  branches:
    include:
      - main
      - develop

pool:
  vmImage: 'ubuntu-latest'

variables:
  pythonVersion: '3.11'
  
stages:
- stage: Build
  jobs:
  - job: BuildJob
    steps:
    - task: UsePythonVersion@0
      inputs:
        versionSpec: '$(pythonVersion)'
      
    - script: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
      displayName: 'Install dependencies'
      
    - script: |
        pytest tests/ --junitxml=test-results.xml
      displayName: 'Run tests'
      
    - task: PublishTestResults@2
      inputs:
        testResultsFiles: 'test-results.xml'
        testRunTitle: 'Python Tests'
      
    - task: ArchiveFiles@2
      inputs:
        rootFolderOrFile: '$(System.DefaultWorkingDirectory)'
        includeRootFolder: false
        archiveType: 'zip'
        archiveFile: '$(Build.ArtifactStagingDirectory)/app.zip'
        
    - publish: $(Build.ArtifactStagingDirectory)/app.zip
      artifact: drop

- stage: Deploy
  dependsOn: Build
  condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))
  jobs:
  - deployment: DeployWeb
    environment: 'production'
    strategy:
      runOnce:
        deploy:
          steps:
          - task: AzureWebApp@1
            inputs:
              azureSubscription: 'Azure Connection'
              appType: 'webAppLinux'
              appName: 'byod-synthetic-prod-app'
              package: '$(Pipeline.Workspace)/drop/app.zip'
```

## Docker Deployment

### Create Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p data/local_storage data/cache data/samples logs

# Expose port
EXPOSE 8201

# Run application
CMD ["python", "main.py"]
```

### Build and Run with Docker
```bash
# Build image
docker build -t byod-synthetic:latest .

# Run container
docker run -d \
  --name byod-synthetic \
  -p 8201:8201 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  --env-file .env \
  byod-synthetic:latest

# View logs
docker logs -f byod-synthetic
```

### Docker Compose
Create `docker-compose.yml`:
```yaml
version: '3.8'

services:
  web:
    build: .
    ports:
      - "8201:8201"
    environment:
      - ENVIRONMENT=production
      - LOG_LEVEL=INFO
    env_file:
      - .env
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    restart: unless-stopped
    
  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
    restart: unless-stopped
    
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./certs:/etc/nginx/certs
    depends_on:
      - web
    restart: unless-stopped
```

Run with Docker Compose:
```bash
docker-compose up -d
docker-compose logs -f
docker-compose down
```

## Production Configuration

### Environment Variables
```env
# Production settings
ENVIRONMENT=production
LOG_LEVEL=INFO
APP_HOST=0.0.0.0
APP_PORT=8201

# Azure OpenAI (Required)
AZURE_OPENAI_ENDPOINT=https://prod-openai.openai.azure.com/
AZURE_OPENAI_API_KEY=${AZURE_OPENAI_API_KEY}
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=gpt-4
AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME=text-embedding-ada-002

# Azure Storage
AZURE_STORAGE_CONNECTION_STRING=${AZURE_STORAGE_CONNECTION_STRING}
BLOB_STORAGE_CONTAINER_NAME=synthetic-data-uploads

# Azure Cosmos DB
COSMOS_DB_ENDPOINT=https://prod-cosmos.documents.azure.com:443/
COSMOS_DB_KEY=${COSMOS_DB_KEY}
COSMOS_DB_DATABASE_NAME=SyntheticData
COSMOS_DB_CONTAINER_NAME=ProgramCatalog

# Azure Search
AZURE_SEARCH_ENDPOINT=https://prod-search.search.windows.net
AZURE_SEARCH_API_KEY=${AZURE_SEARCH_API_KEY}
AZURE_SEARCH_INDEX_NAME=program-vectors

# Security
USE_HTTPS=true
ALLOWED_ORIGINS=https://yourdomain.com
API_KEY_REQUIRED=true
```

### NGINX Configuration
Create `nginx.conf`:
```nginx
events {
    worker_connections 1024;
}

http {
    upstream app {
        server web:8201;
    }
    
    server {
        listen 80;
        server_name yourdomain.com;
        return 301 https://$server_name$request_uri;
    }
    
    server {
        listen 443 ssl http2;
        server_name yourdomain.com;
        
        ssl_certificate /etc/nginx/certs/cert.pem;
        ssl_certificate_key /etc/nginx/certs/key.pem;
        
        client_max_body_size 100M;
        
        location / {
            proxy_pass http://app;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 300s;
            proxy_connect_timeout 75s;
        }
        
        location /static {
            alias /app/src/web/static;
            expires 30d;
        }
    }
}
```

### Security Hardening

1. **API Authentication:**
```python
# Add to main.py
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Depends(api_key_header)):
    if settings.API_KEY_REQUIRED and api_key != settings.API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key
```

2. **Rate Limiting:**
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/generate")
@limiter.limit("10/minute")
async def generate_synthetic_data(...):
    ...
```

3. **CORS Configuration:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

## Monitoring & Maintenance

### Health Checks
```bash
# Basic health check
curl https://yourdomain.com/health

# Detailed status
curl https://yourdomain.com/api/status
```

### Logging
```python
# Configure production logging
import logging
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler(
    'logs/app.log',
    maxBytes=10485760,  # 10MB
    backupCount=10
)
handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s'
))
logger.addHandler(handler)
```

### Monitoring with Azure Application Insights
```python
from applicationinsights import TelemetryClient

tc = TelemetryClient(settings.APP_INSIGHTS_KEY)

# Track custom events
tc.track_event('synthetic_generation', {
    'rows': num_rows,
    'threshold': match_threshold,
    'format': output_format
})

# Track metrics
tc.track_metric('generation_time', elapsed_time)
tc.flush()
```

### Backup Strategy
```bash
# Backup Cosmos DB
az cosmosdb sql database backup list \
  --resource-group rg-byod-synthetic-prod \
  --account-name byod-synthetic-prod-cosmos \
  --database-name SyntheticData

# Backup Storage Account
azcopy copy \
  'https://prodstorage.blob.core.windows.net/synthetic-data-uploads/*' \
  'https://backupstorage.blob.core.windows.net/backup/' \
  --recursive
```

### Maintenance Tasks
```bash
# Clear old cache (weekly)
curl -X DELETE "https://yourdomain.com/cache?older_than_days=7"

# Update dependencies (monthly)
pip list --outdated
pip install --upgrade -r requirements.txt

# Database optimization (monthly)
az cosmosdb sql container throughput update \
  --resource-group rg-byod-synthetic-prod \
  --account-name byod-synthetic-prod-cosmos \
  --database-name SyntheticData \
  --name ProgramCatalog \
  --throughput 400
```

## Scaling Considerations

### Horizontal Scaling
```yaml
# Azure App Service scaling
az webapp scale \
  --resource-group rg-byod-synthetic-prod \
  --name byod-synthetic-prod-app \
  --instance-count 3

# Kubernetes deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: byod-synthetic
spec:
  replicas: 3
  selector:
    matchLabels:
      app: byod-synthetic
  template:
    metadata:
      labels:
        app: byod-synthetic
    spec:
      containers:
      - name: app
        image: byod-synthetic:latest
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
```

### Performance Optimization
1. **Enable caching** for repeated datasets
2. **Use CDN** for static assets
3. **Implement database indexes** for faster lookups
4. **Use async operations** for I/O-bound tasks
5. **Optimize container size** with multi-stage builds

## Troubleshooting Deployment

### Common Issues

1. **Port binding errors:**
```bash
# Check if port is in use
lsof -i :8201
# Kill process using port
kill -9 $(lsof -t -i:8201)
```

2. **Memory issues:**
```bash
# Increase container memory
docker run -m 4g byod-synthetic:latest
```

3. **SSL certificate issues:**
```bash
# Generate self-signed cert for testing
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes
```

4. **Database connection issues:**
```bash
# Test Cosmos DB connection
az cosmosdb show \
  --resource-group rg-byod-synthetic-prod \
  --name byod-synthetic-prod-cosmos
```

## Support

For deployment assistance:
- Review [Azure documentation](https://docs.microsoft.com/azure)
- Check [Docker documentation](https://docs.docker.com)
- Submit issues on GitHub