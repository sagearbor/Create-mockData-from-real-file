# Use a minimal, secure base image with Python pre-installed.
FROM python:3.11-slim-bullseye

# Set metadata labels
LABEL maintainer="Your Org <security@your-org.com>"
LABEL description="A secure, isolated environment for running the Claude AI CLI."

# Create a non-root user and group to run the application.
# This is a critical security measure to avoid running as root.
RUN groupadd --gid 1001 appuser && \
    useradd --uid 1001 --gid 1001 -m appuser

# Install Node.js 20 LTS and required packages for Claude CLI
RUN apt-get update && \
    apt-get install -y curl iptables ca-certificates gnupg procps && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g @anthropic-ai/claude-code && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy the entrypoint script
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Set the working directory for the container.
# This is where the project files will be mounted.
WORKDIR /app

# Note: We cannot use USER here because iptables requires root
# The wrapper script will handle dropping privileges after setting up firewall

# Set the entrypoint to our script which sets up network restrictions
ENTRYPOINT ["/usr/local/bin/entrypoint.sh", "claude"]
