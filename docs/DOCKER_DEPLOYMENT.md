# Docker Guide for BYOD Synthetic Data Generator

This guide covers running the service in a container on your own machine. The deployed service runs on Azure Container Apps from `Dockerfile.aca`; see [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md). There is no production environment yet.

Do not upload real study data or patient identifiers: this release has not been approved for them.

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+ (optional)
- An Azure OpenAI endpoint. Generation does not work without the AI model.

## The Dockerfiles

| File | Used for |
|------|----------|
| `Dockerfile.aca` | The deployed image (Azure Container Apps). Base image pinned by digest, pinned libraries, non-root user |
| `Dockerfile` | Local runs, port 8201, non-root user |
| `Dockerfile.api` | Google Cloud Run, port 8080. Reference only, not the approved route |

## Run locally with Docker

```bash
# Build the image
docker build -t byod-synthetic-generator:latest .

# Run it. The cache and logs are kept on your machine in ./data and ./logs.
docker run -d \
  --name byod-synthetic-generator \
  -p 8201:8201 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  byod-synthetic-generator:latest
```

Signing in to Azure OpenAI from a local container: outside Azure, `LLM_AUTH=identity` uses the Azure CLI sign-in (`az login`) of the environment the app runs in. A sign-in on your own machine is not inside the container. The simplest setting for a local container is `LLM_AUTH=key` with `AZURE_OPENAI_API_KEY` in your `.env`. Never commit `.env`.

`docker-compose.yml` builds and runs the same image (`docker-compose up -d`). It also passes settings for Blob Storage, Cosmos DB, AI Search and Key Vault from an earlier plan; the application does not read them.

## Logs and stopping

```bash
docker logs -f byod-synthetic-generator

docker stop byod-synthetic-generator
docker rm byod-synthetic-generator
```

## Settings

| Setting | Needed | What it does |
|---------|--------|--------------|
| `AZURE_OPENAI_ENDPOINT` | yes | Address of the Azure OpenAI resource. Without it `/ready` answers 503 and every generation request fails |
| `LLM_AUTH` | no | `identity` (default: `az login` locally, managed identity when deployed) or `key` |
| `AZURE_OPENAI_API_KEY` | only with `LLM_AUTH=key` | Key for people without an Azure identity |
| `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` | no | The server default model (default `gpt-5-nano`) |
| `LLM_ALLOWED_MODELS` | no | Comma-separated models a request may choose. Unset = the built-in list in `src/core/models.py` |
| `LLM_REASONING_EFFORT` | no | Default `low`; `off` = do not send |
| `SOLUTION_NAME` | no | Name written into the AI call telemetry lines |
| `ALLOWED_ORIGINS` | no | CORS: comma-separated origins allowed to call the site from a browser |
| `MOCKDATA_MAX_UPLOAD_BYTES` | no | Largest request body on the upload routes (default 50 MB) |
| `MOCKDATA_API_KEY` | no | If set, `/api/v1` requests must send it in `X-API-Key`. Other routes never check a key |
| `MOCKDATA_API_MAX_BYTES` | no | Largest request body on `/api/v1` (default 10 MB) |
| `GENERATOR_VERSION` | no | Part of every cache key (default `1.1`). Raising it retires every cached script |
| `LOCAL_CACHE_PATH` | no | Folder for cached descriptions and scripts (default `./data/cache`) |
| `APP_PORT` | no | Port (default 8201) |

## Health check

```bash
# Liveness: always 200 while the process is up
curl http://localhost:8201/health

# Readiness: 200 only when the AI model is configured, otherwise 503 with the reason
curl -i http://localhost:8201/ready
```

## What the container can and cannot do

- The process runs as a non-root user.
- Scripts written by the AI model are screened (only data libraries; no file, network or process access) and then run as a separate process inside the same container. This is not full isolation.
- The service has no sign-in. Do not publish the port beyond your own machine or the organisation network.

## Troubleshooting

### Container will not start
- Check logs: `docker logs byod-synthetic-generator`
- Check that `.env` exists and holds `AZURE_OPENAI_ENDPOINT`

### Generation fails with status 503
- The AI model is not configured or the sign-in failed. `curl -i http://localhost:8201/ready` gives the reason

### Connection issues
- Check the container is running: `docker ps`
- Test the health endpoint: `curl http://localhost:8201/health`
