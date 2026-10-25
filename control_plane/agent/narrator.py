"""
BUILD-WEEK STUB: narrator.

Deterministic timeline messages only.
TODO(build-week): LLM narration via llm_gateway.
"""
from __future__ import annotations


def narrate(kind: str, **kwargs) -> str:
    templates = {
        "start": "Job {job_id} started for {label}.",
        "scan": "Scavenge complete: {n} findings.",
        "triage": "Triage (confidence≥{threshold}): {n} candidates.",
        "baseline": "Baseline tests: {ok}.",
        "batch": "Proving batch of {n} removals…",
        "split": "Batch failed — splitting.",
        "removed": "Removed {symbol} from {file}.",
        "alive": "Restored {symbol} — marked alive.",
        "done": "Done: {removed} removed, {alive} left alive.",
        "containment": "Containment evidence recorded (runtime={runtime}).",
    }
    return templates.get(kind, kind).format(**kwargs)
