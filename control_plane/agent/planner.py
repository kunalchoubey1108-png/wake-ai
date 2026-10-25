"""
BUILD-WEEK STUB: planner.

Deterministic fallback — detect pytest heuristically. No LLM.
TODO(build-week): call llm_gateway with planning prompt (not before 3 Nov).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def plan_repo(repo_root: Path) -> dict[str, Any]:
    """Return a simple execution plan without AI."""
    has_pytest = False
    for name in ("pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini"):
        p = repo_root / name
        if p.is_file() and "pytest" in p.read_text(encoding="utf-8", errors="ignore").lower():
            has_pytest = True
            break
    if not has_pytest and (repo_root / "tests").is_dir():
        has_pytest = True
    test_cmd = ["python", "-m", "pytest", "-q"] if has_pytest else ["python", "-c", "print('no-tests')"]
    return {
        "has_pytest": has_pytest,
        "test_cmd": test_cmd,
        "scan_cmd_vulture": ["vulture", "src", "--min-confidence", "60"],
        "scan_cmd_ruff": ["ruff", "check", "src", "--select", "F401,F841", "--output-format", "json"],
        "notes": ["deterministic planner stub — replace during build week"],
    }
