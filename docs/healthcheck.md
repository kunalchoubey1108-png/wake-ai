# Healthcheck & restart

## Endpoint

`GET /api/health` → `{"ok": true, "service": "wake.ai", "ai": "stubbed-until-build-week"}`

Use this for load balancers, Caddy, Vultr health probes, and `infra/restart.sh`.

## Restart

```bash
# Docker Compose (default)
./infra/restart.sh
# or
./infra/restart.sh --compose

# Local uvicorn (dev / agent box without compose)
./infra/restart.sh --local-uvicorn
```

The script:

1. Starts or rebuilds the control plane.
2. Polls `/api/health` for up to 60s (`WAKE_HEALTH_WAIT`).
3. Runs `infra/sweeper.sh` once (destroys Wake job containers older than 15 minutes).

Override the probe URL with `WAKE_HEALTH_URL` (default `http://127.0.0.1:8080/api/health`).

## Compose probe example

```yaml
healthcheck:
  test: ["CMD", "curl", "-fsS", "http://127.0.0.1:8080/api/health"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 20s
```

## Uptime notes

- Control plane holds keys and **never** runs user code; restarting it does not require draining sandboxes first, but in-flight jobs will fail — clients should retry or use replay.
- Sandbox host: keep `dockerd` + `runsc` up; cron the sweeper every 15 minutes (see `infra/cloud-init/`).
- After any restart, confirm `docker ps` shows **0** leftover `wake.ai/job` containers once jobs settle.
