"""wake.md + wake.lock.json graveyard."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class RemovalRecord:
    id: str
    file: str
    base_sha: str
    hunk: str
    sha256: str
    depends_on: list[str] = field(default_factory=list)
    symbol: str = ""
    kind: str = ""
    reason: str = ""


@dataclass
class Graveyard:
    repo: str
    base_sha: str
    job_id: str
    removals: list[RemovalRecord] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    version: int = 1


def write_wake_lock(path: Path, g: Graveyard) -> None:
    payload: dict[str, Any] = {
        "version": g.version,
        "repo": g.repo,
        "base_sha": g.base_sha,
        "job_id": g.job_id,
        "created_at": g.created_at,
        "removals": [
            {
                "id": r.id,
                "file": r.file,
                "base_sha": r.base_sha,
                "hunk": r.hunk,
                "sha256": r.sha256,
                "depends_on": r.depends_on,
                "symbol": r.symbol,
                "kind": r.kind,
                "reason": r.reason,
            }
            for r in g.removals
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_wake_lock(path: Path) -> Graveyard:
    data = json.loads(path.read_text(encoding="utf-8"))
    removals = [RemovalRecord(**{k: v for k, v in r.items() if k in RemovalRecord.__dataclass_fields__}) for r in data.get("removals", [])]
    return Graveyard(
        repo=data.get("repo", ""),
        base_sha=data.get("base_sha", ""),
        job_id=data.get("job_id", ""),
        removals=removals,
        created_at=data.get("created_at", ""),
        version=int(data.get("version", 1)),
    )


def write_wake_md(path: Path, g: Graveyard) -> str:
    lines = [
        "# Wake.ai graveyard",
        "",
        f"- Repo: {g.repo}",
        f"- Base commit: `{g.base_sha}`",
        f"- Job id: `{g.job_id}`",
        f"- Generated (UTC): {g.created_at}",
        "",
        "## Removals",
        "",
    ]
    for r in g.removals:
        deps = ", ".join(f"`{d}`" for d in r.depends_on) if r.depends_on else "_(none)_"
        lines += [
            f"### `{r.id}` — {r.symbol or r.kind}",
            f"- **File:** `{r.file}`",
            f"- **Reason:** {r.reason or r.kind}",
            f"- **Depends on:** {deps}",
            f"- **Resurrect:** `wake resurrect {r.id}`",
            "",
            "Removed hunk:",
            "",
            "```python",
            r.hunk.rstrip("\n"),
            "```",
            "",
        ]
    text = "\n".join(lines)
    path.write_text(text, encoding="utf-8")
    return text
