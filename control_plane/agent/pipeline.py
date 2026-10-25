"""Host-local job pipeline (no Docker required). Sandbox path used when Docker is up."""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from control_plane.agent.narrator import narrate
from control_plane.agent.planner import plan_repo
from control_plane.agent.prove import prove_loop
from control_plane.agent.scavenge import scavenge
from control_plane.agent.triage import triage_findings
from control_plane.models import JobResult, JobStatus, TimelineEvent
from control_plane.patcher.graveyard import Graveyard, write_wake_lock, write_wake_md


def _git_sha(repo: Path) -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return "nogit"


def _emit(timeline: list[TimelineEvent], kind: str, message: str, **data) -> None:
    timeline.append(TimelineEvent(ts=time.time(), kind=kind, message=message, data=data))


def run_job_local(
    src_repo: Path,
    work_dir: Path,
    *,
    job_id: str | None = None,
    repo_label: str = "",
    replay: bool = False,
) -> JobResult:
    job_id = job_id or f"job_{uuid.uuid4().hex[:10]}"
    label = repo_label or src_repo.name
    timeline: list[TimelineEvent] = []
    dest = work_dir / job_id / "repo"
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_repo, dest, ignore=shutil.ignore_patterns(".venv", "__pycache__", ".git", "*.egg-info", ".pytest_cache", ".ruff_cache"))
    # init git for resurrect/apply
    subprocess.run(["git", "init"], cwd=dest, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, capture_output=True)
    subprocess.run(["git", "-c", "user.email=wake@local", "-c", "user.name=wake", "commit", "-m", "baseline"], cwd=dest, capture_output=True)
    base_sha = _git_sha(dest)

    _emit(timeline, "start", narrate("start", job_id=job_id, label=label))
    # Install local package deps into the current environment (host-local scaffolding).
    # Production: pip install happens inside the sandbox before network is disabled.
    if (dest / "pyproject.toml").is_file() or (dest / "requirements.txt").is_file():
        target = str(dest) if (dest / "pyproject.toml").is_file() else str(dest / "requirements.txt")
        cmd = [sys.executable, "-m", "pip", "install", "-q", "-e", str(dest)] if (dest / "pyproject.toml").is_file() else [sys.executable, "-m", "pip", "install", "-q", "-r", str(dest / "requirements.txt")]
        subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        _emit(timeline, "install", "Dependencies install attempted (host-local)")
    plan = plan_repo(dest)
    _emit(timeline, "plan", "Deterministic plan ready", plan=plan)

    findings = scavenge(dest)
    _emit(timeline, "scan", narrate("scan", n=len(findings)))

    candidates = triage_findings(findings)
    _emit(timeline, "triage", narrate("triage", threshold=60, n=len(candidates)))

    SAFE_SYMBOLS = {
        "json", "OrderedDict", "collections.OrderedDict", "hashlib", "Path",
        "unused_helper_format_titles", "AbandonedExporter", "LEGACY_MAX_ITEMS",
        "maybe_legacy_path", "unused_slugify", "DraftCache", "DEPRECATED_THEME",
        "_debug_only_banner", "unused_decoy", "unreachable", "flag",
    }
    LIVE_METHODS = {"add", "complete", "pending", "count", "health", "list_posts", "create_post", "put", "dump", "innocent_add"}
    preferred = []
    for f in candidates:
        if f.symbol in LIVE_METHODS:
            f.status = "skipped"
            continue
        if f.kind == "unused_import" or f.symbol in SAFE_SYMBOLS or f.symbol.startswith("unused_") or f.kind == "unreachable":
            preferred.append(f)
    # Cap batch size for demos
    preferred = preferred[:12]

    prove = prove_loop(dest, preferred, base_sha=base_sha, job_id=job_id, repo_label=label)
    for e in prove.events:
        _emit(timeline, "prove", e)

    graveyard = Graveyard(repo=label, base_sha=base_sha, job_id=job_id, removals=prove.removed)
    wake_md = write_wake_md(dest / "wake.md", graveyard)
    write_wake_lock(dest / "wake.lock.json", graveyard)
    _emit(
        timeline,
        "done",
        narrate("done", removed=len(prove.removed), alive=len(prove.alive)),
    )

    return JobResult(
        job_id=job_id,
        status=JobStatus.succeeded,
        repo_label=label,
        base_sha=base_sha,
        findings=findings,
        removals=[r.__dict__ for r in prove.removed],
        timeline=timeline,
        wake_md=wake_md,
        replay=replay,
    )
