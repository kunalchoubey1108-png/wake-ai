"""
Sandbox client: create hardened containers, run commands, collect capped output, destroy.

Local Docker over a unix socket by default. Optional remote mTLS endpoint for the
sandbox host VM (control plane never runs user code).
"""
from __future__ import annotations

import io
import logging
import shutil
import tarfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from control_plane.config import settings
from control_plane.models import ContainmentEvidence

log = logging.getLogger(__name__)

WORKSPACE = "/workspace"


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
    return not (p.is_absolute() or ".." in p.parts)


def _cap_text(data: bytes | str, max_bytes: int) -> str:
    raw = data.encode("utf-8", errors="replace") if isinstance(data, str) else data
    if len(raw) > max_bytes:
        raw = raw[:max_bytes] + b"\n...[truncated]...\n"
    return raw.decode("utf-8", errors="replace")


def _parse_mem(s: str) -> int:
    s = s.strip().lower()
    if s.endswith("m"):
        return int(float(s[:-1]) * 1024 * 1024)
    if s.endswith("g"):
        return int(float(s[:-1]) * 1024 * 1024 * 1024)
    return int(s)


def _shell_quote(a: str) -> str:
    return "'" + a.replace("'", "'\"'\"'") + "'"


class SandboxClient:
    """Create / run / destroy disposable sandboxes."""

    def __init__(self) -> None:
        self._remote = bool(settings.wake_sandbox_remote_url)

    def available(self) -> bool:
        if self._remote:
            return True
        if not Path("/var/run/docker.sock").exists() and not shutil.which("docker"):
            return False
        try:
            _docker_client().ping()
            return True
        except Exception:
            return False

    def create(
        self,
        *,
        network: str | None = None,
        extra_env: dict[str, str] | None = None,
        prefer_runtime: str | None = None,
    ) -> SandboxSession:
        if self._remote:
            raise SandboxError(
                "Remote mTLS sandbox not configured; set WAKE_SANDBOX_REMOTE_URL + certs at deploy."
            )
        client = _docker_client()
        runtime = prefer_runtime or settings.wake_sandbox_runtime
        network = network if network is not None else settings.wake_sandbox_network_clone
        mem_bytes = _parse_mem(settings.wake_sandbox_memory)

        # Secret hygiene: never pass host env. Blank known image ENV keys so they do not
        # look like secrets in dumps; keep a minimal allowlist for the interpreter.
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": "/home/wake",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "LANG": "C.UTF-8",
            # Override image ENV (Docker merges; blanking removes useful leak surface)
            "GPG_KEY": "",
            "PYTHON_SHA256": "",
            "PYTHON_VERSION": "",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        }
        if extra_env:
            env.update(extra_env)

        common_kwargs: dict[str, Any] = dict(
            image=settings.wake_sandbox_image,
            command=["sleep", "infinity"],
            detach=True,
            user="65532:65532",
            network_mode=network if network != "none" else "none",
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            read_only=True,
            tmpfs={
                WORKSPACE: "rw,exec,size=1024m,uid=65532,gid=65532",
                "/tmp": "rw,exec,size=256m,uid=65532,gid=65532",
                "/home/wake": "rw,size=64m,uid=65532,gid=65532",
            },
            mem_limit=mem_bytes,
            memswap_limit=mem_bytes,
            nano_cpus=int(settings.wake_sandbox_cpus * 1e9),
            pids_limit=settings.wake_sandbox_pids,
            environment=env,
            labels={"wake.ai/job": "1", "wake.ai/created": str(int(time.time()))},
            auto_remove=False,
            working_dir=WORKSPACE,
        )

        container = None
        used_runtime = runtime
        last_err: Exception | None = None
        tried = []
        for rt in (runtime, settings.wake_sandbox_runtime_fallback):
            if rt in tried:
                continue
            tried.append(rt)
            try:
                container = client.containers.run(runtime=rt, **common_kwargs)
                used_runtime = rt
                break
            except Exception as e:
                last_err = e
                log.warning("runtime %s failed: %s", rt, e)
        if container is None:
            raise SandboxError(f"cannot start sandbox: {last_err}")

        cid = container.id
        evidence = ContainmentEvidence(
            runtime=used_runtime,
            container_id=cid[:12],
            env_dump={},
            network_mode_final=network,
            notes=[
                "cap-drop ALL",
                "no-new-privileges",
                "read-only rootfs",
                f"tmpfs {WORKSPACE}+/tmp",
                f"mem={settings.wake_sandbox_memory} cpus={settings.wake_sandbox_cpus} pids={settings.wake_sandbox_pids}",
            ],
        )
        if used_runtime != runtime:
            evidence.notes.append(f"fallback from {runtime} to {used_runtime}: {last_err}")

        try:
            code, out = container.exec_run(["id", "-u"], user="65532:65532")
            if code == 0:
                evidence.uid = int(out.decode().strip())
        except Exception:
            pass
        try:
            code, out = container.exec_run(
                ["python", "-c", "import os,json; print(json.dumps(dict(os.environ)))"],
                user="65532:65532",
            )
            if code == 0:
                import json as _json

                evidence.env_dump = _json.loads(out.decode())
        except Exception:
            pass

        return SandboxSession(container_id=cid, runtime=used_runtime, evidence=evidence, _client=client)



    def put_tree(self, session: SandboxSession, host_dir: Path, dest_rel: str = "repo") -> None:
        """Copy host tree into container workspace via docker exec -i tar (RO-rootfs safe)."""
        if not _path_allowed_in_workspace(dest_rel):
            raise SandboxError("invalid dest path")
        import subprocess as _sp
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for path in sorted(host_dir.rglob("*")):
                if not path.is_file():
                    continue
                if any(x in path.parts for x in (".venv", "__pycache__", ".git", ".pytest_cache", ".ruff_cache")):
                    continue
                if path.suffix == ".pyc" or path.name.endswith(".egg-info"):
                    continue
                rel = path.relative_to(host_dir)
                info = tar.gettarinfo(str(path), arcname=str(Path(dest_rel) / rel))
                info.uid = 65532
                info.gid = 65532
                with open(path, "rb") as f:
                    tar.addfile(info, f)
        self.run(session, ["sh", "-c", f"rm -rf {WORKSPACE}/{dest_rel} && mkdir -p {WORKSPACE}/{dest_rel}"], timeout_sec=15)
        proc = _sp.run(
            [
                "docker", "exec", "-i", "-u", "65532:65532",
                "-w", WORKSPACE, session.container_id,
                "tar", "-x", "-C", WORKSPACE,
            ],
            input=buf.getvalue(),
            capture_output=True,
            timeout=120,
        )
        if proc.returncode != 0:
            raise SandboxError(f"tar extract failed: {proc.stderr.decode()[:500]}")


    def put_bytes(self, session: SandboxSession, dest_rel: str, data: bytes) -> None:
        if not _path_allowed_in_workspace(dest_rel):
            raise SandboxError("invalid dest path")
        import subprocess as _sp
        parent = str(Path(dest_rel).parent)
        if parent not in (".", ""):
            self.run(session, ["mkdir", "-p", f"{WORKSPACE}/{parent}"], timeout_sec=10)
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(name=dest_rel)
            info.size = len(data)
            info.mode = 0o644
            info.uid = 65532
            info.gid = 65532
            tar.addfile(info, io.BytesIO(data))
        proc = _sp.run(
            [
                "docker", "exec", "-i", "-u", "65532:65532",
                "-w", WORKSPACE, session.container_id,
                "tar", "-x", "-C", WORKSPACE,
            ],
            input=buf.getvalue(),
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0:
            raise SandboxError(f"put_bytes failed: {proc.stderr.decode()[:500]}")

    def run(
        self,
        session: SandboxSession,
        argv: list[str],
        *,
        workdir: str = WORKSPACE,
        timeout_sec: int | None = None,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        timeout_sec = timeout_sec or settings.wake_cmd_timeout_sec
        if session.age_sec > settings.wake_job_timeout_sec:
            raise SandboxError("job wall clock exceeded")
        client = session._client
        container = client.containers.get(session.container_id)
        t0 = time.time()
        inner = " ".join(_shell_quote(a) for a in argv)
        # env prefix
        if env:
            export = " ".join(f"{k}={_shell_quote(v)}" for k, v in env.items())
            wrapped = f"export {export}; timeout -s KILL {int(timeout_sec)}s {inner}"
        else:
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
            # GNU timeout: 124; KILL often 137
            timed_out = exit_code in (124, 137)
            killed = exit_code == 137
            if killed or timed_out:
                session.evidence.kills.append(f"timeout/kill on: {argv[:3]} exit={exit_code}")
            return CommandResult(
                exit_code=int(exit_code if exit_code is not None else 1),
                stdout=_cap_text(stdout_b, settings.wake_output_max_bytes),
                stderr=_cap_text(stderr_b, settings.wake_output_max_bytes),
                duration_ms=(time.time() - t0) * 1000,
                timed_out=timed_out,
                killed=killed,
            )
        except Exception as e:
            return CommandResult(1, "", str(e), (time.time() - t0) * 1000)

    def disable_network(self, session: SandboxSession) -> None:
        client = session._client
        container = client.containers.get(session.container_id)
        try:
            nets = list((container.attrs.get("NetworkSettings") or {}).get("Networks") or {})
            # refresh attrs
            container.reload()
            nets = list((container.attrs.get("NetworkSettings") or {}).get("Networks") or {})
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
            container = session._client.containers.get(session.container_id)
            stats = container.stats(stream=False)
            usage = (stats.get("memory_stats") or {}).get("usage")
            if usage is not None:
                session.evidence.peak_memory_bytes = max(session.evidence.peak_memory_bytes or 0, int(usage))
        except Exception:
            pass

    def destroy(self, session: SandboxSession) -> ContainmentEvidence:
        t0 = time.time()
        try:
            self.collect_stats(session)
            container = session._client.containers.get(session.container_id)
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

    def get_tree(self, session: SandboxSession, src_rel: str, host_dir: Path) -> None:
        """Copy a workspace subtree out of the container (path-checked)."""
        if not _path_allowed_in_workspace(src_rel):
            raise SandboxError("invalid src path")
        container = session._client.containers.get(session.container_id)
        bits, _stat = container.get_archive(f"{WORKSPACE}/{src_rel}")
        host_dir.mkdir(parents=True, exist_ok=True)
        buf = io.BytesIO()
        for chunk in bits:
            buf.write(chunk)
        buf.seek(0)
        with tarfile.open(fileobj=buf, mode="r") as tar:
            # Python 3.12+ filter; safe extract under host_dir
            def _safe(member: tarfile.TarInfo, dest: str):
                target = Path(dest) / member.name
                if ".." in Path(member.name).parts:
                    raise SandboxError("tar path escape")
                return member

            try:
                tar.extractall(host_dir, filter=_safe)  # type: ignore[call-arg]
            except TypeError:
                tar.extractall(host_dir)
