from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wake_resurrect_script(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    f = repo / "a.py"
    f.write_text("x = 1\n", encoding="utf-8")
    hunk = "import json\n"
    lock = {
        "version": 1,
        "repo": "t",
        "base_sha": "x",
        "job_id": "j",
        "created_at": "t",
        "removals": [
            {
                "id": "f_0001",
                "file": "a.py",
                "base_sha": "x",
                "hunk": hunk,
                "sha256": hashlib.sha256(hunk.encode()).hexdigest(),
                "depends_on": [],
            }
        ],
    }
    lock_path = tmp_path / "wake.lock.json"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "wake_resurrect.py"), "f_0001", "--lock", str(lock_path), "--repo", str(repo)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "json" in f.read_text(encoding="utf-8")
