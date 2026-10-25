from __future__ import annotations

import asyncio
import json
import io
import shutil
import tarfile
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from control_plane.agent.sandbox_pipeline import run_job_auto as run_job_local
from control_plane.api.db import Database
from control_plane.config import settings
from control_plane.patcher.graveyard import load_wake_lock
from control_plane.patcher.diff import restore_hunk

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "demo-repos"
WEB = ROOT / "web"

REPLAY = ROOT / "replay"


def _load_replay_fixture(label: str) -> dict:
    # map github urls / uploads to tidy-todo fallback
    key = label
    if label not in ("tidy-todo", "flask-blog", "poisoned-carcass"):
        key = "tidy-todo"
    path = REPLAY / f"{key}.json"
    if not path.is_file():
        # also try settings path
        alt = settings.wake_replay_dir / f"{key}.json"
        path = alt if alt.is_file() else path
    if not path.is_file():
        raise FileNotFoundError(f"no replay fixture for {key}")
    import copy
    data = json.loads(path.read_text(encoding="utf-8"))
    return copy.deepcopy(data)


def _should_force_replay(db: Database, explicit: bool) -> tuple[bool, str]:
    if explicit:
        return True, "explicit"
    if db.count_all_jobs() >= settings.wake_spend_cap_jobs:
        return True, "spend_cap"
    return False, ""


