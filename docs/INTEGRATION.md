# Integration Guide — Calling the BYOD Mock Data Generator

The BYOD Synthetic Data Generator exposes its capabilities over **three
independent interfaces** that share a single core pipeline
(`src/core/generation_service.py`).  Choose the interface that best fits your
integration context.

---

## 1. REST API

The REST interface is the FastAPI application served at port 8201 by default.

### Key endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/generate` | Upload a file and download synthetic data |
| `POST` | `/metadata` | Extract structural/statistical metadata |
| `GET`  | `/health` | Service health + A2A backend identifier |
| `GET`  | `/docs` | Interactive Swagger UI |

### A2A-specific REST endpoints (new)

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/.well-known/agent.json` | Serve the AgentCard so callers can discover this agent |
| `POST` | `/a2a/mock-data-generator` | Receive an A2A Message envelope and return a response envelope |

### Example — generate CSV via REST

```bash
curl -X POST "http://localhost:8201/generate" \
  -F "file=@patients.csv" \
  -F "num_rows=500" \
  -F "output_format=csv" \
  -F "safety_mode=balanced" \
  --output synthetic_patients.csv
```

### Example — extract metadata via REST

```bash
curl -X POST "http://localhost:8201/metadata" \
  -F "file=@patients.csv" \
  -o metadata.json
```

---

## 2. MCP (Model Context Protocol)

The MCP interface exposes the same pipeline as a stdio server that any
MCP-compatible host (Claude Desktop, Cursor, custom agents) can connect to.

### Launch

```bash
# From the repo root with the virtualenv activated:
python -m src.mcp_server
```

The server communicates over stdin/stdout using the MCP protocol.

### Tools

#### `generate_synthetic_data`

Generate synthetic rows from a base64-encoded source file.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `data_content` | string | yes | Base64-encoded file bytes |
| `file_name` | string | no | Original file name, e.g. `"patients.csv"` |
| `num_rows` | integer | no | Rows to generate; omit to match source |
| `match_threshold` | number | no | Statistical match threshold 0–1 (default 0.8) |
| `output_format` | `"csv"` \| `"json"` | no | Output format (default `"csv"`) |
| `safety_mode` | `"balanced"` \| `"strict"` \| `"permissive"` | no | Privacy level (default `"balanced"`) |
| `use_cache` | boolean | no | Reuse cached generation code (default `true`) |

Returns: JSON string with `status`, `format`, `shape`, `data`, and `generation_info`.

#### `extract_metadata`

Extract statistical and structural metadata without generating synthetic data.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `data_content` | string | yes | Base64-encoded file bytes |
| `file_name` | string | no | Original file name |
| `safety_mode` | `"balanced"` \| `"strict"` \| `"permissive"` | no | Privacy level |

Returns: JSON string with `status` and `metadata`.

### MCP client configuration example (Claude Desktop)

```json
{
  "mcpServers": {
    "mock-data-generator": {
      "command": "python",
      "args": ["-m", "src.mcp_server"],
      "cwd": "/path/to/Create-mockData-from-real-file"
    }
  }
}
```

---

## 3. A2A (Agent-to-Agent)

The A2A interface enables peer-to-peer calls between agents using the
organisation's A2A wire contract.  The FastAPI app mounts the A2A transport
so no separate process is needed.

### AgentCard

The agent's discovery document is served at:

```
GET /.well-known/agent.json
```

Example response:

```json
{
  "capabilities": {"pushNotifications": false, "streaming": false},
  "defaultInputModes": ["application/json"],
  "defaultOutputModes": ["application/json"],
  "description": "Generates privacy-safe synthetic data ...",
  "methods": ["message/send", "tasks/get"],
  "name": "BYOD Mock Data Generator",
  "url": "/a2a/mock-data-generator",
  "version": "1.0.0",
  "x-dcri": {"agent_id": "mock-data-generator", "internal_only": false}
}
```

### Calling the agent

Send a `POST` request to `/a2a/mock-data-generator` with a JSON body produced
by `a2a_runtime.encode_message`.

#### Python example (in-process, using the shim)

```python
import asyncio, base64, pathlib
from a2a_runtime import A2AClient, encode_message

csv_bytes = pathlib.Path("patients.csv").read_bytes()
data_content = base64.b64encode(csv_bytes).decode()

client = A2AClient()  # uses default_registry for in-process dispatch

result = asyncio.run(client.call(
    "mock-data-generator",
    {
        "operation": "generate",
        "data_content": data_content,
        "file_name": "patients.csv",
        "num_rows": 100,
        "output_format": "csv",
    },
    correlation_id="req-001",
    cycle=1,
))
print(result["status"])  # "success"
```

#### HTTP example (remote call)

```python
import httpx, json
from a2a_runtime import encode_message, decode_message

envelope = encode_message(
    {
        "operation": "generate",
        "data_content": "<base64-csv>",
        "file_name": "data.csv",
        "num_rows": 200,
    },
    correlation_id="req-http-001",
    cycle=1,
    agent_id="mock-data-generator",
)

resp = httpx.post("https://<host>/a2a/mock-data-generator", json=envelope)
resp.raise_for_status()

result_payload, meta = decode_message(resp.json())
print(result_payload["status"])
```

### Wiring dcri-ct-graph to this agent

Point a graph node's `a2a_endpoint` at the agent URL:

```yaml
nodes:
  - id: mock-data
    a2a_endpoint: "https://<host>/a2a/mock-data-generator"
    agent_card_url: "https://<host>/.well-known/agent.json"
