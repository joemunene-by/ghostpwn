"""The orchestration engine: schedule and run a workflow's stages.

Given a validated workflow, the orchestrator:

  - resolves each stage's templated params against workflow vars and the outputs
    of already-completed stages,
  - runs independent stages concurrently using asyncio, bounded by a concurrency
    limit, while honouring ``needs`` ordering,
  - enforces per-stage timeouts,
  - applies the failure policy: a failed required stage skips its transitive
    dependents, whereas ``continue_on_error`` lets dependents still run,
  - aggregates everything into a :class:`RunReport`.

Synchronous adapters are dispatched to a thread via ``asyncio.to_thread`` so they
never block the event loop; async adapters are awaited directly.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from typing import Any

from . import adapters
from .adapters.base import StageContext
from .errors import TemplateError
from .graph import DependencyGraph
from .models import RunReport, Stage, StageResult, StageStatus, Workflow
from .template import render

logger = logging.getLogger("ghostpwn.orchestrator")


class Orchestrator:
    """Execute a workflow's stage DAG with bounded parallelism."""

    def __init__(
        self,
        workflow: Workflow,
        graph: DependencyGraph,
        *,
        concurrency: int = 4,
        output_dir: str | None = None,
        dry_run: bool = False,
    ) -> None:
        self.workflow = workflow
        self.graph = graph
        self.concurrency = max(1, concurrency)
        self.output_dir = output_dir
        self.dry_run = dry_run
        self._stage_map: dict[str, Stage] = workflow.stage_map()
        self._results: dict[str, StageResult] = {}
        self._semaphore = asyncio.Semaphore(self.concurrency)

    def run(self) -> RunReport:
        """Synchronous entry point. Runs the async scheduler to completion."""
        return asyncio.run(self.run_async())

    async def run_async(self) -> RunReport:
        report = RunReport(
            workflow=self.workflow.name,
            target=self.workflow.target,
            started_at=time.time(),
        )
        order = self.graph.topological_order()
        remaining = set(order)
        running: dict[str, asyncio.Task[StageResult]] = {}

        while remaining or running:
            # Launch every stage whose dependencies are all complete.
            for stage_id in list(remaining):
                stage = self._stage_map[stage_id]
                if not self._deps_complete(stage):
                    continue
                skip_reason = self._skip_reason(stage)
                if skip_reason is not None:
                    self._results[stage_id] = StageResult(
                        stage_id=stage_id,
                        adapter=stage.adapter,
                        status=StageStatus.SKIPPED,
                        error=skip_reason,
                    )
                    remaining.discard(stage_id)
                    continue
                remaining.discard(stage_id)
                running[stage_id] = asyncio.create_task(self._run_stage(stage))

            if not running:
                # Nothing runnable and nothing running: every leftover is skipped.
                for stage_id in list(remaining):
                    stage = self._stage_map[stage_id]
                    self._results[stage_id] = StageResult(
                        stage_id=stage_id,
                        adapter=stage.adapter,
                        status=StageStatus.SKIPPED,
                        error="skipped: dependency did not complete",
                    )
                    remaining.discard(stage_id)
                break

            done, _ = await asyncio.wait(
                running.values(), return_when=asyncio.FIRST_COMPLETED
            )
            finished_ids = [sid for sid, task in running.items() if task in done]
            for stage_id in finished_ids:
                task = running.pop(stage_id)
                self._results[stage_id] = task.result()

        report.results = [self._results[sid] for sid in order]
        report.finished_at = time.time()
        return report

    def _deps_complete(self, stage: Stage) -> bool:
        return all(dep in self._results for dep in stage.needs)

    def _skip_reason(self, stage: Stage) -> str | None:
        """If a required dependency failed, return why this stage is skipped."""
        for dep in stage.needs:
            result = self._results.get(dep)
            if result is None:
                continue
            if result.status in (StageStatus.SKIPPED,):
                return f"skipped: dependency '{dep}' was skipped"
            if result.status in (StageStatus.FAILED, StageStatus.ERROR):
                dep_stage = self._stage_map[dep]
                if not dep_stage.continue_on_error:
                    return (
                        f"skipped: required dependency '{dep}' "
                        f"{result.status.value}"
                    )
        return None

    def _build_context(self, stage: Stage) -> StageContext:
        """Resolve a stage's templated params into a ready-to-run context."""
        prior_outputs = {
            sid: result.outputs for sid, result in self._results.items()
        }
        template_context: dict[str, Any] = {
            "vars": dict(self.workflow.vars),
            "target": self.workflow.target,
            "stages": {sid: {"outputs": out} for sid, out in prior_outputs.items()},
        }
        resolved_params = render(stage.params, template_context)
        return StageContext(
            stage_id=stage.id,
            target=self.workflow.target,
            params=resolved_params,
            vars=dict(self.workflow.vars),
            prior_outputs=prior_outputs,
            output_dir=self.output_dir,
            dry_run=self.dry_run,
        )

    async def _run_stage(self, stage: Stage) -> StageResult:
        async with self._semaphore:
            started = time.time()
            adapter = adapters.get(stage.adapter)
            if adapter is None:  # pragma: no cover - validated earlier
                return StageResult(
                    stage_id=stage.id,
                    adapter=stage.adapter,
                    status=StageStatus.ERROR,
                    error=f"adapter '{stage.adapter}' not registered",
                    started_at=started,
                    finished_at=time.time(),
                )

            try:
                context = self._build_context(stage)
            except TemplateError as exc:
                return StageResult(
                    stage_id=stage.id,
                    adapter=stage.adapter,
                    status=StageStatus.ERROR,
                    error=f"template error: {exc}",
                    started_at=started,
                    finished_at=time.time(),
                )

            logger.info("running stage '%s' (adapter=%s)", stage.id, stage.adapter)
            try:
                coro = self._invoke(adapter, context)
                if stage.timeout is not None:
                    result = await asyncio.wait_for(coro, timeout=stage.timeout)
                else:
                    result = await coro
            except TimeoutError:
                result = StageResult(
                    stage_id=stage.id,
                    adapter=stage.adapter,
                    status=StageStatus.ERROR,
                    error=f"stage timed out after {stage.timeout}s",
                )
            except Exception as exc:  # noqa: BLE001 - convert any adapter crash to ERROR
                logger.exception("stage '%s' raised", stage.id)
                result = StageResult(
                    stage_id=stage.id,
                    adapter=stage.adapter,
                    status=StageStatus.ERROR,
                    error=f"{type(exc).__name__}: {exc}",
                )

            result.started_at = started
            result.finished_at = time.time()
            return result

    async def _invoke(self, adapter: Any, context: StageContext) -> StageResult:
        """Call an adapter's run, awaiting async ones and threading sync ones."""
        if inspect.iscoroutinefunction(adapter.run):
            return await adapter.run(context)
        return await asyncio.to_thread(adapter.run, context)