def create_app() -> FastAPI:
    settings.wake_data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.wake_data_dir / "wake.db")
    app = FastAPI(title="Wake.ai", version="0.1.0")
    app.state.db = db

    if (WEB / "static").is_dir():
        app.mount("/static", StaticFiles(directory=str(WEB / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index():
        index_path = WEB / "templates" / "index.html"
        return index_path.read_text(encoding="utf-8")

    @app.get("/api/health")
    def health():
        return {"ok": True, "service": "wake.ai", "ai": "stubbed-until-build-week"}

    @app.get("/api/demo-repos")
    def demo_repos():
        items = []
        if DEMO.is_dir():
            for p in sorted(DEMO.iterdir()):
                if p.is_dir() and not p.name.startswith("."):
                    items.append({"id": p.name, "path": str(p), "danger": p.name == "poisoned-carcass"})
        return {"repos": items}

    def _client_ip(request: Request) -> str:
        return request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0].strip()

    def _rate_check(ip: str) -> None:
        if db.count_recent(ip) >= settings.wake_rate_limit_jobs_per_hour:
            raise HTTPException(429, "rate limit: 3 jobs/IP/hour")
        if db.count_running(ip) >= settings.wake_max_running_per_ip:
            raise HTTPException(429, "rate limit: 1 running job per IP")

    def _start_job(src: Path, ip: str, label: str, replay: bool = False) -> str:
        force, reason = _should_force_replay(db, replay)
        if not force:
            try:
                _rate_check(ip)
            except HTTPException as e:
                if e.status_code == 429:
                    force, reason = True, "rate_limit"
                else:
                    raise
        job_id = f"job_{uuid.uuid4().hex[:10]}"
        work = settings.wake_data_dir / "jobs"
        work.mkdir(parents=True, exist_ok=True)
        db.insert_job(job_id, ip, label, str(work), replay=force)
        if not force:
            db.record_rate(ip)

        def worker():
            db.update_job(job_id, "running")
            try:
                if force:
                    fixture = _load_replay_fixture(label if label in ("tidy-todo", "flask-blog", "poisoned-carcass") else "tidy-todo")
                    fixture["job_id"] = job_id
                    fixture["replay"] = True
                    fixture.setdefault("timeline", [])
                    # stream-friendly: stamp reason on first event
                    fixture["timeline"].insert(
                        0,
                        {"ts": time.time(), "kind": "replay", "message": f"Serving recorded runsc fixture ({reason})", "data": {"reason": reason}},
                    )
                    # pace timeline slightly so SSE clients see events
                    time.sleep(0.15)
                    db.update_job(job_id, fixture.get("status", "succeeded"), fixture)
                    return
                result = run_job_local(src, work, job_id=job_id, repo_label=label, replay=False)
                db.update_job(job_id, result.status.value, result.model_dump(mode="json"))
            except Exception as e:
                db.update_job(job_id, "failed", {"job_id": job_id, "status": "failed", "error": str(e), "timeline": []})

        threading.Thread(target=worker, daemon=True).start()
        return job_id

    @app.post("/api/jobs")
    async def create_job(
        request: Request,
        github_url: Optional[str] = Form(None),
        demo_id: Optional[str] = Form(None),
        replay: bool = Form(False),
        archive: Optional[UploadFile] = File(None),
    ):
        ip = _client_ip(request)
        if demo_id:
            force_replay, _reason = _should_force_replay(db, replay)
            if demo_id == "poisoned-carcass" and not force_replay:
                raise HTTPException(
                    400,
                    "poisoned-carcass only via replay (?replay=1 / spend cap) or a hardened sandbox with WAKE_SANDBOX=1; "
                    "not available as a live host-local demo",
                )
            src = DEMO / demo_id
            if not src.is_dir() and demo_id != "poisoned-carcass":
                raise HTTPException(404, "unknown demo")
            if not src.is_dir():
                src = DEMO / "tidy-todo"  # unused when replaying poisoned fixture
            job_id = _start_job(src, ip, demo_id, replay=force_replay or replay)
            return {"job_id": job_id, "replay": force_replay or replay}

        if archive is not None:
            data = await archive.read()
            if len(data) > 5 * 1024 * 1024:
                raise HTTPException(400, "zip must be ≤5MB")
            tmp = settings.wake_data_dir / "uploads" / f"{uuid.uuid4().hex}"
            tmp.mkdir(parents=True)
            zpath = tmp / "upload.zip"
            zpath.write_bytes(data)
            extract = tmp / "src"
            extract.mkdir()
            try:
                with zipfile.ZipFile(zpath) as zf:
                    names = zf.namelist()
                    if len(names) > 300:
                        raise HTTPException(400, "zip must contain ≤300 files")
                    zf.extractall(extract)
            except zipfile.BadZipFile:
                raise HTTPException(400, "invalid zip")
            # if single top dir, use it
            kids = [p for p in extract.iterdir() if not p.name.startswith(".")]
            src = kids[0] if len(kids) == 1 and kids[0].is_dir() else extract
            job_id = _start_job(src, ip, archive.filename or "upload", replay=replay)
            return {"job_id": job_id}

        if github_url:
            # Scaffolding: shallow clone locally (network). Production: clone inside sandbox with net then disable.
            tmp = settings.wake_data_dir / "clones" / uuid.uuid4().hex
            tmp.mkdir(parents=True)
            import subprocess

            r = subprocess.run(
                ["git", "clone", "--depth", "1", github_url, str(tmp / "repo")],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if r.returncode != 0:
                raise HTTPException(400, f"clone failed: {r.stderr[:500]}")
            job_id = _start_job(tmp / "repo", ip, github_url, replay=replay)
            return {"job_id": job_id}

        raise HTTPException(400, "provide demo_id, github_url, or archive")

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        row = db.get_job(job_id)
        if not row:
            raise HTTPException(404)
        return row

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str):
        async def gen():
            last = 0
            for _ in range(600):
                row = db.get_job(job_id)
                if not row:
                    yield {"event": "error", "data": "not found"}
                    return
                result = row.get("result") or {}
                timeline = result.get("timeline") or []
                while last < len(timeline):
                    ev = timeline[last]
                    yield {"event": "timeline", "data": json.dumps(ev)}
                    last += 1
                if row["status"] in ("succeeded", "failed", "cancelled"):
                    yield {"event": "done", "data": row["status"]}
                    return
                await asyncio.sleep(0.4)

        return EventSourceResponse(gen())

    @app.get("/api/jobs/{job_id}/graveyard")
    def graveyard(job_id: str):
        row = db.get_job(job_id)
        if not row:
            raise HTTPException(404)
        result = row.get("result") or {}
        return {"removals": result.get("removals") or [], "wake_md": result.get("wake_md") or ""}

    @app.post("/api/jobs/{job_id}/resurrect/{removal_id}")
    def resurrect_one(job_id: str, removal_id: str):
        row = db.get_job(job_id)
        if not row:
            raise HTTPException(404)
        repo = Path(row["work_dir"]) / job_id / "repo"
        lock = repo / "wake.lock.json"
        if not lock.is_file():
            raise HTTPException(404, "no wake.lock.json")
        g = load_wake_lock(lock)
        rec = next((r for r in g.removals if r.id == removal_id), None)
        if not rec:
            raise HTTPException(404, "unknown removal")
        restore_hunk(repo, rec.file, rec.hunk, expected_sha256=rec.sha256)
        g.removals = [r for r in g.removals if r.id != removal_id]
        from control_plane.patcher.graveyard import write_wake_lock, write_wake_md

        write_wake_lock(lock, g)
        write_wake_md(repo / "wake.md", g)
        return {"ok": True, "resurrected": removal_id}

    @app.post("/api/jobs/{job_id}/resurrect")
    def resurrect_all(job_id: str):
        row = db.get_job(job_id)
        if not row:
            raise HTTPException(404)
        repo = Path(row["work_dir"]) / job_id / "repo"
        lock = repo / "wake.lock.json"
        if not lock.is_file():
            raise HTTPException(404)
        g = load_wake_lock(lock)
        ids = []
        for rec in list(g.removals):
            restore_hunk(repo, rec.file, rec.hunk, expected_sha256=rec.sha256)
            ids.append(rec.id)
        g.removals = []
        from control_plane.patcher.graveyard import write_wake_lock, write_wake_md

        write_wake_lock(lock, g)
        write_wake_md(repo / "wake.md", g)
        return {"ok": True, "resurrected": ids}

    @app.get("/api/jobs/{job_id}/download")
    def download(job_id: str):
        row = db.get_job(job_id)
        if not row:
            raise HTTPException(404)
        repo = Path(row["work_dir"]) / job_id / "repo"
        if not repo.is_dir():
            raise HTTPException(404)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in repo.rglob("*"):
                if p.is_file() and ".git" not in p.parts:
                    zf.write(p, p.relative_to(repo))
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{job_id}.zip"'},
        )


    @app.get("/api/replay")
    def list_replay():
        items = []
        for p in sorted(REPLAY.glob("*.json")):
            items.append({"id": p.stem, "path": str(p.relative_to(ROOT))})
        return {"fixtures": items, "spend_cap": settings.wake_spend_cap_jobs, "jobs_so_far": db.count_all_jobs()}

    @app.get("/api/containment/evidence")
    def containment_evidence():
        path = ROOT / "docs" / "poisoned_carcass_evidence.json"
        if not path.is_file():
            raise HTTPException(404)
        return json.loads(path.read_text(encoding="utf-8"))

    return app


app = create_app()
