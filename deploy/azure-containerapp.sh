#!/usr/bin/env bash
# deploy/azure-containerapp.sh — DEFAULT deploy target (Azure Container Apps).
#
# Deploys main:app (agent_id "mock-data-generator") as a publicly-reachable
# Azure Container App using Azure Container Registry for the image.
#
# ============================================================
# REGISTRY AUTH STRATEGY — ACR admin credentials
# ============================================================
# This script uses the simplest reliable approach: it enables the built-in
# ACR admin account and passes the registry server / username / password
# directly to `az containerapp create/update` via --registry-server,
# --registry-username, and --registry-password.
#
# Trade-off:
#   + No extra role assignments or managed-identity wiring needed.
#   + Works immediately after `az acr update --admin-enabled true`.
#   - The admin credential is a long-lived static secret; rotate regularly.
#
# Alternative (more secure): assign the AcrPull role to the Container App's
# system-assigned managed identity and omit the registry-* flags.  Switch to
# that approach for production workloads.
# ============================================================
#
# Required environment variable:
#   ACR_NAME   — globally-unique ACR name (5–50 alphanumeric chars, no dashes)
#
# Optional environment variables (with defaults):
#   RESOURCE_GROUP   default: rg-mock-data-generator
#   LOCATION         default: eastus
#   ACA_ENV          default: aca-env-mock-data
#   APP_NAME         default: mock-data-generator-api
#   IMAGE_TAG        default: latest
#
# Optional Azure OpenAI credentials (passed through if set; otherwise the
# service uses the deterministic fallback generator):
#   AZURE_OPENAI_API_KEY
#   AZURE_OPENAI_ENDPOINT
#   AZURE_OPENAI_CHAT_DEPLOYMENT_NAME
#   AZURE_OPENAI_API_VERSION
#
# Usage:
#   ACR_NAME=myacr ./deploy/azure-containerapp.sh
#
#   ACR_NAME=myacr \
#     RESOURCE_GROUP=rg-demo \
#     AZURE_OPENAI_API_KEY=<key> \
#     AZURE_OPENAI_ENDPOINT=<endpoint> \
#     AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=<deployment> \
#     AZURE_OPENAI_API_VERSION=2024-02-01 \
#     ./deploy/azure-containerapp.sh
#
# SECURITY NOTE:
#   External ingress is PUBLIC (unauthenticated) — suitable for temporary demos
#   and smoke-testing only.  Add Azure API Management, Container App auth
#   (Easy Auth / Azure AD), or a reverse proxy with authN before real-data use.
#   The service itself never sends raw data to the LLM — it works with
#   statistical metadata only (see src/core/generation_service.py).

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration — override via environment variables
# ---------------------------------------------------------------------------
: "${ACR_NAME:?ERROR: ACR_NAME is required (globally-unique 5-50 alphanumeric chars)}"
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-mock-data-generator}"
LOCATION="${LOCATION:-eastus}"
ACA_ENV="${ACA_ENV:-aca-env-mock-data}"
APP_NAME="${APP_NAME:-mock-data-generator-api}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

ACR_LOGIN_SERVER="${ACR_NAME}.azurecr.io"
IMAGE_REF="${ACR_LOGIN_SERVER}/${APP_NAME}:${IMAGE_TAG}"

echo "=== BYOD Mock Data Generator — Azure Container Apps Deployment ==="
echo "  Resource Group : ${RESOURCE_GROUP}"
echo "  Location       : ${LOCATION}"
echo "  ACR            : ${ACR_LOGIN_SERVER}"
echo "  ACA Environment: ${ACA_ENV}"
echo "  App Name       : ${APP_NAME}"
echo "  Image          : ${IMAGE_REF}"
echo ""

# ---------------------------------------------------------------------------
# 1. Resource group (idempotent)
# ---------------------------------------------------------------------------
echo "--- Creating / verifying resource group '${RESOURCE_GROUP}' ---"
az group create \
    --name "${RESOURCE_GROUP}" \
    --location "${LOCATION}" \
    --output none
echo "    OK"
echo ""

# ---------------------------------------------------------------------------
# 2. Azure Container Registry (idempotent)
# ---------------------------------------------------------------------------
echo "--- Creating / verifying ACR '${ACR_NAME}' (Basic SKU) ---"
az acr create \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${ACR_NAME}" \
    --sku Basic \
    --location "${LOCATION}" \
    --output none \
    2>/dev/null || true
echo "    OK (already existed or was just created)"
echo ""

# ---------------------------------------------------------------------------
# 3. Build image in ACR (runs the build in the cloud; no local Docker needed)
# ---------------------------------------------------------------------------
echo "--- Building image via ACR build (Dockerfile.api -> ${IMAGE_REF}) ---"
az acr build \
    --registry "${ACR_NAME}" \
    --image "${APP_NAME}:${IMAGE_TAG}" \
    --file Dockerfile.api \
    .
echo "    Build complete"
echo ""

# ---------------------------------------------------------------------------
# 4. Container Apps extension + environment (idempotent)
# ---------------------------------------------------------------------------
echo "--- Installing / upgrading 'containerapp' CLI extension ---"
az extension add --name containerapp --upgrade --output none 2>/dev/null || true
echo "    OK"
echo ""

echo "--- Creating / verifying Container Apps environment '${ACA_ENV}' ---"
az containerapp env create \
    --name "${ACA_ENV}" \
    --resource-group "${RESOURCE_GROUP}" \
    --location "${LOCATION}" \
    --output none \
    2>/dev/null || true
echo "    OK (already existed or was just created)"
echo ""

