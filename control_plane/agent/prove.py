"""
Prove loop: baseline → batch remove → re-test → split on failure → restore culprit → mark alive.
Runs against a local checkout (host-side) for unit tests; sandbox path wraps the same logic.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from control_plane.models import Finding
from control_plane.patcher.diff import apply_removal, restore_hunk
from control_plane.patcher.graveyard import Graveyard, RemovalRecord


TestFn = Callable[[Path], bool]


def default_pytest(repo: Path) -> bool:
    import os
    import sys
    env = os.environ.copy()
    src = repo / "src"
    parts = [str(src)] if src.is_dir() else []
    if env.get("PYTHONPATH"):
        parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    return r.returncode == 0


@dataclass
class ProveResult:
    removed: list[RemovalRecord] = field(default_factory=list)
    alive: list[Finding] = field(default_factory=list)
    events: list[str] = field(default_factory=list)


def prove_loop(
    repo: Path,
    candidates: list[Finding],
    *,
    base_sha: str,
    job_id: str,
    repo_label: str,
    test_fn: TestFn | None = None,
) -> ProveResult:
    test_fn = test_fn or default_pytest
    result = ProveResult()
    if not test_fn(repo):
        result.events.append("baseline failed — abort")
        for c in candidates:
            c.status = "alive"
            result.alive.append(c)
        return result
    result.events.append("baseline ok")

    def try_batch(batch: list[Finding]) -> bool:
        """Apply all, test; on failure restore all and return False."""
        applied: list[tuple[Finding, str, str]] = []  # finding, hunk, sha
        try:
            for f in batch:
                hunk, digest = apply_removal(repo, f.file, f.symbol, f.kind, f.line)
                applied.append((f, hunk, digest))
            if test_fn(repo):
                for f, hunk, digest in applied:
                    f.status = "removed"
                    result.removed.append(
                        RemovalRecord(
                            id=f.id,
                            file=f.file,
                            base_sha=base_sha,
                            hunk=hunk,
                            sha256=digest,
                            symbol=f.symbol,
                            kind=f.kind,
                            reason=f"{f.source}: {f.message}",
                        )
                    )
                    result.events.append(f"removed {f.symbol}")
                return True
        except Exception as e:
            result.events.append(f"apply error: {e}")
        # restore in reverse
        for f, hunk, digest in reversed(applied):
            try:
                # re-read won't have hunk — restore by writing hunk back via restore_hunk
                restore_hunk(repo, f.file, hunk, expected_sha256=digest)
            except Exception as e:
                result.events.append(f"restore error {f.id}: {e}")
        return False

    def split_prove(batch: list[Finding]) -> None:
        if not batch:
            return
        if len(batch) == 1:
            f = batch[0]
            if try_batch([f]):
                return
            f.status = "alive"
            result.alive.append(f)
            result.events.append(f"alive {f.symbol}")
            return
        if try_batch(batch):
            return
        result.events.append(f"split n={len(batch)}")
        mid = len(batch) // 2
        split_prove(batch[:mid])
        split_prove(batch[mid:])

    split_prove(list(candidates))
    return result
