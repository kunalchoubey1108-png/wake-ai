from __future__ import annotations

from control_plane.agent.scavenge import parse_vulture, parse_ruff_json
from control_plane.agent.triage import triage_findings
from control_plane.models import Finding
from pathlib import Path


def test_parse_vulture(tmp_path: Path):
    sample = "src/a.py:5: unused import 'json' (90% confidence)\n"
    f = parse_vulture(sample, tmp_path)
    assert f and f[0].symbol == "json" and f[0].confidence == 90


def test_parse_ruff():
    sample = '[{"code":"F401","filename":"/tmp/x/src/a.py","message":"`json` imported but unused","location":{"row":1,"column":8}}]'
    f = parse_ruff_json(sample, Path("/tmp/x"))
    assert f and f[0].kind == "unused_import"


def test_triage_threshold():
    findings = [
        Finding(id="1", file="a.py", kind="unused_import", symbol="json", line=1, confidence=90, message="", source="vulture"),
        Finding(id="2", file="a.py", kind="unused_function", symbol="x", line=2, confidence=40, message="", source="vulture"),
    ]
    out = triage_findings(findings, threshold=60)
    assert len(out) == 1 and out[0].symbol == "json"
