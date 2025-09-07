#!/bin/bash

# BYOD Synthetic Data Generator - Start Script with Port Selection

echo "==========================================="
echo "BYOD Synthetic Data Generator"
echo "==========================================="

# Default port
PORT=${1:-8201}

# Check if port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 1  # Port is in use
    else
        return 0  # Port is free
    fi
}

# Find available port
find_available_port() {
    local start_port=$1
    local port=$start_port
    
    while ! check_port $port; do
        echo "Port $port is in use, trying next port..."
        port=$((port + 1))
        if [ $port -gt $((start_port + 10)) ]; then
            echo "Could not find available port between $start_port and $port"
            return 1
        fi
    done
    
    echo $port
}

# Kill existing processes
echo "Cleaning up any existing processes..."
pkill -f "python.*main.py" 2>/dev/null
pkill -f "uvicorn.*main:app" 2>/dev/null
sleep 1

# Check requested port
if ! check_port $PORT; then
    echo "Port $PORT is in use."
    AVAILABLE_PORT=$(find_available_port $PORT)
    if [ $? -eq 0 ]; then
        echo "Using port $AVAILABLE_PORT instead."
        PORT=$AVAILABLE_PORT
    else
        echo "Please manually specify a different port: ./start_server.sh <port>"
        exit 1
    fi
else
    echo "Using port $PORT"
fi

# Create necessary directories
mkdir -p data/local_storage data/cache data/samples logs

# Update .env with port if needed
if [ -f .env ]; then
    # Backup original
    cp .env .env.backup
    # Update port
    if grep -q "APP_PORT=" .env; then
        sed -i "s/APP_PORT=.*/APP_PORT=$PORT/" .env
    else
        echo "APP_PORT=$PORT" >> .env
    fi
fi

echo ""
echo "==========================================="
echo "Starting server on port $PORT"
echo "==========================================="
echo ""
echo "Web Interface: http://localhost:$PORT"
echo "API Docs:      http://localhost:$PORT/docs"
echo "Health Check:  http://localhost:$PORT/health"
echo ""
echo "Press Ctrl+C to stop the server"
echo "==========================================="
echo ""

# Run with explicit port
APP_PORT=$PORT python3 main.py