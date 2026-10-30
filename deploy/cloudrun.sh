#!/usr/bin/env bash
# deploy/cloudrun.sh — Deploy the BYOD Mock Data Generator to Google Cloud Run.
#
# This script:
#   1. Ensures the Artifact Registry repository 'apps' exists (creates it if not).
#   2. Builds the Dockerfile.api image using Cloud Build (cloudbuild.yaml).
#   3. Deploys the image to Cloud Run as a public, unauthenticated service.
#   4. Optionally forwards Azure OpenAI credentials as Cloud Run env vars so
#      real (non-fallback) generation works in the deployed service.
#
# Prerequisites:
#   - gcloud CLI authenticated: gcloud auth login
#   - Billing enabled on the project
#   - APIs enabled: Cloud Build, Cloud Run, Artifact Registry
#     gcloud services enable cloudbuild.googleapis.com run.googleapis.com \
#       artifactregistry.googleapis.com
#
# Required environment variables:
#   PROJECT_ID   — GCP project ID (no default; script exits if not set)
#
# Optional environment variables:
#   REGION       — GCP region (default: us-central1)
#   SERVICE      — Cloud Run service name (default: mock-data-generator-api)
#
# Optional Azure OpenAI credentials (passed through if set; otherwise the
# service runs with the deterministic fallback generator):
#   AZURE_OPENAI_API_KEY
#   AZURE_OPENAI_ENDPOINT
#   AZURE_OPENAI_CHAT_DEPLOYMENT_NAME
#   AZURE_OPENAI_API_VERSION
#
# Usage:
#   PROJECT_ID=my-gcp-project ./deploy/cloudrun.sh
#   PROJECT_ID=my-gcp-project REGION=us-east1 ./deploy/cloudrun.sh

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
: "${PROJECT_ID:?ERROR: PROJECT_ID environment variable is required}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-mock-data-generator-api}"
ARTIFACT_REPO="apps"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/${SERVICE}:latest"

echo "=== BYOD Mock Data Generator — Cloud Run Deployment ==="
echo "  Project   : ${PROJECT_ID}"
echo "  Region    : ${REGION}"
echo "  Service   : ${SERVICE}"
echo "  Image     : ${IMAGE}"
echo ""

# ---------------------------------------------------------------------------
# Ensure Artifact Registry repository exists
# ---------------------------------------------------------------------------
echo "--- Ensuring Artifact Registry repository '${ARTIFACT_REPO}' exists ---"
gcloud artifacts repositories create "${ARTIFACT_REPO}" \
    --repository-format=docker \
    --location="${REGION}" \
    --project="${PROJECT_ID}" \
    --description="Container images for BYOD services" \
    2>/dev/null || true
echo "    OK (repository already existed or was just created)"
echo ""

# ---------------------------------------------------------------------------
# Configure Docker auth for Artifact Registry
# ---------------------------------------------------------------------------
echo "--- Configuring Docker authentication ---"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
echo ""

# ---------------------------------------------------------------------------
# Build image via Cloud Build (uses cloudbuild.yaml in repo root)
# ---------------------------------------------------------------------------
echo "--- Submitting Cloud Build (Dockerfile.api -> ${IMAGE}) ---"
gcloud builds submit \
    --config cloudbuild.yaml \
    --substitutions="_IMAGE=${IMAGE}" \
    --project="${PROJECT_ID}" \
    .
echo ""

# ---------------------------------------------------------------------------
# Build optional --set-env-vars flag for Azure OpenAI credentials.
# The flag is only included when at least one variable is set, so the deploy
# still works cleanly in environments without Azure credentials (the service
# uses the deterministic fallback generation path in that case).
# ---------------------------------------------------------------------------
ENV_VARS=""
ENV_PAIRS=()

if [[ -n "${AZURE_OPENAI_API_KEY:-}" ]]; then
    # Cloud Run has no Azure managed identity, so dcri_llm must use the key.
    ENV_PAIRS+=("LLM_AUTH=key")
    ENV_PAIRS+=("AZURE_OPENAI_API_KEY=${AZURE_OPENAI_API_KEY}")
fi
ENV_PAIRS+=("SOLUTION_NAME=${SOLUTION_NAME:-mock-data-generator}")
if [[ -n "${AZURE_OPENAI_ENDPOINT:-}" ]]; then
    ENV_PAIRS+=("AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}")
fi
if [[ -n "${AZURE_OPENAI_CHAT_DEPLOYMENT_NAME:-}" ]]; then
    ENV_PAIRS+=("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=${AZURE_OPENAI_CHAT_DEPLOYMENT_NAME}")
fi
if [[ -n "${AZURE_OPENAI_API_VERSION:-}" ]]; then
    ENV_PAIRS+=("AZURE_OPENAI_API_VERSION=${AZURE_OPENAI_API_VERSION}")
fi

if [[ ${#ENV_PAIRS[@]} -gt 0 ]]; then
    # Join array with commas
    JOINED=$(printf "%s," "${ENV_PAIRS[@]}")
    JOINED="${JOINED%,}"  # strip trailing comma
    ENV_VARS="--set-env-vars=${JOINED}"
    echo "--- Azure OpenAI credentials detected; will pass ${#ENV_PAIRS[@]} env var(s) ---"
else
    echo "--- No Azure OpenAI credentials found; deploying with fallback generation ---"
fi
echo ""

# ---------------------------------------------------------------------------
# Deploy to Cloud Run
# ---------------------------------------------------------------------------
echo "--- Deploying to Cloud Run (unauthenticated) ---"
gcloud run deploy "${SERVICE}" \
    --image "${IMAGE}" \
    --region "${REGION}" \
    --platform managed \
    --allow-unauthenticated \
    --port 8080 \
    --project="${PROJECT_ID}" \
    ${ENV_VARS}
echo ""

# ---------------------------------------------------------------------------
# Retrieve and display the service URL
# ---------------------------------------------------------------------------
SERVICE_URL=$(gcloud run services describe "${SERVICE}" \
    --region "${REGION}" \
    --project="${PROJECT_ID}" \
    --format="value(status.url)")

echo "============================================================"
echo "  Deployment complete!"
echo "  Service URL : ${SERVICE_URL}"
echo ""
echo "  Health check:"
echo "    curl ${SERVICE_URL}/health"
echo ""
echo "  Agent card:"
echo "    curl ${SERVICE_URL}/.well-known/agent.json"
echo ""
echo "  End-to-end A2A proof:"
echo "    python3 scripts/e2e_a2a_check.py --url ${SERVICE_URL}"
echo "============================================================"
