#!/usr/bin/env bash
# Destroy Wake.ai containers older than 15 minutes
set -euo pipefail
cutoff=$(( $(date +%s) - 900 ))
docker ps -aq --filter "label=wake.ai/job=1" | while read -r id; do
  [[ -z "$id" ]] && continue
  created=$(docker inspect -f '{{ index .Config.Labels "wake.ai/created" }}' "$id" 2>/dev/null || echo 0)
  if [[ "${created:-0}" =~ ^[0-9]+$ ]] && (( created < cutoff )); then
    docker rm -f "$id" || true
  fi
done
