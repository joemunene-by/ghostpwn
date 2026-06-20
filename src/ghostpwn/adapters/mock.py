"""Deterministic mock adapter for demos and tests.

The mock adapter performs no real I/O. It echoes its params, emits configurable
outputs and findings, and can be told to fail or sleep. Because its behaviour is
fully determined by its params, it underpins the offline test suite and the
quickstart example so ghostpwn is runnable with zero external tools installed.
"""

from __future__ import annotations

import time
from typing import Any

from ..models import Finding, Severity, StageResult, StageStatus
from .base import Adapter, StageContext


class MockAdapter(Adapter):
    """A configurable, side-effect-free adapter.

    Supported params:
      - ``outputs``: dict merged verbatim into the stage outputs.
      - ``findings``: list of ``{title, severity, description}`` dicts.
      - ``fail``: if truthy, the stage reports FAILED.
      - ``message``: optional string echoed into outputs as ``message``.
      - ``sleep``: optional float seconds to sleep (used to observe parallelism).
      - ``echo``: arbitrary value echoed into outputs as ``echo``.
    """

    name = "mock"

    def run(self, context: StageContext) -> StageResult:
        params = context.params
        if params.get("sleep"):
            time.sleep(float(params["sleep"]))

        outputs: dict[str, Any] = {"stage_id": context.stage_id}
        if context.target is not None:
            outputs["target"] = context.target
        if "outputs" in params and isinstance(params["outputs"], dict):
            outputs.update(params["outputs"])
        if "message" in params:
            outputs["message"] = params["message"]
        if "echo" in params:
            outputs["echo"] = params["echo"]

        findings: list[Finding] = []
        for raw in params.get("findings", []) or []:
            findings.append(
                Finding(
                    title=raw.get("title", "mock finding"),
                    severity=Severity(raw.get("severity", "info")),
                    description=raw.get("description", ""),
                    metadata=raw.get("metadata", {}) or {},
                )
            )

        if params.get("fail"):
            return StageResult(
                stage_id=context.stage_id,
                adapter=self.name,
                status=StageStatus.FAILED,
                outputs=outputs,
                findings=findings,
                error=str(params.get("error", "mock failure requested")),
            )

        return StageResult(
            stage_id=context.stage_id,
            adapter=self.name,
            status=StageStatus.SUCCESS,
            outputs=outputs,
            findings=findings,
        )
