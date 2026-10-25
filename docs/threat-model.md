# Wake.ai threat model

## Assets
- Vultr / LLM API keys (control plane only)
- Customer repository contents (ephemeral in sandbox)
- Host kernel / sibling workloads on sandbox VM

## Trust boundaries
1. **Browser → control plane** (TLS via Caddy)
2. **Control plane → sandbox host** (private net / mTLS; no keys on sandbox)
3. **Sandbox container → outside** (network none after clone; firewall drops 169.254.169.254 + RFC1918)

## Adversary capabilities (Poisoned Carcass)
- Destructive FS writes (`rm -rf /`)
- Fork bomb / infinite loops
- Env exfiltration
- Cloud metadata & egress probes

## Mitigations
| Threat | Control |
|--------|---------|
| Escape to host | gVisor `runsc`, cap-drop ALL, no-new-privileges, non-root, read-only rootfs |
| Secret theft | Empty container env; keys never mounted; network none post-clone |
| Metadata SSRF | Egress DROP 169.254.169.254 |
| Resource exhaustion | 512m, 1 CPU, pids 128, 60s cmd, 8 min job |
| Orphan containers | `--rm` / explicit destroy + 15-min sweeper |
| Path traversal on collect | Workspace-relative path checks + size caps |
| Supply-chain image swap | Pin image digest at deploy time |

## Out of scope (scaffolding)
- Full formal verification of gVisor
- Multi-tenant hard isolation beyond one job / one container
