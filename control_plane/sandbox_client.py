"""
Sandbox client: create hardened containers, run commands, collect capped output, destroy.

Local Docker over a unix socket by default. Optional remote mTLS endpoint for the
sandbox host VM (control plane never runs user code).
"""
from __future__ import annotations

import io
import json
import logging
import os
import shutil
import tarfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from control_plane.config import settings
from control_plane.models import ContainmentEvidence

log = logging.getLogger(__name__)

WORKSPACE = "/workspace"
FORBIDDEN_HOST_PREFIXES = ("/etc", "/proc", "/sys", "/var/run", "/root", "/home")


@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool = False
    killed: bool = False


@dataclass
class SandboxSession:
    container_id: str
    runtime: str
    evidence: ContainmentEvidence = field(default_factory=ContainmentEvidence)
    _client: Any = None
    _created_at: float = field(default_factory=time.time)

    @property
    def age_sec(self) -> float:
        return time.time() - self._created_at


class SandboxError(RuntimeError):
    pass


def _docker_client():
    try:
        import docker
    except ImportError as e:
        raise SandboxError("docker SDK not installed") from e
    return docker.DockerClient(base_url=settings.wake_docker_host)


def _path_allowed_in_workspace(rel: str) -> bool:
    p = Path(rel)
    if p.is_absolute() or ".." in p.parts:
        return False
    return True


def _cap_text(data: bytes | str, max_bytes: int) -> str:
    if isinstance(data, str):
        raw = data.encode("utf-8", errors="replace")
    else:
        raw = data
    if len(raw) > max_bytes:
        raw = raw[:max_bytes] + b"\n...[truncated]...\n"
    return raw.decode("utf-8", errors="replace")


