#!/bin/bash

# BYOD Synthetic Data Generator - Run Script

echo "===========================================" 
echo "BYOD Synthetic Data Generator"
echo "==========================================="
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version

# Kill any existing processes on port 8201
echo ""
echo "Checking for processes on port 8201..."
if lsof -Pi :8201 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "Found process on port 8201, killing it..."
    kill -9 $(lsof -Pi :8201 -sTCP:LISTEN -t) 2>/dev/null
    sleep 2
fi

# Create necessary directories
echo ""
echo "Creating necessary directories..."
mkdir -p data/local_storage data/cache data/samples logs

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Install/upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip --quiet

# Install requirements
echo ""
echo "Installing requirements (this may take a moment)..."
pip install -r requirements.txt --quiet

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo ""
    echo "Creating .env file from example..."
    cp .env.example .env
    echo "Note: Edit .env file to add Azure OpenAI credentials for full functionality"
fi

# Display startup information
echo ""
echo "==========================================="
echo "Starting BYOD Synthetic Data Generator"
echo "==========================================="
echo ""
echo "Web Interface: http://localhost:8201"
echo "API Docs:      http://localhost:8201/docs"
echo "Health Check:  http://localhost:8201/health"
echo ""
echo "Press Ctrl+C to stop the server"
echo "==========================================="
echo ""

# Run the application with visible output
python3 main.py