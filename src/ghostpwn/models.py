"""Core data models for workflows, stages, and results.

These dataclasses are the in-memory representation of a parsed workflow plus the
structured outputs produced as it runs. They are deliberately plain so they can be
serialized to JSON for the consolidated report without external schema machinery.
"""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from typing import Any


class Severity(str, enum.Enum):
    """Severity classification for a finding."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        order = ["info", "low", "medium", "high", "critical"]
        return order.index(self.value)


class StageStatus(str, enum.Enum):
    """Terminal status of a stage after a run."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass(frozen=True)
class Finding:
    """A single security-relevant observation produced by an adapter."""

    title: str
    severity: Severity = Severity.INFO
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "severity": self.severity.value,
            "description": self.description,
            "metadata": self.metadata,
        }


@dataclass
class Stage:
    """A single workflow stage: one adapter invocation with templated params."""

    id: str
    adapter: str
    params: dict[str, Any] = field(default_factory=dict)
    needs: list[str] = field(default_factory=list)
    continue_on_error: bool = False
    timeout: float | None = None
    description: str = ""


@dataclass
class Workflow:
    """A complete workflow: a target, shared variables, and a list of stages."""

    name: str
    target: str | None = None
    vars: dict[str, Any] = field(default_factory=dict)
    stages: list[Stage] = field(default_factory=list)

    def stage_ids(self) -> list[str]:
        return [s.id for s in self.stages]

    def stage_map(self) -> dict[str, Stage]:
        return {s.id: s for s in self.stages}


@dataclass
class StageResult:
    """The structured result of running one stage."""

    stage_id: str
    adapter: str
    status: StageStatus
    outputs: dict[str, Any] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None

    @property
    def duration(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return self.finished_at - self.started_at

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["findings"] = [f.to_dict() for f in self.findings]
        data["duration"] = self.duration
        return data


@dataclass
class RunReport:
    """The consolidated report aggregating every stage result for a run."""

    workflow: str
    target: str | None
    results: list[StageResult] = field(default_factory=list)
    started_at: float | None = None
    finished_at: float | None = None

    @property
    def duration(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return self.finished_at - self.started_at

    @property
    def all_findings(self) -> list[Finding]:
        findings: list[Finding] = []
        for result in self.results:
            findings.extend(result.findings)
        return findings

    @property
    def succeeded(self) -> bool:
        """True only if no stage failed or errored (skipped is tolerated)."""
        return all(
            r.status not in (StageStatus.FAILED, StageStatus.ERROR) for r in self.results
        )

    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {s.value: 0 for s in StageStatus}
        for result in self.results:
            counts[result.status.value] += 1
        return counts

    def severity_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {s.value: 0 for s in Severity}
        for finding in self.all_findings:
            counts[finding.severity.value] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow,
            "target": self.target,
            "succeeded": self.succeeded,
            "duration": self.duration,
            "status_counts": self.status_counts(),
            "severity_counts": self.severity_counts(),
            "results": [r.to_dict() for r in self.results],
        }
