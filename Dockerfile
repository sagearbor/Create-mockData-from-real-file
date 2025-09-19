# Multi-stage build for BYOD Synthetic Data Generator
# Stage 1: Builder
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies for building Python packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

# Set metadata labels
LABEL maintainer="BYOD Synthetic Data Team"
LABEL description="BYOD Synthetic Data Generation Service - Generate privacy-preserving synthetic data"
LABEL version="1.0"

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Install runtime dependencies only
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code and all necessary files
# This includes: main.py, src/, static/, templates/, .env (if present)
COPY --chown=appuser:appuser . .

# Create necessary directories with appropriate permissions
RUN mkdir -p /app/data /app/cache /app/logs /app/static /app/templates && \
    chown -R appuser:appuser /app

# Verify critical files are present
RUN echo "=== Verifying Docker build contents ===" && \
    ls -la /app/ | head -20 && \
    echo "=== Checking for main.py ===" && \
    test -f /app/main.py && echo "✓ main.py found" || echo "✗ main.py missing" && \
    echo "=== Checking for src directory ===" && \
    test -d /app/src && echo "✓ src/ directory found" || echo "✗ src/ directory missing" && \
    echo "=== Checking for .env file ===" && \
    test -f /app/.env && echo "✓ .env file found (local mode)" || echo "✗ .env not found (use Azure env vars)"

# Switch to non-root user
USER appuser

# Environment variables
# PYTHONUNBUFFERED: Ensures stdout/stderr are unbuffered for real-time logs
# PYTHONDONTWRITEBYTECODE: Prevents Python from writing .pyc files
# PORT: Application port (can be overridden by Azure App Service)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8201

# Default environment variables (can be overridden)
# These will be overridden by .env file if present, or Azure App Service configs
ENV ENVIRONMENT=production \
    LOG_LEVEL=INFO

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Expose port
EXPOSE 8201

# Run the application
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8201"]
