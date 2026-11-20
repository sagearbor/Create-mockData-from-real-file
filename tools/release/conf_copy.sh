#!/usr/bin/env bash
# Runs conf_copy.py with the Atlassian variables loaded the same way the jc launcher does
# (from the private token file when the shell profile did not supply them). Never prints them.
set -euo pipefail
if [ -z "${ATLASSIAN_API_TOKEN:-}" ] && [ -f "${ATLASSIAN_TOKEN_FILE:-$HOME/.atlassian-token}" ]; then
  set -a; . "${ATLASSIAN_TOKEN_FILE:-$HOME/.atlassian-token}" 2>/dev/null; set +a
fi
exec python3 -B "$(dirname "$0")/conf_copy.py" "$@"
