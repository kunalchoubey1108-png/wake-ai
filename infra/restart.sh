#!/usr/bin/env bash
# Restart Wake.ai control plane with a health probe.
# Usage: ./infra/restart.sh [--local-uvicorn | --compose]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
MODE="${1:---compose}"
HEALTH_URL="${WAKE_HEALTH_URL:-http://127.0.0.1:8080/api/health}"
MAX_WAIT="${WAKE_HEALTH_WAIT:-60}"

health_ok() {
  curl -fsS "$HEALTH_URL" | grep -q '"ok": *true'
}

wait_healthy() {
  local i=0
  echo "Waiting for health at $HEALTH_URL (max ${MAX_WAIT}s)…"
  while (( i < MAX_WAIT )); do
    if health_ok; then
      echo "Healthy: $(curl -fsS "$HEALTH_URL")"
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  echo "ERROR: health check failed after ${MAX_WAIT}s" >&2
  return 1
}

case "$MODE" in
  --compose)
    if command -v docker >/dev/null 2>&1; then
      docker compose -f infra/docker-compose.yml up -d --build
    else
      echo "docker not found; falling back to --local-uvicorn" >&2
      exec "$0" --local-uvicorn
    fi
    ;;
  --local-uvicorn)
    mkdir -p data
    if [[ -f /tmp/wake-uvicorn.pid ]] && kill -0 "$(cat /tmp/wake-uvicorn.pid)" 2>/dev/null; then
      kill "$(cat /tmp/wake-uvicorn.pid)" || true
      sleep 1
    fi
    # shellcheck disable=SC1091
    if [[ -f .venv/bin/activate ]]; then source .venv/bin/activate; fi
    nohup uvicorn control_plane.api.app:app --host 127.0.0.1 --port 8080 \
      >/tmp/wake-uvicorn.log 2>&1 &
    echo $! >/tmp/wake-uvicorn.pid
    echo "Started uvicorn pid $(cat /tmp/wake-uvicorn.pid)"
    ;;
  *)
    echo "Usage: $0 [--compose|--local-uvicorn]" >&2
    exit 2
    ;;
esac

wait_healthy
# Optional sweeper pass after restart
if [[ -x infra/sweeper.sh ]]; then
  infra/sweeper.sh || true
fi
echo "Restart complete."
