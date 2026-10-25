from __future__ import annotations

from pathlib import Path

import pytest

from control_plane.agent.pipeline import run_job_local

ROOT = Path(__file__).resolve().parents[1]
DEMOS = ROOT / "demo-repos"


@pytest.mark.parametrize("name", ["tidy-todo", "flask-blog"])
def test_e2e_demo_local(name: str, tmp_path: Path):
    src = DEMOS / name
    assert src.is_dir()
    result = run_job_local(src, tmp_path, repo_label=name)
    assert result.status.value == "succeeded"
    assert result.wake_md
    # should remove at least one planted dead item
    assert len(result.removals) >= 1
    repo = tmp_path / result.job_id / "repo"
    assert (repo / "wake.lock.json").is_file()
