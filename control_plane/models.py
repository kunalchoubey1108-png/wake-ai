from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class Finding(BaseModel):
    id: str
    file: str
    kind: str  # unused_import | unused_variable | unused_function | unused_class | unreachable
    symbol: str
    line: int
    confidence: float
    message: str
    source: str  # vulture | ruff
    status: str = "candidate"  # candidate | removed | alive | skipped


class TimelineEvent(BaseModel):
    ts: float
    kind: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class ContainmentEvidence(BaseModel):
    runtime: str = ""
    uid: Optional[int] = None
    container_id: str = ""
    peak_memory_bytes: Optional[int] = None
    kills: list[str] = Field(default_factory=list)
    teardown_ms: Optional[float] = None
    env_dump: dict[str, str] = Field(default_factory=dict)
    network_mode_final: str = ""
    notes: list[str] = Field(default_factory=list)


class JobResult(BaseModel):
    job_id: str
    status: JobStatus
    repo_label: str = ""
    base_sha: str = ""
    findings: list[Finding] = Field(default_factory=list)
    removals: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    containment: Optional[ContainmentEvidence] = None
    error: Optional[str] = None
    wake_md: str = ""
    replay: bool = False
