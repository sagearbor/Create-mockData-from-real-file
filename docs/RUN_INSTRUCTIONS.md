# 🚀 Quick Run Instructions

The application runs on **port 8201**.

Generation needs an Azure OpenAI model: set `AZURE_OPENAI_ENDPOINT` in `.env` (see
`.env.example`). Without it the server starts, `/ready` answers 503, and every
generation request fails with an error. Do not upload real study data or patient
identifiers: this release has not been approved for them.

## Start the Server

```bash
# From the project directory:
cd Create-mockData-from-real-file

# With virtual environment activated:
python3 main.py
```

## Access Points

Once running, access the application at:

- **Web Interface**: http://localhost:8201
- **Health Check**: http://localhost:8201/health  
- **API Docs**: http://localhost:8201/docs
- **API Info**: http://localhost:8201/api

## Verify It's Working

In a new terminal:
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

## Test with Sample Data

```bash
# Test with the included sample CSV
curl -X POST "http://localhost:8201/generate" \
  -F "file=@data/samples/sales_data.csv" \
  -F "match_threshold=0.8" \
  -F "output_format=json" | python3 -m json.tool
```

## Alternative Ports

If 8201 is busy, use a different port:
```bash
APP_PORT=8202 python3 main.py
# Or
APP_PORT=8203 python3 main.py
```

## Stop the Server

Press `Ctrl+C` in the terminal where it's running.

## What You'll See in Terminal

When running correctly:
```
INFO:     Started server process [PID]
INFO:     Waiting for application startup.
2025-09-06 13:34:16 - byod_synthetic - INFO - Starting BYOD Synthetic Data Generator
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8201 (Press CTRL+C to quit)
```

Then as you use it:
```
INFO:     127.0.0.1:45370 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:45371 - "GET / HTTP/1.1" 200 OK
INFO:     127.0.0.1:45372 - "POST /generate HTTP/1.1" 200 OK
```

## Troubleshooting

If you see "Address already in use":
```bash
# Check what's using the port
lsof -i :8201

# Kill it if needed
kill -9 $(lsof -t -i:8201)

# Or just use a different port
APP_PORT=8205 python3 main.py
```

## If the AI model is not configured

`curl -i http://localhost:8201/ready` answers 503 and gives the reason. The app does
not generate data without the AI model: each generation request fails with an error.
