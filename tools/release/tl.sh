#!/usr/bin/env bash
# Append one start/stop event to the release timeline (used for the Gantt in the wrap-up).
# Usage: tools/release/tl.sh start|stop <slug> "<what>"
printf '{"ts":"%s","event":"%s","slug":"%s","what":"%s"}\n' "$(date +%Y-%m-%dT%H:%M:%S%z)" "$1" "$2" "$3" >> docs/release-1.0/timeline.jsonl
