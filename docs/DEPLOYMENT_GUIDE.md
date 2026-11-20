# Deployment Guide - BYOD Synthetic Data Generator

## Status of this release

- The service runs as one container on **Azure Container Apps**. That is the only approved route.
- As deployed, it is reachable only on the organisation network (VPN). **There is no production environment yet.**
- The service has **no sign-in**. Anyone who can reach it can use it.
- This release has **not been approved for real study data or patient identifiers**. No compliance assessment has been done.
- Generated scripts are screened before they run, but they run in the same container as the application. This is not full isolation.

## Table of Contents
1. [Local Development](#local-development)
2. [Settings](#settings)
3. [Azure Container Apps](#azure-container-apps)
4. [Health and readiness](#health-and-readiness)
5. [What the container stores](#what-the-container-stores)
6. [Files kept for reference only](#files-kept-for-reference-only)
7. [Troubleshooting](#troubleshooting)

## Local Development

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
# Edit .env: AZURE_OPENAI_ENDPOINT is required

# Sign in so the app can reach Azure OpenAI (LLM_AUTH=identity, the default)
az login

# Run application
python main.py
```

```bash
# Run tests
pytest

# Run with auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8201
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

Secrets are never written into a manifest or committed. `.env` is ignored by git.

On Azure Container Apps, `AZURE_CLIENT_ID` names the user-assigned managed identity the container signs in with.

`src/utils/config.py` also accepts settings for Blob Storage, Cosmos DB, AI Search, a tenant id and a client secret. The application code does not use them.

## Azure Container Apps

- Image: built from `Dockerfile.aca` for `linux/amd64`. The base image is pinned by digest and the libraries are pinned in `requirements-aca.txt` and `constraints-aca.txt`. The process runs as a non-root user that can write only to `data/` and `logs/`.
- Manifest: `deploy/aca/containerapp.yaml`. It holds placeholders, not real resource names. It sets `LLM_AUTH=identity`, so the container signs in to Azure OpenAI with a managed identity and no key.
- Deploying: follow the organisation's guarded Container Apps procedure. It is not described in this public repository.
- Replicas: the manifest runs exactly one. The cache, the uploaded dictionaries and the previews live on that one container's disk and memory, so more than one replica would not share them.

## Health and readiness

```bash
# Liveness: the process is up. Always 200.
curl https://<your-site>/health

# Readiness: 200 only when the AI model is configured, otherwise 503 with the reason.
curl -i https://<your-site>/ready
```

Generation work runs outside the event loop so that `/health` keeps answering during a long AI call.

## What the container stores

- `data/cache/`: for each cached script, the description of the data it was written for (column names, summary statistics, and the values the safety mode allows) and the script. Kept until the cache is cleared (`DELETE /cache` or `DELETE /api/cache/clear`, optional `older_than_days`).
- `logs/usage/`: one line per generation with the time, method, row and column counts and timings.
- Standard output: application log lines, and one `llm_call` telemetry line per AI call (counts and timings, no prompt text). When `TELEMETRY_BLOB_ACCOUNT_URL` is set, the telemetry lines are also written to that storage account.
- Uploaded files are not written to the cache. They are held in memory while a request is processed, and the web framework may keep a temporary file for that time.

A container's disk is lost when the container is replaced, so the cache starts empty after each deployment.

## Files kept for reference only

These are in the repository but are **not** the approved route, and this guide does not vouch for them:

- `infrastructure/terraform/`, `infrastructure/bicep/`: templates from an earlier plan (App Service, Function App, Blob Storage, Cosmos DB, AI Search, Key Vault). The application code does not use those services.
- `deploy/cloudrun.sh`, `cloudbuild.yaml`, `Dockerfile.api`, `.github/workflows/deploy-cloudrun.yml`: Google Cloud Run. They deploy with authentication required.
- `Dockerfile`, `docker-compose.yml`: local container runs. See [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md).

## Troubleshooting

1. **Every generation request fails with status 503:** the AI model is not configured. `GET /ready` gives the reason. Check `AZURE_OPENAI_ENDPOINT`, `LLM_AUTH` and the identity's access to the Azure OpenAI resource.

2. **Status 502 on generation:** the AI call or the generated script failed. No data is returned; there is no other generator.

3. **Status 413:** the request body is over `MOCKDATA_MAX_UPLOAD_BYTES` (or `MOCKDATA_API_MAX_BYTES` on `/api/v1`).

4. **Port already in use (local):**
```bash
lsof -i :8201
```
