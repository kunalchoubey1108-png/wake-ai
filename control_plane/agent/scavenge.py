"""Run vulture + ruff F401/F841 and parse into Finding list."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from control_plane.models import Finding


def _run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
        return r.returncode, r.stdout or "", r.stderr or ""
    except FileNotFoundError:
        return 127, "", f"missing: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def parse_vulture(text: str, repo: Path) -> list[Finding]:
    findings: list[Finding] = []
    # path:line: message (N% confidence)
    pat = re.compile(r"^(?P<path>.+?):(?P<line>\d+):\s+(?P<msg>.+?)\s+\((?P<conf>\d+)% confidence\)\s*$")
    for i, line in enumerate(text.splitlines()):
        m = pat.match(line.strip())
        if not m:
            continue
        msg = m.group("msg")
        kind = "unused"
        symbol = msg
        if "unused import" in msg:
            kind = "unused_import"
            symbol = msg.split("'")[1] if "'" in msg else msg
        elif "unused function" in msg or "unused method" in msg:
            kind = "unused_function"
            symbol = msg.split("'")[1] if "'" in msg else msg.split()[-1]
        elif "unused class" in msg:
            kind = "unused_class"
            symbol = msg.split("'")[1] if "'" in msg else msg.split()[-1]
        elif "unused variable" in msg:
            kind = "unused_variable"
            symbol = msg.split("'")[1] if "'" in msg else msg.split()[-1]
        elif "unsatisfiable" in msg:
            kind = "unreachable"
            symbol = "unreachable"
        rel = m.group("path")
        try:
            rel = str(Path(rel).resolve().relative_to(repo.resolve()))
        except Exception:
            pass
        findings.append(
            Finding(
                id=f"vulture_{i}",
                file=rel,
                kind=kind,
                symbol=symbol.strip("'\""),
                line=int(m.group("line")),
                confidence=float(m.group("conf")),
                message=msg,
                source="vulture",
            )
        )
    return findings


def parse_ruff_json(text: str, repo: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        data = json.loads(text) if text.strip() else []
    except json.JSONDecodeError:
        return findings
    for i, item in enumerate(data):
        code = item.get("code") or item.get("rule") or ""
        if code not in ("F401", "F841"):
            continue
        loc = item.get("location") or item.get("locator") or {}
        row = loc.get("row") or item.get("line", 1)
        path = item.get("filename") or item.get("file") or ""
        try:
            rel = str(Path(path).resolve().relative_to(repo.resolve()))
        except Exception:
            rel = path
        msg = item.get("message") or code
        kind = "unused_import" if code == "F401" else "unused_variable"
        # extract symbol from backticks or quotes
        sym = msg
        for sep in ("`", "'", '"'):
            if sep in msg:
                parts = msg.split(sep)
                if len(parts) >= 2:
                    sym = parts[1]
                    break
        findings.append(
            Finding(
                id=f"ruff_{i}",
                file=rel,
                kind=kind,
                symbol=sym,
                line=int(row),
                confidence=90.0,
                message=msg,
                source="ruff",
            )
        )
    return findings


def scavenge(repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    # prefer src/ else .
    target = "src" if (repo_root / "src").is_dir() else "."
    code, out, err = _run(["vulture", target, "--min-confidence", "60"], repo_root)
    findings.extend(parse_vulture(out or err, repo_root))
    code, out, err = _run(
        ["ruff", "check", target, "--select", "F401,F841", "--output-format", "json"],
        repo_root,
    )
    findings.extend(parse_ruff_json(out, repo_root))
    # dedupe by file:line:symbol
    seen: set[tuple] = set()
    uniq: list[Finding] = []
    for f in findings:
        key = (f.file, f.line, f.symbol)
        if key in seen:
            continue
        seen.add(key)
        f.id = f"f_{len(uniq):04d}"
        uniq.append(f)
    return uniq
