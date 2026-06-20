"""Consolidated reporting: console rendering, JSON, and artifact persistence.

Turns a :class:`RunReport` into a rich console summary (per-stage status table
plus a findings rollup), a JSON document, and on-disk artifacts under an output
directory so a run is auditable after the fact.
"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import RunReport, Severity, StageStatus

_STATUS_STYLE = {
    StageStatus.SUCCESS: "green",
    StageStatus.FAILED: "red",
    StageStatus.ERROR: "red",
    StageStatus.SKIPPED: "yellow",
}

_SEVERITY_STYLE = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "red",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "cyan",
    Severity.INFO: "dim",
}


def to_json(report: RunReport, *, indent: int = 2) -> str:
    """Serialize the consolidated report to a JSON string."""
    return json.dumps(report.to_dict(), indent=indent, default=str)


def render_console(report: RunReport, console: Console | None = None) -> None:
    """Render the consolidated report to a rich console."""
    console = console or Console()

    header = f"ghostpwn run: {report.workflow}"
    if report.target:
        header += f"  target={report.target}"
    console.print(Panel(header, expand=False))

    stage_table = Table(title="Stage results", show_lines=False)
    stage_table.add_column("stage", style="bold")
    stage_table.add_column("adapter")
    stage_table.add_column("status")
    stage_table.add_column("duration", justify="right")
    stage_table.add_column("findings", justify="right")
    stage_table.add_column("detail")

    for result in report.results:
        style = _STATUS_STYLE.get(result.status, "white")
        duration = f"{result.duration:.2f}s" if result.duration is not None else "-"
        detail = result.error or ""
        stage_table.add_row(
            result.stage_id,
            result.adapter,
            f"[{style}]{result.status.value}[/{style}]",
            duration,
            str(len(result.findings)),
            detail,
        )
    console.print(stage_table)

    findings = sorted(
        report.all_findings, key=lambda f: f.severity.rank, reverse=True
    )
    if findings:
        findings_table = Table(title="Findings rollup")
        findings_table.add_column("severity")
        findings_table.add_column("title", style="bold")
        findings_table.add_column("description")
        for finding in findings:
            style = _SEVERITY_STYLE.get(finding.severity, "white")
            findings_table.add_row(
                f"[{style}]{finding.severity.value}[/{style}]",
                finding.title,
                finding.description,
            )
        console.print(findings_table)
    else:
        console.print("[dim]No findings reported.[/dim]")

    counts = report.status_counts()
    sev = report.severity_counts()
    summary = (
        f"stages: {counts['success']} ok, {counts['failed']} failed, "
        f"{counts['error']} error, {counts['skipped']} skipped  |  "
        f"findings: {sev['critical']} critical, {sev['high']} high, "
        f"{sev['medium']} medium, {sev['low']} low, {sev['info']} info"
    )
    overall = "PASS" if report.succeeded else "FAIL"
    overall_style = "green" if report.succeeded else "red"
    console.print(
        Panel(
            f"[{overall_style}]{overall}[/{overall_style}]  {summary}",
            expand=False,
        )
    )


def persist(report: RunReport, output_dir: str | Path) -> Path:
    """Write the JSON report and per-stage artifacts under ``output_dir``.

    Returns the path to the written ``report.json``.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "report.json"
    report_path.write_text(to_json(report), encoding="utf-8")

    stages_dir = out / "stages"
    stages_dir.mkdir(exist_ok=True)
    for result in report.results:
        stage_path = stages_dir / f"{result.stage_id}.json"
        stage_path.write_text(
            json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8"
        )
    return report_path
