#!/bin/bash

# Docker Context Switcher Script
# Easily switch between Windows Docker Desktop and WSL Linux Docker

show_usage() {
    echo "Docker Context Switcher"
    echo "Usage: ./docker-switch.sh [wsl|windows|status]"
    echo ""
    echo "Commands:"
    echo "  wsl      - Switch to native WSL Linux Docker"
    echo "  windows  - Switch to Windows Docker Desktop"
    echo "  status   - Show current context and available contexts"
    echo ""
}

switch_to_wsl() {
    echo "Switching to WSL Linux Docker..."
    docker context use wsl
    echo "✓ Now using native WSL Linux Docker"
    echo ""
    docker ps
}

switch_to_windows() {
    echo "Switching to Windows Docker Desktop..."
    docker context use desktop-linux
    echo "✓ Now using Windows Docker Desktop"
    echo ""
    echo "Note: Make sure Docker Desktop is running on Windows"
    docker ps 2>/dev/null || echo "⚠ Cannot connect to Docker Desktop. Is it running?"
}

show_status() {
    echo "Current Docker Context:"
    docker context show
    echo ""
    echo "Available Contexts:"
    docker context ls
    echo ""
    echo "Current Docker Info:"
    docker version --format 'Server Version: {{.Server.Version}}'
    docker info --format 'Server: {{.ServerVersion}} | OS: {{.OperatingSystem}}'
}

# Main script logic
case "$1" in
    wsl)
        switch_to_wsl
        ;;
    windows)
        switch_to_windows
        ;;
    status|"")
        show_status
        ;;
    -h|--help|help)
        show_usage
        ;;
    *)
        echo "Invalid option: $1"
        echo ""
        show_usage
        exit 1
        ;;
esac