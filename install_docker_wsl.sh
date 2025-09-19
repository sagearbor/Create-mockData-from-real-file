#!/bin/bash

# Docker installation script for WSL Ubuntu
echo "Starting Docker installation for WSL Ubuntu..."

# Update package index
echo "Updating package index..."
sudo apt update

# Install prerequisites
echo "Installing prerequisites..."
sudo apt install -y apt-transport-https ca-certificates curl software-properties-common lsb-release

# Add Docker's official GPG key
echo "Adding Docker GPG key..."
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Add Docker repository
echo "Adding Docker repository..."
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Update package index again
echo "Updating package index with Docker repository..."
sudo apt update

# Install Docker Engine
echo "Installing Docker Engine..."
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add current user to docker group
echo "Adding user to docker group..."
sudo usermod -aG docker $USER

# Start Docker service
echo "Starting Docker service..."
sudo service docker start

# Enable Docker service to start on boot
echo "Enabling Docker service..."
sudo systemctl enable docker 2>/dev/null || true

echo ""
echo "Docker installation complete!"
echo ""
echo "IMPORTANT: You need to log out and back in for group changes to take effect."
echo "Alternatively, run: newgrp docker"
echo ""
echo "To verify installation, run:"
echo "  docker --version"
echo "  docker compose version"