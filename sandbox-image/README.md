# wake-sandbox image

```bash
docker build -t wake-sandbox:local -f sandbox-image/Dockerfile .
```

Requires Docker. Prefer gVisor `runsc` at runtime (configured in `sandbox_client.py`).
