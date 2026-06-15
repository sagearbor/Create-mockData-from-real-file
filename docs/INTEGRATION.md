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