class SandboxClient:
    """Create / run / destroy disposable sandboxes."""

    def __init__(self) -> None:
        self._remote = bool(settings.wake_sandbox_remote_url)

    def available(self) -> bool:
        if self._remote:
            return True
        if not shutil.which("docker") and not Path("/var/run/docker.sock").exists():
            return False
        try:
            c = _docker_client()
            c.ping()
            return True
        except Exception:
            return False

    def create(self, *, network: str | None = None) -> SandboxSession:
        if self._remote:
            raise SandboxError(
                "Remote mTLS sandbox not configured for this scaffolding build; "
                "set WAKE_SANDBOX_REMOTE_URL + certs during deploy week."
            )
        client = _docker_client()
        runtime = settings.wake_sandbox_runtime
        network = network or settings.wake_sandbox_network_clone
        mem = settings.wake_sandbox_memory
        # matching swap: memory + memory_swap equal => no extra swap beyond mem
        mem_bytes = _parse_mem(mem)

        common_kwargs: dict[str, Any] = dict(
            image=settings.wake_sandbox_image,
            command=["sleep", "infinity"],
            detach=True,
            user="65532:65532",
            network_mode=network,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            read_only=True,
            tmpfs={
                WORKSPACE: "rw,exec,size=1024m,uid=65532,gid=65532",
                "/tmp": "rw,exec,size=256m,uid=65532,gid=65532",
            },
            mem_limit=mem_bytes,
            memswap_limit=mem_bytes,
            nano_cpus=int(settings.wake_sandbox_cpus * 1e9),
            pids_limit=settings.wake_sandbox_pids,
            environment={},  # empty env — secret hygiene
            labels={"wake.ai/job": "1", "wake.ai/created": str(int(time.time()))},
            auto_remove=False,
            working_dir=WORKSPACE,
        )

        container = None
        used_runtime = runtime
        try:
            container = client.containers.run(runtime=runtime, **common_kwargs)
        except Exception as e:
            log.warning("runtime %s failed (%s); falling back to %s", runtime, e, settings.wake_sandbox_runtime_fallback)
            used_runtime = settings.wake_sandbox_runtime_fallback
            try:
                container = client.containers.run(runtime=used_runtime, **common_kwargs)
            except Exception as e2:
                raise SandboxError(f"cannot start sandbox: {e2}") from e2

        cid = container.id
        evidence = ContainmentEvidence(
            runtime=used_runtime,
            container_id=cid[:12],
            env_dump={},
            network_mode_final=network,
            notes=[f"created with cap-drop ALL, no-new-privileges, read-only rootfs, tmpfs {WORKSPACE}"],
        )
        # probe uid inside
        try:
            code, out = container.exec_run(["id", "-u"], user="65532:65532")
            if code == 0:
                evidence.uid = int(out.decode().strip())
        except Exception:
            pass
        return SandboxSession(container_id=cid, runtime=used_runtime, evidence=evidence, _client=client)

    def put_tree(self, session: SandboxSession, host_dir: Path, dest_rel: str = "repo") -> None:
        if not _path_allowed_in_workspace(dest_rel):
            raise SandboxError("invalid dest path")
        client = session._client
        container = client.containers.get(session.container_id)
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for path in host_dir.rglob("*"):
                if path.is_file():
                    rel = path.relative_to(host_dir)
                    tar.add(path, arcname=str(Path(dest_rel) / rel))
        buf.seek(0)
        container.put_archive(WORKSPACE, buf.getvalue())

    def run(
        self,
        session: SandboxSession,
        argv: list[str],
        *,
        workdir: str = WORKSPACE,
        timeout_sec: int | None = None,
    ) -> CommandResult:
        timeout_sec = timeout_sec or settings.wake_cmd_timeout_sec
        if session.age_sec > settings.wake_job_timeout_sec:
            raise SandboxError("job wall clock exceeded")
        client = session._client
        container = client.containers.get(session.container_id)
        t0 = time.time()
        # docker exec has no native timeout; use shell wrapper
        inner = " ".join(_shell_quote(a) for a in argv)
        wrapped = f"timeout -s KILL {int(timeout_sec)}s {inner}"
        try:
            exit_code, output = container.exec_run(
                ["sh", "-c", wrapped],
                workdir=workdir,
                user="65532:65532",
                demux=True,
            )
            stdout_b, stderr_b = output if isinstance(output, tuple) else (output or b"", b"")
            stdout_b = stdout_b or b""
            stderr_b = stderr_b or b""
            timed_out = exit_code in (124, 137)
            killed = exit_code == 137
            if killed:
                session.evidence.kills.append(f"SIGKILL after timeout on: {argv[0]}")
            return CommandResult(
                exit_code=exit_code if exit_code is not None else 1,
                stdout=_cap_text(stdout_b, settings.wake_output_max_bytes),
                stderr=_cap_text(stderr_b, settings.wake_output_max_bytes),
                duration_ms=(time.time() - t0) * 1000,
                timed_out=timed_out,
                killed=killed,
            )
        except Exception as e:
            return CommandResult(
                exit_code=1,
                stdout="",
                stderr=str(e),
                duration_ms=(time.time() - t0) * 1000,
            )

    def disable_network(self, session: SandboxSession) -> None:
        """Disconnect from all networks (post-clone / post-install)."""
        client = session._client
        container = client.containers.get(session.container_id)
        try:
            nets = list(container.attrs.get("NetworkSettings", {}).get("Networks", {}).keys())
            for n in nets:
                try:
                    client.networks.get(n).disconnect(container, force=True)
                except Exception as e:
                    session.evidence.notes.append(f"network disconnect {n}: {e}")
            session.evidence.network_mode_final = "none"
            session.evidence.notes.append("network disabled after clone/install")
        except Exception as e:
            session.evidence.notes.append(f"disable_network failed: {e}")

    def collect_stats(self, session: SandboxSession) -> None:
        try:
            client = session._client
            container = client.containers.get(session.container_id)
            stats = container.stats(stream=False)
            usage = stats.get("memory_stats", {}).get("usage")
            if usage is not None:
                session.evidence.peak_memory_bytes = max(session.evidence.peak_memory_bytes or 0, int(usage))
        except Exception:
            pass

    def destroy(self, session: SandboxSession) -> ContainmentEvidence:
        t0 = time.time()
        try:
            client = session._client
            container = client.containers.get(session.container_id)
            try:
                self.collect_stats(session)
            except Exception:
                pass
            try:
                container.kill()
            except Exception:
                pass
            try:
                container.remove(force=True)
            except Exception as e:
                session.evidence.notes.append(f"remove: {e}")
        finally:
            session.evidence.teardown_ms = (time.time() - t0) * 1000
        return session.evidence


def _parse_mem(s: str) -> int:
    s = s.strip().lower()
    if s.endswith("m"):
        return int(float(s[:-1]) * 1024 * 1024)
    if s.endswith("g"):
        return int(float(s[:-1]) * 1024 * 1024 * 1024)
    return int(s)


def _shell_quote(a: str) -> str:
    return "'" + a.replace("'", "'\"'\"'") + "'"
