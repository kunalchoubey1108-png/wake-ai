"""
BUILD-WEEK STUB: triage.

Deterministic fallback — keep findings at/above scanner confidence threshold.
TODO(build-week): LLM triage via llm_gateway (no prompts until kickoff).
"""
from __future__ import annotations

from control_plane.models import Finding

DEFAULT_THRESHOLD = 60.0


def triage_findings(findings: list[Finding], *, threshold: float = DEFAULT_THRESHOLD) -> list[Finding]:
    out: list[Finding] = []
    for f in findings:
        conf = f.confidence if f.confidence <= 1.0 else f.confidence  # vulture uses 0-100
        score = conf if conf > 1.0 else conf * 100
        if score >= threshold:
            f.status = "candidate"
            out.append(f)
        else:
            f.status = "skipped"
    return out
