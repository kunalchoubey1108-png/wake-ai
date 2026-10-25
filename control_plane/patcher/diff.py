"""Deterministic source edits and unified diffs."""
from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def extract_symbol_hunk(source: str, symbol: str, kind: str, line: int) -> tuple[str, str]:
    """
    Return (hunk_text, new_source) by removing the symbol definition / import.
    Heuristic, line-anchored; good enough for demo fixtures.
    """
    lines = source.splitlines(keepends=True)
    idx = max(0, min(line - 1, len(lines) - 1))

    if kind in ("unused_import",) or "import" in kind:
        # remove the import line containing symbol
        for i, ln in enumerate(lines):
            if symbol in ln and ("import" in ln or "from " in ln):
                hunk = ln
                new = "".join(lines[:i] + lines[i + 1 :])
                return hunk, new
        # fallback: remove idx line
        hunk = lines[idx]
        new = "".join(lines[:idx] + lines[idx + 1 :])
        return hunk, new

    if kind in ("unused_variable",):
        for i, ln in enumerate(lines):
            if re.match(rf"^\s*{re.escape(symbol)}\s*=", ln):
                hunk = ln
                new = "".join(lines[:i] + lines[i + 1 :])
                return hunk, new
        hunk = lines[idx]
        new = "".join(lines[:idx] + lines[idx + 1 :])
        return hunk, new

    # function / class / unreachable: remove block from def/class or if False
    start = idx
    for i in range(idx, -1, -1):
        if re.match(rf"^(async\s+)?def\s+{re.escape(symbol)}\b", lines[i]) or re.match(
            rf"^class\s+{re.escape(symbol)}\b", lines[i]
        ):
            start = i
            break
        if kind == "unreachable" and re.search(r"if\s+False\b", lines[i]):
            start = i
            break
    # determine indent
    indent_m = re.match(r"^(\s*)", lines[start])
    base_indent = indent_m.group(1) if indent_m else ""
    end = start + 1
    while end < len(lines):
        ln = lines[end]
        if ln.strip() == "":
            end += 1
            continue
        cur = re.match(r"^(\s*)", ln).group(1)
        if len(cur) <= len(base_indent) and not ln.startswith(base_indent + " ") and not ln.startswith(base_indent + "\t"):
            # dedent — end of block (allow nested empty handled above)
            if ln.startswith(base_indent) and len(cur) == len(base_indent):
                # same indent: end
                break
            if len(cur) < len(base_indent):
                break
        end += 1
    hunk = "".join(lines[start:end])
    new = "".join(lines[:start] + lines[end:])
    return hunk, new


def apply_removal(repo_root: Path, file_rel: str, symbol: str, kind: str, line: int) -> tuple[str, str]:
    """Apply removal; return (hunk, sha256_hex)."""
    path = repo_root / file_rel
    if not path.is_file():
        raise FileNotFoundError(file_rel)
    src = _read(path)
    hunk, new = extract_symbol_hunk(src, symbol, kind, line)
    _write(path, new)
    digest = hashlib.sha256(hunk.encode("utf-8")).hexdigest()
    return hunk, digest


def restore_hunk(repo_root: Path, file_rel: str, hunk: str, *, expected_sha256: str | None = None) -> None:
    """Re-insert hunk by appending near original location via reverse patch when possible."""
    if expected_sha256:
        got = hashlib.sha256(hunk.encode("utf-8")).hexdigest()
        if got != expected_sha256:
            raise ValueError("hunk sha256 mismatch")
    path = repo_root / file_rel
    # Try git apply --3way with a reverse unified diff first
    if _try_git_apply_reverse(repo_root, file_rel, hunk):
        return
    # Fallback: append hunk at end of file (deterministic, visible)
    existing = _read(path) if path.is_file() else ""
    if not existing.endswith("\n") and existing:
        existing += "\n"
    _write(path, existing + "\n# --- wake resurrect ---\n" + hunk)


def _try_git_apply_reverse(repo_root: Path, file_rel: str, hunk: str) -> bool:
    """Build a synthetic reverse patch: deletion of hunk as addition."""
    # Create a patch that adds the hunk at line 1 as a best-effort; git apply --3way
    lines = hunk.splitlines(keepends=True)
    if not lines:
        return False
    body = "".join("+" + (ln if ln.endswith("\n") else ln + "\n") for ln in lines)
    patch = f"diff --git a/{file_rel} b/{file_rel}\n--- a/{file_rel}\n+++ b/{file_rel}\n@@ -0,0 +1,{len(lines)} @@\n{body}"
    try:
        r = subprocess.run(
            ["git", "apply", "--3way", "--whitespace=nowarn", "-"],
            cwd=repo_root,
            input=patch.encode(),
            capture_output=True,
            timeout=30,
        )
        return r.returncode == 0
    except Exception:
        return False


def write_unified_diff(path: Path, old: str, new: str, file_rel: str) -> str:
    import difflib

    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{file_rel}",
        tofile=f"b/{file_rel}",
    )
    text = "".join(diff)
    path.write_text(text, encoding="utf-8")
    return text
