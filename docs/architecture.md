# Architecture

```mermaid
flowchart LR
  User[User Browser] --> CP[Control Plane VM]
  CP --> LLM[Vultr Serverless Inference<br/>build-week]
  CP --> SH[Sandbox Host VM]
  SH --> C[Hardened Container<br/>gVisor runsc]
  C -->|clone then net none| Repo[User Repo tmpfs]
  C --> Scan[vulture + ruff]
  CP --> Prove[Prove loop / patcher]
  Prove --> Grave[wake.md + wake.lock.json]
```

## Split of trust

| VM | Holds | Runs user code |
|----|-------|----------------|
| Control plane | API keys, SQLite jobs, web UI | **Never** |
| Sandbox host | Docker/gVisor only | **Yes** |

## Job lifecycle
1. Accept GitHub URL / zip / demo id  
2. Create sandbox (network on) → clone/install  
3. Disable network  
4. Scavenge → triage (stub: confidence) → prove  
5. Write graveyard → destroy container → sweeper safety net  
