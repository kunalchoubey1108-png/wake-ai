# Sandbox install notes (this box)

## Outcome
- **Docker Engine** 29.9.2 installed; `dockerd` started manually (no systemd `--now`).
- **gVisor runsc** `release-20261019.0` installed from GitHub `gvisor-x86_64.tar.zstd`.
- Sidecar binaries under `/usr/local/bin/gvisor-bin/`; `runsc` registered in `/etc/docker/daemon.json`.
- **Runtime used: `runsc`** (gVisor). runc fallback was **not** required — ptrace/KVM path works here after sidecar install.
- Image: `wake-sandbox:local` from pinned `python:3.12.7-slim-bookworm@sha256:60d9996b6a8a3689d36db740b49f4327be3be09a21122bd02fb8895abb38b50d`.

## Unverified here
- VM-level metadata firewall (`iptables` DROP to `169.254.169.254`) is a production Vultr sandbox-VM control and **cannot be fully verified** on this shared agent box. Container `network_mode=none` was verified (metadata + example.com fetches fail).
