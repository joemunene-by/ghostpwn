"""Generic external-command adapter.

Runs an arbitrary CLI as an argument vector (never via a shell), captures stdout
and stderr, enforces a timeout, and optionally parses JSON output. This is the
seam for wiring real tools (nmap, ghostrecon, ghostmap, and similar) into a
workflow with no code changes: point a stage at ``adapter: command`` and supply
``cmd`` plus ``args``.

Security note: the command is always executed with ``shell=False`` against an
explicit argument list, so there is no shell-injection surface. Inputs are still
templated from workflow vars and prior outputs, so operators remain responsible
for only running this against authorized targets.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from ..errors import AdapterError
from ..models import Finding, Severity, StageResult, StageStatus
from .base import Adapter, StageContext


class CommandAdapter(Adapter):
    """Run an external command safely and capture its result.

    Supported params:
      - ``cmd`` (str, required): the executable to run.
      - ``args`` (list[str | int | float]): argument vector, no shell expansion.
      - ``timeout`` (float): seconds before the process is killed (default 60).
      - ``parse_json`` (bool): if true, parse stdout as JSON into ``json`` output.
      - ``allow_nonzero`` (bool): if true, a nonzero exit is still SUCCESS.
      - ``env`` (dict[str, str]): extra environment variables.
      - ``cwd`` (str): working directory for the process.
    """

    name = "command"

    def validate_params(self, params: dict[str, Any]) -> None:
        if not params.get("cmd"):
            raise AdapterError("command adapter requires a 'cmd' param")
        args = params.get("args", [])
        if args is not None and not isinstance(args, list):
            raise AdapterError("command adapter 'args' must be a list")

    def run(self, context: StageContext) -> StageResult:
        params = context.params
        cmd = params["cmd"]
        args = [str(a) for a in (params.get("args") or [])]
        argv = [str(cmd), *args]
        timeout = float(params.get("timeout", 60))
        parse_json = bool(params.get("parse_json", False))
        allow_nonzero = bool(params.get("allow_nonzero", False))
        env = params.get("env")
        cwd = params.get("cwd")

        if context.dry_run:
            return StageResult(
                stage_id=context.stage_id,
                adapter=self.name,
                status=StageStatus.SUCCESS,
                outputs={"command": argv, "dry_run": True},
            )

        if shutil.which(str(cmd)) is None and "/" not in str(cmd):
            return StageResult(
                stage_id=context.stage_id,
                adapter=self.name,
                status=StageStatus.ERROR,
                outputs={"command": argv},
                error=f"executable '{cmd}' not found on PATH",
            )

        run_env = None
        if env:
            import os

            run_env = {**os.environ, **{str(k): str(v) for k, v in env.items()}}

        try:
            completed = subprocess.run(  # noqa: S603 - argv list, shell=False, no injection
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=run_env,
                cwd=cwd,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return StageResult(
                stage_id=context.stage_id,
                adapter=self.name,
                status=StageStatus.ERROR,
                outputs={"command": argv},
                error=f"command timed out after {timeout}s",
                findings=[
                    Finding(
                        title=f"command timed out: {cmd}",
                        severity=Severity.LOW,
                        description=str(exc),
                    )
                ],
            )
        except (OSError, ValueError) as exc:
            return StageResult(
                stage_id=context.stage_id,
                adapter=self.name,
                status=StageStatus.ERROR,
                outputs={"command": argv},
                error=f"failed to launch command: {exc}",
            )

        outputs: dict[str, Any] = {
            "command": argv,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

        if parse_json and completed.stdout.strip():
            try:
                outputs["json"] = json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                outputs["json_error"] = str(exc)

        ok = completed.returncode == 0 or allow_nonzero
        status = StageStatus.SUCCESS if ok else StageStatus.FAILED
        error = None if ok else f"command exited with code {completed.returncode}"
        return StageResult(
            stage_id=context.stage_id,
            adapter=self.name,
            status=status,
            outputs=outputs,
            error=error,
        )
