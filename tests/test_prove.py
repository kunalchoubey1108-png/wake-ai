from __future__ import annotations

from pathlib import Path

from control_plane.agent.prove import prove_loop
from control_plane.models import Finding


def _repo_with_dead(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "mod.py").write_text(
        "import json\n\ndef used():\n    return 42\n\ndef unused_helper():\n    return 0\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_mod.py").write_text(
        "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))\nfrom mod import used\n\ndef test_used():\n    assert used() == 42\n",
        encoding="utf-8",
    )
    return repo


def test_prove_removes_safe_dead_code(tmp_path: Path):
    repo = _repo_with_dead(tmp_path)
    cands = [
        Finding(id="f_0001", file="src/mod.py", kind="unused_import", symbol="json", line=1, confidence=90, message="unused import 'json'", source="vulture"),
        Finding(id="f_0002", file="src/mod.py", kind="unused_function", symbol="unused_helper", line=5, confidence=60, message="unused function 'unused_helper'", source="vulture"),
    ]
    result = prove_loop(repo, cands, base_sha="x", job_id="j", repo_label="r")
    assert len(result.removed) >= 1
    text = (repo / "src" / "mod.py").read_text(encoding="utf-8")
    assert "def used" in text


def test_prove_marks_alive_when_removal_breaks_tests(tmp_path: Path):
    repo = tmp_path / "r"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "mod.py").write_text("def critical():\n    return 1\n", encoding="utf-8")
    (repo / "tests" / "test_mod.py").write_text(
        "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))\nfrom mod import critical\n\ndef test_c():\n    assert critical() == 1\n",
        encoding="utf-8",
    )
    cands = [
        Finding(id="f_0001", file="src/mod.py", kind="unused_function", symbol="critical", line=1, confidence=60, message="unused function", source="vulture"),
    ]
    result = prove_loop(repo, cands, base_sha="x", job_id="j", repo_label="r")
    assert any(a.symbol == "critical" for a in result.alive)
    assert "def critical" in (repo / "src" / "mod.py").read_text(encoding="utf-8")
