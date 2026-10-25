from __future__ import annotations

import hashlib
from pathlib import Path

from control_plane.patcher.diff import apply_removal, extract_symbol_hunk, restore_hunk
from control_plane.patcher.graveyard import Graveyard, RemovalRecord, load_wake_lock, write_wake_lock, write_wake_md


def test_extract_and_apply_import(tmp_path: Path):
    f = tmp_path / "m.py"
    f.write_text("import json\n\ndef ok():\n    return 1\n", encoding="utf-8")
    hunk, digest = apply_removal(tmp_path, "m.py", "json", "unused_import", 1)
    assert "import json" in hunk
    assert "import json" not in f.read_text(encoding="utf-8")
    assert digest == hashlib.sha256(hunk.encode()).hexdigest()


def test_extract_function(tmp_path: Path):
    src = "def keep():\n    return 1\n\ndef unused_helper():\n    return 2\n\ndef also():\n    return 3\n"
    hunk, new = extract_symbol_hunk(src, "unused_helper", "unused_function", 4)
    assert "def unused_helper" in hunk
    assert "def unused_helper" not in new
    assert "def keep" in new and "def also" in new


def test_graveyard_roundtrip(tmp_path: Path):
    g = Graveyard(
        repo="demo",
        base_sha="abc",
        job_id="job_1",
        removals=[
            RemovalRecord(
                id="f_0001",
                file="m.py",
                base_sha="abc",
                hunk="import json\n",
                sha256=hashlib.sha256(b"import json\n").hexdigest(),
                symbol="json",
                kind="unused_import",
            )
        ],
    )
    lock = tmp_path / "wake.lock.json"
    md = tmp_path / "wake.md"
    write_wake_lock(lock, g)
    text = write_wake_md(md, g)
    assert "f_0001" in text
    loaded = load_wake_lock(lock)
    assert loaded.removals[0].id == "f_0001"


def test_restore_hunk(tmp_path: Path):
    f = tmp_path / "m.py"
    f.write_text("def ok():\n    return 1\n", encoding="utf-8")
    hunk = "import json\n"
    digest = hashlib.sha256(hunk.encode()).hexdigest()
    restore_hunk(tmp_path, "m.py", hunk, expected_sha256=digest)
    assert "import json" in f.read_text(encoding="utf-8") or "wake resurrect" in f.read_text(encoding="utf-8")
