# Docker Deployment Guide for BYOD Synthetic Data Generator

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+ (for local development)
- Azure CLI (for Azure deployment)
- Azure Container Registry (ACR) access

## Local Development with Docker

### 1. Build the Docker Image

```bash
# Build the image
docker build -t byod-synthetic-generator:latest .

# Or use docker-compose
docker-compose build
```

### 2. Run Locally with Docker

```bash
# Run with docker directly
docker run -d \
  --name byod-synthetic-generator \
  -p 8201:8201 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/cache:/app/cache \
  -v $(pwd)/logs:/app/logs \
  byod-synthetic-generator:latest

# Or use docker-compose (recommended)
docker-compose up -d
```

### 3. View Logs

```bash
# Docker logs
docker logs -f byod-synthetic-generator

# Or with docker-compose
docker-compose logs -f
```

### 4. Stop the Container

```bash
# Stop and remove container
docker stop byod-synthetic-generator
docker rm byod-synthetic-generator

# Or with docker-compose
docker-compose down
```

## Azure Deployment

### 1. Push to Azure Container Registry (ACR)

```bash
# Login to Azure
az login

# Login to ACR
az acr login --name <your-acr-name>

# Tag the image
docker tag byod-synthetic-generator:latest <your-acr-name>.azurecr.io/byod-synthetic-generator:latest

# Push to ACR
docker push <your-acr-name>.azurecr.io/byod-synthetic-generator:latest
```

### 2. Deploy to Azure Container Instances (ACI)

```bash
# Create container instance
az container create \
  --resource-group <your-resource-group> \
  --name byod-synthetic-generator \
  --image <your-acr-name>.azurecr.io/byod-synthetic-generator:latest \
  --cpu 2 \
  --memory 4 \
  --registry-login-server <your-acr-name>.azurecr.io \
  --registry-username <acr-username> \
  --registry-password <acr-password> \
  --ports 8201 \
  --environment-variables \
    AZURE_OPENAI_ENDPOINT=<your-endpoint> \
    AZURE_OPENAI_API_KEY=<your-api-key> \
    AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=<your-deployment> \
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME=<your-embedding-deployment> \
  --dns-name-label byod-synthetic-gen \
  --location <your-location>
```

### 3. Deploy to Azure App Service

```bash
# Create App Service Plan
az appservice plan create \
  --name byod-synthetic-plan \
  --resource-group <your-resource-group> \
  --sku B2 \
  --is-linux

# Create Web App
az webapp create \
  --resource-group <your-resource-group> \
  --plan byod-synthetic-plan \
  --name byod-synthetic-app \
  --deployment-container-image-name <your-acr-name>.azurecr.io/byod-synthetic-generator:latest

# Configure container settings
az webapp config container set \
  --name byod-synthetic-app \
  --resource-group <your-resource-group> \
  --docker-custom-image-name <your-acr-name>.azurecr.io/byod-synthetic-generator:latest \
  --docker-registry-server-url https://<your-acr-name>.azurecr.io \
  --docker-registry-server-user <acr-username> \
  --docker-registry-server-password <acr-password>

# Set environment variables
az webapp config appsettings set \
  --resource-group <your-resource-group> \
  --name byod-synthetic-app \
  --settings \
    AZURE_OPENAI_ENDPOINT=<your-endpoint> \
    AZURE_OPENAI_API_KEY=<your-api-key> \
    AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=<your-deployment> \
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME=<your-embedding-deployment> \
    WEBSITES_PORT=8201
```

### 4. Deploy to Azure Kubernetes Service (AKS)

