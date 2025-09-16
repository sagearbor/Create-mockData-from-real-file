#!/bin/bash
# Wrapper script to run the claude tool inside a secure, locked-down Docker container.
set -e

IMAGE_NAME="claude-secure-env"
SECCOMP_PROFILE_PATH="./tools/seccomp.json"

# SECCOMP TEMPORARILY DISABLED - Azure VM Compatibility Issue
# ------------------------------------------------------------
# The seccomp security profile is currently commented out due to compatibility
# issues with Azure VM kernels (6.8.0-xxxx-azure). Even with all necessary
# syscalls added, the profile causes "operation not permitted" errors during
# container initialization, specifically:
#   "error closing exec fds: ensure /proc/thread-self/fd is on procfs"
#
# This appears to be related to how Azure VMs handle certain proc filesystem
# operations differently than standard Linux kernels.
#
# TO RE-ENABLE SECCOMP IN THE FUTURE:
# 1. Uncomment the seccomp check below (lines 22-25)
# 2. Uncomment the --security-opt line in docker run (line 35)
# 3. Test thoroughly on the target system
#
# Note: Even without seccomp, the container remains highly secure through:
# - Network isolation (iptables restricts to Anthropic API only)
# - Filesystem isolation (only current directory is accessible)
# - Ephemeral containers (--rm flag)
# - No persistent state between runs

# if [ ! -f "$SECCOMP_PROFILE_PATH" ]; then
#     echo "❌ Security profile not found at $SECCOMP_PROFILE_PATH. Please run the installer again."
#     exit 1
# fi

docker run \
    --rm \
    --interactive --tty \
    --cap-add NET_ADMIN \
    --env APPLY_NETWORK_RESTRICTIONS=true \
    -v "$(pwd)":/app:rw \
    --workdir /app \
    "$IMAGE_NAME" \
    "$@"
    # --security-opt seccomp="$SECCOMP_PROFILE_PATH" \  # DISABLED - See note above

# --------------------------- SECURITY EXPLANATION ---------------------------
# The `docker run` command above constructs a temporary, locked-down "prison"
# for the claude tool to run in. Here is what each flag does:
#
# --rm: Ephemeral. The container is completely destroyed upon exit. This
#   prevents any state, malware, or hidden files from persisting.
#
# --interactive --tty: Allows you to interact with the command-line tool.
#
# --cap-add NET_ADMIN: Allows iptables to configure network filtering rules.
#   The entrypoint script uses this to restrict network access to ONLY
#   Anthropic's API endpoints (api.anthropic.com and claude.ai).
#
# --env APPLY_NETWORK_RESTRICTIONS=true: Triggers the network filtering.
#   Only HTTPS connections to Anthropic's servers are allowed.
#
# --security-opt seccomp=...: CRITICAL. Applies a strict whitelist of
#   allowed kernel-level actions (system calls). This prevents advanced,
#   low-level attacks even if the tool itself were compromised.
#
# -v "$(pwd)":/app: Controlled File Access. Maps ONLY the current project
#   directory into the container. The tool CANNOT see or access any other
#   files or folders on your system (e.g., ~/.ssh, /etc).
# ----------------------------------------------------------------------------
