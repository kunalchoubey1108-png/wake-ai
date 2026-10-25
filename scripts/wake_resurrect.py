#!/usr/bin/env python3
"""Standalone resurrect (~40 lines): reverse a wake.lock.json removal into the working tree."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description="Resurrect a Wake.ai removal from wake.lock.json")
    p.add_argument("removal_id")
    p.add_argument("--lock", default="wake.lock.json")
    p.add_argument("--repo", default=".")
    args = p.parse_args()
    lock = Path(args.lock)
    data = json.loads(lock.read_text(encoding="utf-8"))
    rec = next((r for r in data.get("removals", []) if r["id"] == args.removal_id), None)
    if not rec:
        print(f"unknown id: {args.removal_id}", file=sys.stderr)
        return 1
    hunk, digest = rec["hunk"], rec["sha256"]
    if hashlib.sha256(hunk.encode()).hexdigest() != digest:
        print("sha256 mismatch — refusing", file=sys.stderr)
        return 2
    path = Path(args.repo) / rec["file"]
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if not text.endswith("\n") and text:
        text += "\n"
    path.write_text(text + "\n# --- wake resurrect ---\n" + hunk, encoding="utf-8")
    print(f"resurrected {args.removal_id} into {rec['file']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
