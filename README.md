# Wake.ai

**the cleanup crew for your code**

Dead-code cleaner for the [Vultr: Agent Rush](https://lablab.ai/ai-hackathons/vultr-hackathon) hackathon — challenge track **Blast Radius Zero**.

Clones a Python repo into a hardened Docker/gVisor sandbox, scans with Vulture + ruff, triages findings, **proves** each removal with pytest (batch → split → restore), records removals in `wake.md` / `wake.lock.json`, then destroys the sandbox.

> **lablab rule:** core AI (planner / triage / narrator / LLM gateway) is **stubbed** until build week **3–8 Nov 2026**. Deterministic fallbacks are in use now.

## Quick start (host-local, no Docker required)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'  # or: pip install fastapi uvicorn sse-starlette pydantic pydantic-settings httpx python-multipart docker pytest vulture ruff
cp .env.example .env
uvicorn control_plane.api.app:app --reload --port 8080
# open http://127.0.0.1:8080
```

Run unit tests:

```bash
pytest -q
```

Resurrect from a lockfile:

```bash
python scripts/wake_resurrect.py rm_0001 --lock path/to/wake.lock.json --repo path/to/repo
```

## Layout

```
control_plane/     # control plane (plan name: control-plane/)
  api/             # FastAPI + SQLite + SSE
  agent/           # scavenge, prove, stubs for planner/triage/narrator
  patcher/         # diffs, wake.md / wake.lock.json
  sandbox_client.py
  llm_gateway.py   # interface + TODO only
sandbox-image/     # hardened worker image
web/               # SPA landing + timeline + graveyard
demo-repos/        # tidy-todo, flask-blog, poisoned-carcass
infra/             # cloud-init, Caddy, firewall, sweeper, compose
docs/              # architecture, threat model, specs
```

## Containment (target)

gVisor `runsc` (fallback `runc`), `cap-drop ALL`, no-new-privileges, non-root (uid 65532), read-only rootfs, tmpfs `/workspace`+`/tmp`, 512m / 1 CPU / pids 128, network off after clone, block `169.254.169.254`, 60s/command, 8 min/job, 15-min sweeper.

**Never** run `demo-repos/poisoned-carcass` tests on a normal host (`WAKE_SANDBOX=1` required).

## License

MIT
