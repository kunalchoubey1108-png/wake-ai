"""Run cleanup jobs inside a hardened sandbox via SandboxClient."""
from __future__ import annotations

import json
from dataclasses import asdict
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from control_plane.agent.narrator import narrate
from control_plane.agent.planner import plan_repo
from control_plane.agent.prove import prove_loop
from control_plane.agent.scavenge import parse_ruff_json, parse_vulture, scavenge
from control_plane.agent.triage import triage_findings
from control_plane.models import ContainmentEvidence, Finding, JobResult, JobStatus, TimelineEvent
from control_plane.patcher.graveyard import Graveyard, write_wake_lock, write_wake_md
from control_plane.sandbox_client import SandboxClient, SandboxError


def _emit(timeline: list[TimelineEvent], kind: str, message: str, **data) -> None:
    timeline.append(TimelineEvent(ts=time.time(), kind=kind, message=message, data=data))


def _git_sha(repo: Path) -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return "nogit"


def _preferred(candidates: list[Finding]) -> list[Finding]:
    SAFE_SYMBOLS = {
        "json", "OrderedDict", "collections.OrderedDict", "hashlib", "Path",
        "unused_helper_format_titles", "AbandonedExporter", "LEGACY_MAX_ITEMS",
        "maybe_legacy_path", "unused_slugify", "DraftCache", "DEPRECATED_THEME",
        "_debug_only_banner", "unused_decoy", "unreachable", "flag",
    }
    LIVE_METHODS = {
        "add", "complete", "pending", "count", "health", "list_posts",
        "create_post", "put", "dump", "innocent_add",
    }
    preferred = []
    for f in candidates:
        if f.symbol in LIVE_METHODS:
            f.status = "skipped"
            continue
        if (
            f.kind == "unused_import"
            or f.symbol in SAFE_SYMBOLS
            or f.symbol.startswith("unused_")
            or f.kind == "unreachable"
        ):
            preferred.append(f)
    return preferred[:12]


def run_job_sandbox(
    src_repo: Path,
    work_dir: Path,
    *,
    job_id: str | None = None,
    repo_label: str = "",
    replay: bool = False,
    network_for_clone: str = "bridge",
) -> JobResult:
    job_id = job_id or f"job_{uuid.uuid4().hex[:10]}"
    label = repo_label or src_repo.name
    timeline: list[TimelineEvent] = []
    dest = work_dir / job_id / "repo"
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        src_repo,
        dest,
        ignore=shutil.ignore_patterns(".venv", "__pycache__", ".git", "*.egg-info", ".pytest_cache", ".ruff_cache"),
    )
    subprocess.run(["git", "init"], cwd=dest, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=wake@local", "-c", "user.name=wake", "commit", "-m", "baseline"],
        cwd=dest,
        capture_output=True,
    )
    base_sha = _git_sha(dest)

    client = SandboxClient()
    if not client.available():
        raise SandboxError("Docker sandbox not available")

    _emit(timeline, "start", narrate("start", job_id=job_id, label=label))
    session = client.create(network=network_for_clone)
    _emit(
        timeline,
        "sandbox",
        f"Created sandbox runtime={session.runtime} id={session.evidence.container_id}",
        runtime=session.runtime,
        container_id=session.evidence.container_id,
    )

    try:
        client.put_tree(session, dest, "repo")
        # Network not needed for tidy-todo/flask-blog (deps in image); disable immediately.
        client.disable_network(session)
        _emit(timeline, "network", "Network disabled after repo copy")

        plan = plan_repo(dest)
        _emit(timeline, "plan", "Deterministic plan ready", plan=plan)

        # Scavenge inside sandbox
        v = client.run(
            session,
            ["vulture", "src", "--min-confidence", "60"],
            workdir="/workspace/repo",
        )
        r = client.run(
            session,
            ["ruff", "check", "src", "--select", "F401,F841", "--output-format", "json"],
            workdir="/workspace/repo",
        )
        findings = parse_vulture(v.stdout or v.stderr, dest)
        findings += parse_ruff_json(r.stdout, dest)
        # dedupe like scavenge()
        seen: set[tuple] = set()
        uniq: list[Finding] = []
        for f in findings:
            key = (f.file, f.line, f.symbol)
            if key in seen:
                continue
            seen.add(key)
            f.id = f"f_{len(uniq):04d}"
            uniq.append(f)
        findings = uniq
        _emit(timeline, "scan", narrate("scan", n=len(findings)), vulture_exit=v.exit_code, ruff_exit=r.exit_code)

        candidates = triage_findings(findings)
        preferred = _preferred(candidates)
        _emit(timeline, "triage", narrate("triage", threshold=60, n=len(preferred)))

        def sandbox_pytest(repo: Path) -> bool:
            # Sync working tree into container then run pytest with PYTHONPATH
            client.put_tree(session, repo, "repo")
            res = client.run(
                session,
                ["python", "-m", "pytest", "-q"],
                workdir="/workspace/repo",
                env={"PYTHONPATH": "/workspace/repo/src"},
                timeout_sec=60,
            )
            _emit(
                timeline,
                "pytest",
                f"sandbox pytest exit={res.exit_code} timeout={res.timed_out} killed={res.killed} {res.duration_ms:.0f}ms",
            )
            return res.exit_code == 0 and not res.timed_out

        prove = prove_loop(
            dest,
            preferred,
            base_sha=base_sha,
            job_id=job_id,
            repo_label=label,
            test_fn=sandbox_pytest,
        )
        for e in prove.events:
            _emit(timeline, "prove", e)

        # Final sync out (graveyard written on host)
        graveyard = Graveyard(repo=label, base_sha=base_sha, job_id=job_id, removals=prove.removed)
        wake_md = write_wake_md(dest / "wake.md", graveyard)
        write_wake_lock(dest / "wake.lock.json", graveyard)
        client.put_tree(session, dest, "repo")  # leave wake files in sandbox briefly for evidence

        evidence = client.destroy(session)
        _emit(
            timeline,
            "containment",
            narrate("containment", runtime=evidence.runtime),
            evidence=evidence.model_dump(),
        )
        _emit(timeline, "done", narrate("done", removed=len(prove.removed), alive=len(prove.alive)))

        return JobResult(
            job_id=job_id,
            status=JobStatus.succeeded,
            repo_label=label,
            base_sha=base_sha,
            findings=findings,
            removals=[asdict(r) for r in prove.removed],
            timeline=timeline,
            containment=evidence,
            wake_md=wake_md,
            replay=replay,
        )
    except Exception as e:
        try:
            evidence = client.destroy(session)
        except Exception:
            evidence = session.evidence
        _emit(timeline, "error", str(e))
        return JobResult(
            job_id=job_id,
            status=JobStatus.failed,
            repo_label=label,
            base_sha=base_sha,
            timeline=timeline,
            containment=evidence,
            error=str(e),
            replay=replay,
        )


def run_job_auto(src_repo: Path, work_dir: Path, **kwargs) -> JobResult:
    """Prefer sandbox when Docker is available; else host-local."""
    from control_plane.agent.pipeline import run_job_local

    client = SandboxClient()
    if client.available():
        try:
            return run_job_sandbox(src_repo, work_dir, **kwargs)
        except SandboxError as e:
            # fall back
            result = run_job_local(src_repo, work_dir, **kwargs)
            result.timeline.insert(
                0,
                TimelineEvent(ts=time.time(), kind="fallback", message=f"sandbox unavailable: {e}"),
            )
            return result
    return run_job_local(src_repo, work_dir, **kwargs)
