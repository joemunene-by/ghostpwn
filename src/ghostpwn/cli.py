"""Typer command-line interface for ghostpwn.

Subcommands:
  - ``run``: validate and execute a workflow, then emit a consolidated report.
  - ``validate``: parse and semantically validate a workflow without running it.
  - ``graph``: print the resolved DAG and parallelizable execution layers.
  - ``adapters``: list every registered adapter.
  - ``version``: print the installed version.
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import __version__, adapters, report
from .errors import GhostpwnError
from .loader import apply_overrides, load_workflow, validate
from .orchestrator import Orchestrator

app = typer.Typer(
    add_completion=False,
    help="Automated penetration-test orchestration engine for authorized engagements.",
    no_args_is_help=True,
)
console = Console()
err_console = Console(stderr=True)


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _parse_vars(pairs: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise typer.BadParameter(f"--var must be key=value, got '{pair}'")
        key, value = pair.split("=", 1)
        key = key.strip()
        if not key:
            raise typer.BadParameter(f"--var key cannot be empty in '{pair}'")
        overrides[key] = value
    return overrides


def _load_and_validate(
    workflow_file: Path,
    target: str | None,
    var_pairs: list[str],
):
    workflow = load_workflow(workflow_file)
    apply_overrides(
        workflow, target=target, var_overrides=_parse_vars(var_pairs or [])
    )
    graph = validate(workflow)
    return workflow, graph


@app.command()
def run(
    workflow_file: Path = typer.Argument(..., help="Path to the workflow YAML file."),
    target: str | None = typer.Option(None, "--target", help="Override the target."),
    var: list[str] = typer.Option(
        [], "--var", help="Override a workflow var: key=value (repeatable)."
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Directory to persist run artifacts."
    ),
    output_format: str = typer.Option(
        "console", "--format", help="Output format: console or json."
    ),
    concurrency: int = typer.Option(
        4, "--concurrency", "-c", help="Max stages to run in parallel."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Resolve and schedule without invoking tools."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging."),
) -> None:
    """Run a workflow and print or persist its consolidated report."""
    _configure_logging(verbose)
    if output_format not in ("console", "json"):
        err_console.print("[red]--format must be 'console' or 'json'[/red]")
        raise typer.Exit(code=2)
    try:
        workflow, graph = _load_and_validate(workflow_file, target, var)
        orchestrator = Orchestrator(
            workflow,
            graph,
            concurrency=concurrency,
            output_dir=str(output) if output else None,
            dry_run=dry_run,
        )
        run_report = orchestrator.run()
    except GhostpwnError as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if output:
        path = report.persist(run_report, output)
        if output_format == "console":
            console.print(f"[dim]artifacts written to {path.parent}[/dim]")

    if output_format == "json":
        console.print_json(report.to_json(run_report))
    else:
        report.render_console(run_report, console)

    raise typer.Exit(code=0 if run_report.succeeded else 1)


@app.command(name="validate")
def validate_workflow(
    workflow_file: Path = typer.Argument(..., help="Path to the workflow YAML file."),
    target: str | None = typer.Option(None, "--target", help="Override the target."),
    var: list[str] = typer.Option([], "--var", help="Override a workflow var."),
) -> None:
    """Validate a workflow without running it."""
    try:
        workflow, _ = _load_and_validate(workflow_file, target, var)
    except GhostpwnError as exc:
        err_console.print(f"[red]invalid:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(
        f"[green]valid[/green] workflow '{workflow.name}' "
        f"with {len(workflow.stages)} stage(s)"
    )


@app.command()
def graph(
    workflow_file: Path = typer.Argument(..., help="Path to the workflow YAML file."),
    target: str | None = typer.Option(None, "--target", help="Override the target."),
    var: list[str] = typer.Option([], "--var", help="Override a workflow var."),
) -> None:
    """Print the resolved dependency graph and parallel execution layers."""
    try:
        workflow, dep_graph = _load_and_validate(workflow_file, target, var)
    except GhostpwnError as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    order = dep_graph.topological_order()
    layers = dep_graph.layers()

    console.print(f"[bold]workflow:[/bold] {workflow.name}")
    console.print(f"[bold]topological order:[/bold] {' -> '.join(order)}")
    console.print("[bold]execution layers (each layer runs in parallel):[/bold]")
    for index, layer in enumerate(layers):
        console.print(f"  layer {index}: {', '.join(layer)}")

    table = Table(title="stage dependencies")
    table.add_column("stage", style="bold")
    table.add_column("adapter")
    table.add_column("needs")
    for stage in workflow.stages:
        table.add_row(stage.id, stage.adapter, ", ".join(stage.needs) or "-")
    console.print(table)


@app.command(name="adapters")
def list_adapters() -> None:
    """List every registered adapter."""
    table = Table(title="registered adapters")
    table.add_column("name", style="bold")
    table.add_column("class")
    table.add_column("doc")
    for name, adapter in sorted(adapters.all_adapters().items()):
        doc = (adapter.__doc__ or "").strip().splitlines()
        summary = doc[0] if doc else ""
        table.add_row(name, type(adapter).__name__, summary)
    console.print(table)


@app.command()
def version() -> None:
    """Print the ghostpwn version."""
    console.print(f"ghostpwn {__version__}")


if __name__ == "__main__":  # pragma: no cover
    app()
