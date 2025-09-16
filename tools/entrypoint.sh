#!/bin/bash
# Entrypoint script that sets up iptables rules to restrict network access
# Only allows connections to Anthropic's API endpoints

# Enable strict error handling
set -e

# Function to setup firewall rules
setup_firewall() {
    # Allow loopback
    iptables -A OUTPUT -o lo -j ACCEPT
    iptables -A INPUT -i lo -j ACCEPT
    
    # Allow DNS resolution (needed to resolve api.anthropic.com)
    iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
    iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT
    iptables -A INPUT -p udp --sport 53 -j ACCEPT
    iptables -A INPUT -p tcp --sport 53 -j ACCEPT
    
    # Allow HTTPS connections to Anthropic API only
    # api.anthropic.com and claude.ai domains
    iptables -A OUTPUT -p tcp --dport 443 -d api.anthropic.com -j ACCEPT
    iptables -A OUTPUT -p tcp --dport 443 -d claude.ai -j ACCEPT
    iptables -A INPUT -p tcp --sport 443 -s api.anthropic.com -j ACCEPT
    iptables -A INPUT -p tcp --sport 443 -s claude.ai -j ACCEPT
    
    # Allow established connections
    iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
    iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
    
    # Drop everything else
    iptables -P OUTPUT DROP
    iptables -P INPUT DROP
    iptables -P FORWARD DROP
    
    echo "✅ Network restrictions applied: Only Anthropic API access allowed"
}

# Check if we should apply network restrictions
if [ "$APPLY_NETWORK_RESTRICTIONS" = "true" ]; then
    setup_firewall
    
    # Drop privileges after setting up firewall
    # Always run as the non-root appuser (UID 1001) for security

    # Set permissive umask so files created by container are world-writable
    # This allows both container user (UID 1001) and host user to modify files
    echo "Setting permissive file creation mode..."
    umask 000

    # Execute command as the minimal-permission appuser with umask 000
    exec su -s /bin/bash appuser -c "umask 000 && $(printf '%q ' "$@")"
else
    # No network restrictions, just execute normally
    exec "$@"
fi