```

The graph coordinator discovers capabilities from the AgentCard and routes
`message/send` calls to `/a2a/mock-data-generator`.

### Supported `operation` values

| `operation` | Delegates to |
|-------------|-------------|
| `"generate"` (default) | `generation_service.generate()` |
| `"metadata"` or `"extract_metadata"` | `generation_service.extract_metadata()` |

---

## A2A Runtime — shim vs real package

The repo ships a pure-stdlib shim at `a2a_runtime/` that mirrors the public
API of the organisation's `dcri-a2a-core` package.

```python
from a2a_runtime import IS_A2A_SHIM, A2A_BACKEND
# IS_A2A_SHIM == True  → using bundled shim
# IS_A2A_SHIM == False → using real dcri-a2a-core package
```

The `/health` endpoint reports which backend is active:

```json
{"status": "healthy", ..., "a2a_backend": "shim"}
```

To switch to the real wire contract:

```bash
pip install dcri-a2a-core
```

No code changes are required — `a2a_runtime/__init__.py` prefers the real
package automatically.

---

## Authentication

Production authentication (bearer tokens, mTLS, Azure Managed Identity) is a
**deployment-level concern** and is not enforced by this service's A2A or MCP
layers directly.  Configure your API gateway or NGINX reverse proxy to require
authentication before traffic reaches these endpoints.

---

## Deploying to Google Cloud Run (public, unauthenticated)

The repo ships everything needed to deploy `main:app` (agent_id
`"mock-data-generator"`) as a real, publicly-reachable Cloud Run service.

> **WARNING:** `--allow-unauthenticated` makes the synthetic-data generation
> endpoint reachable by anyone on the internet.  This is acceptable for a
> **temporary demo or development smoke-test** but must not be used for
> long-running production workloads.  Add Cloud Run IAM bindings, a managed
> API gateway, or a Cloud Armor policy before promoting to production.

### One-command deploy

```bash
# Authenticate first:
gcloud auth login
gcloud config set project <YOUR_GCP_PROJECT_ID>

# Deploy:
PROJECT_ID=<YOUR_GCP_PROJECT_ID> ./deploy/cloudrun.sh

# Optionally pass Azure OpenAI credentials so real (non-fallback) generation
# is used in the deployed service:
PROJECT_ID=<project> \
  AZURE_OPENAI_API_KEY=<key> \
  AZURE_OPENAI_ENDPOINT=<endpoint> \
  AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=<deployment> \
  AZURE_OPENAI_API_VERSION=2024-02-01 \
  ./deploy/cloudrun.sh
```

The script:
1. Creates an Artifact Registry repo `apps` in the target region (idempotent).
2. Builds `Dockerfile.api` via Cloud Build (`cloudbuild.yaml`).
3. Deploys the image to Cloud Run (public, unauthenticated, port 8080).
4. Prints the live service URL.

Optional environment variables for `cloudrun.sh`:

| Variable | Default | Description |
|----------|---------|-------------|
| `PROJECT_ID` | *(required)* | GCP project ID |
| `REGION` | `us-central1` | GCP region |
| `SERVICE` | `mock-data-generator-api` | Cloud Run service name |

### GitHub Actions alternative

The workflow `.github/workflows/deploy-cloudrun.yml` performs the same steps
from CI via `workflow_dispatch`.

**Required secret** (Settings > Secrets and variables > Actions):

| Secret | Description |
|--------|-------------|
| `GCP_SA_KEY` | JSON key for a GCP Service Account with roles: `run.admin`, `cloudbuild.builds.editor`, `artifactregistry.admin`, `iam.serviceAccountUser`, `storage.admin` |

> **More secure alternative:** Workload Identity Federation avoids storing a
> long-lived JSON key in GitHub.  See the inline comments in
> `.github/workflows/deploy-cloudrun.yml` for the WIF migration path.

**Optional secrets** (enable real Azure OpenAI generation; without them the
service uses the deterministic fallback path):

| Secret | Description |
|--------|-------------|
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` | Chat model deployment name |
| `AZURE_OPENAI_API_VERSION` | API version (e.g. `2024-02-01`) |

### Getting the service URL

After deployment the URL is printed by the deploy script.  You can also
retrieve it any time:

```bash
gcloud run services describe mock-data-generator-api \
  --region us-central1 \
  --format="value(status.url)"
```

### End-to-end check

Run the stdlib-only proof script against the live URL to verify all three
layers (health, agent card, A2A generation):

```bash
python3 scripts/e2e_a2a_check.py --url https://<service-url>
# or
E2E_URL=https://<service-url> python3 scripts/e2e_a2a_check.py
```

The script:
- Checks `/health` and asserts `a2a_backend` is present in the response.
- Checks `/.well-known/agent.json` and asserts `url == "/a2a/mock-data-generator"`.
- Posts a tiny base64-encoded CSV to `/a2a/mock-data-generator` via the
  canonical DCRI JSON envelope and asserts a non-error result.
- Prints a ready-to-paste `curl` example.
- Exits `0` on full pass, `1` on any failure.

**Fallback-path note:** Without Azure OpenAI credentials the service uses the
built-in deterministic fallback generator (lower statistical fidelity but
fully functional).  The e2e script treats a non-empty `"data"` or
`"generation_info"` key as success even when `method == "fallback"`, so the
check passes in either mode.

### A2A wire contract note

The `/a2a/{agent_id}` endpoint speaks the **canonical DCRI JSON envelope**
produced by `a2a_runtime.encode_message` / `decode_message` (the same shape
used by this repo's shim and by the real `dcri-a2a-core` package).  When
`dcri-a2a-core` is installed, `a2a_runtime/__init__.py` switches
transparently to the real package.  Verify inbound framing against the actual
`a2a-sdk` `message/send` JSON-RPC spec when adopting `dcri-a2a-core` in
production, as the shim uses a simplified envelope that may differ from the
full JSON-RPC framing expected by the real SDK.