# ---------------------------------------------------------------------------
# 5. Retrieve ACR admin credentials
# ---------------------------------------------------------------------------
echo "--- Enabling ACR admin account and retrieving credentials ---"
az acr update \
    --name "${ACR_NAME}" \
    --admin-enabled true \
    --output none

ACR_USERNAME=$(az acr credential show \
    --name "${ACR_NAME}" \
    --query "username" \
    --output tsv)

ACR_PASSWORD=$(az acr credential show \
    --name "${ACR_NAME}" \
    --query "passwords[0].value" \
    --output tsv)
echo "    Credentials retrieved"
echo ""

# ---------------------------------------------------------------------------
# 6. Build Azure OpenAI secret + env-var arrays (only when key is present)
# ---------------------------------------------------------------------------
SECRETS_ARGS=()
ENV_VAR_ARGS=()

if [[ -n "${AZURE_OPENAI_API_KEY:-}" ]]; then
    echo "--- Azure OpenAI credentials detected; configuring full-fidelity generation ---"
    # Store the API key as a Container App secret (never exposed in plain env)
    SECRETS_ARGS+=(
        "openai-key=${AZURE_OPENAI_API_KEY}"
    )
    # Reference the secret plus pass the other non-sensitive vars as plain env
    ENV_VAR_ARGS+=(
        "AZURE_OPENAI_API_KEY=secretref:openai-key"
        "AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT:-}"
        "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=${AZURE_OPENAI_CHAT_DEPLOYMENT_NAME:-}"
        "AZURE_OPENAI_API_VERSION=${AZURE_OPENAI_API_VERSION:-2024-02-01}"
    )
    echo "    API key stored as Container App secret 'openai-key'."
    echo "    Non-sensitive Azure OpenAI vars passed as plain environment variables."
else
    echo "--- No AZURE_OPENAI_API_KEY found; deploying with deterministic fallback generation ---"
    echo "    Set AZURE_OPENAI_API_KEY (+ optional AZURE_OPENAI_ENDPOINT,"
    echo "    AZURE_OPENAI_CHAT_DEPLOYMENT_NAME, AZURE_OPENAI_API_VERSION)"
    echo "    and re-run to enable full-fidelity LLM-assisted generation."
fi
echo ""

# ---------------------------------------------------------------------------
# 7. Build az containerapp CLI argument fragments
# ---------------------------------------------------------------------------
# Convert arrays to properly-quoted argument strings for the CLI.
# Secrets are passed as space-separated key=value pairs after --secrets.
# Env vars are passed as space-separated key=value pairs after --env-vars.
SECRET_FLAG=()
if [[ ${#SECRETS_ARGS[@]} -gt 0 ]]; then
    SECRET_FLAG=(--secrets "${SECRETS_ARGS[@]}")
fi

ENV_FLAG=()
if [[ ${#ENV_VAR_ARGS[@]} -gt 0 ]]; then
    ENV_FLAG=(--env-vars "${ENV_VAR_ARGS[@]}")
fi

# ---------------------------------------------------------------------------
# 8. Create OR update the Container App
# ---------------------------------------------------------------------------
# We attempt create first; if the app already exists we update it.
echo "--- Deploying Container App '${APP_NAME}' ---"

if az containerapp show \
    --name "${APP_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --output none 2>/dev/null; then

    echo "    App exists — updating image and configuration..."
    az containerapp update \
        --name "${APP_NAME}" \
        --resource-group "${RESOURCE_GROUP}" \
        --image "${IMAGE_REF}" \
        --registry-server "${ACR_LOGIN_SERVER}" \
        --registry-username "${ACR_USERNAME}" \
        --registry-password "${ACR_PASSWORD}" \
        "${SECRET_FLAG[@]+"${SECRET_FLAG[@]}"}" \
        "${ENV_FLAG[@]+"${ENV_FLAG[@]}"}" \
        --output none
else
    echo "    App does not exist — creating..."
    az containerapp create \
        --name "${APP_NAME}" \
        --resource-group "${RESOURCE_GROUP}" \
        --environment "${ACA_ENV}" \
        --image "${IMAGE_REF}" \
        --target-port 8080 \
        --ingress external \
        --registry-server "${ACR_LOGIN_SERVER}" \
        --registry-username "${ACR_USERNAME}" \
        --registry-password "${ACR_PASSWORD}" \
        "${SECRET_FLAG[@]+"${SECRET_FLAG[@]}"}" \
        "${ENV_FLAG[@]+"${ENV_FLAG[@]}"}" \
        --output none
fi

echo "    Deployment complete"
echo ""

# ---------------------------------------------------------------------------
# 9. Retrieve FQDN and print summary
# ---------------------------------------------------------------------------
FQDN=$(az containerapp show \
    --name "${APP_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --query "properties.configuration.ingress.fqdn" \
    --output tsv)

APP_URL="https://${FQDN}"

echo "============================================================"
echo "  Deployment complete!"
echo "  App URL : ${APP_URL}"
echo ""
echo "  Health check:"
echo "    curl ${APP_URL}/health"
echo ""
echo "  Agent card:"
echo "    curl ${APP_URL}/.well-known/agent.json"
echo ""
echo "  End-to-end A2A proof:"
echo "    python3 scripts/e2e_a2a_check.py --url ${APP_URL}"
echo ""
echo "  SECURITY REMINDER:"
echo "    External ingress is PUBLIC (unauthenticated) — for demo / smoke-test"
echo "    use only.  Add auth before any real-data or production use."
echo "    The service sends only statistical metadata (never raw rows) to the LLM."
echo "============================================================"