Create a Kubernetes deployment file (`k8s-deployment.yaml`):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: byod-synthetic-generator
spec:
  replicas: 3
  selector:
    matchLabels:
      app: byod-synthetic-generator
  template:
    metadata:
      labels:
        app: byod-synthetic-generator
    spec:
      containers:
      - name: byod-synthetic-generator
        image: <your-acr-name>.azurecr.io/byod-synthetic-generator:latest
        ports:
        - containerPort: 8201
        env:
        - name: AZURE_OPENAI_ENDPOINT
          valueFrom:
            secretKeyRef:
              name: byod-secrets
              key: azure-openai-endpoint
        - name: AZURE_OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: byod-secrets
              key: azure-openai-api-key
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
---
apiVersion: v1
kind: Service
metadata:
  name: byod-synthetic-service
spec:
  selector:
    app: byod-synthetic-generator
  ports:
  - port: 80
    targetPort: 8201
  type: LoadBalancer
```

Deploy to AKS:

```bash
# Get AKS credentials
az aks get-credentials --resource-group <your-resource-group> --name <your-aks-cluster>

# Create secrets
kubectl create secret generic byod-secrets \
  --from-literal=azure-openai-endpoint=<your-endpoint> \
  --from-literal=azure-openai-api-key=<your-api-key>

# Apply deployment
kubectl apply -f k8s-deployment.yaml

# Check deployment status
kubectl get deployments
kubectl get pods
kubectl get services
```

## Environment Variables

Required environment variables for all deployments:

- `AZURE_OPENAI_ENDPOINT`: Your Azure OpenAI endpoint
- `AZURE_OPENAI_API_KEY`: Your Azure OpenAI API key
- `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`: Name of your chat model deployment
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME`: Name of your embedding model deployment

Optional environment variables:

- `AZURE_STORAGE_CONNECTION_STRING`: For blob storage
- `COSMOS_ENDPOINT`: For Cosmos DB
- `COSMOS_KEY`: Cosmos DB access key
- `AZURE_SEARCH_ENDPOINT`: For Azure Cognitive Search
- `AZURE_SEARCH_KEY`: Azure Search API key
- `AZURE_KEY_VAULT_URL`: For Key Vault integration

## Health Check

The application exposes a health endpoint at `/health` which can be used for container health checks and monitoring.

## Security Considerations

1. **Never hardcode secrets** - Use environment variables or Azure Key Vault
2. **Use managed identities** when possible for Azure resource access
3. **Enable HTTPS** in production deployments
4. **Scan images** for vulnerabilities using Azure Container Registry scanning
5. **Run as non-root user** (already configured in Dockerfile)

## Troubleshooting

### Container won't start
- Check logs: `docker logs byod-synthetic-generator`
- Verify environment variables are set correctly
- Ensure required Azure services are accessible

### Connection issues
- Verify network configuration and firewall rules
- Check if the container is running: `docker ps`
- Test health endpoint: `curl http://localhost:8201/health`

### Performance issues
- Increase container resources (CPU/Memory)
- Enable caching features
- Consider scaling horizontally in AKS

## CI/CD Pipeline Example

For automated deployment, add this to your Azure DevOps pipeline:

```yaml
trigger:
  branches:
    include:
      - main

pool:
  vmImage: 'ubuntu-latest'

variables:
  dockerRegistryServiceConnection: 'acr-connection'
  imageRepository: 'byod-synthetic-generator'
  containerRegistry: 'yourregistry.azurecr.io'
  dockerfilePath: '$(Build.SourcesDirectory)/Dockerfile'
  tag: '$(Build.BuildId)'

stages:
- stage: Build
  jobs:
  - job: Build
    steps:
    - task: Docker@2
      inputs:
        command: buildAndPush
        repository: $(imageRepository)
        dockerfile: $(dockerfilePath)
        containerRegistry: $(dockerRegistryServiceConnection)
        tags: |
          $(tag)
          latest

- stage: Deploy
  jobs:
  - job: Deploy
    steps:
    - task: AzureWebAppContainer@1
      inputs:
        azureSubscription: 'azure-subscription'
        appName: 'byod-synthetic-app'
        containers: $(containerRegistry)/$(imageRepository):$(tag)
```