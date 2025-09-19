# Quick Start Commands

## Option 1: Direct Python Run (Simplest)
```bash
# Run this command to start the server immediately
python3 main.py
```

## Option 2: Test Run Script (With Import Checks)
```bash
# This will test all imports first, then start the server
python3 test_run.py
```

## Option 3: Full Setup Script (Recommended for First Time)
```bash
# This will set up virtual environment and install dependencies
./run_app.sh
```

## Manual Commands (Step by Step)

If you want to see each step:

```bash
# 1. Check if port 8201 is free
lsof -i :8201

# 2. If port is in use, kill the process
kill -9 $(lsof -t -i:8201)

# 3. Create directories
mkdir -p data/local_storage data/cache data/samples logs

# 4. Install dependencies (if not already installed)
pip3 install fastapi uvicorn pandas numpy python-dotenv

# 5. Run the application
python3 main.py
```

## Testing the Application

Once running, you can test with:

```bash
# In a new terminal:

# 1. Check health
curl http://localhost:8201/health

# 2. Open in browser
open http://localhost:8201

# 3. Test with sample data
curl -X POST "http://localhost:8201/generate" \
  -F "file=@data/samples/sales_data.csv" \
  -F "match_threshold=0.8" \
  -F "output_format=csv" \
  --output test_synthetic.csv
```

## Troubleshooting

If you get import errors:
```bash
# Install missing packages
pip3 install pydantic pydantic-settings python-multipart aiofiles

# Or install all requirements
pip3 install -r requirements.txt
```

If port 8201 is busy:
```bash
# Use a different port
APP_PORT=8202 python3 main.py

# Or kill existing process
pkill -f "python.*main.py"
```

## Stop the Server
Press `Ctrl+C` in the terminal where the server is running.