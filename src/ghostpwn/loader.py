"""Workflow loading, parsing, and validation.

Turns a YAML document into a validated :class:`Workflow`. Validation is split in
two phases:

  1. Structural parsing (this module): the document is a mapping with the
     expected keys and types; each stage has an id and adapter; ids are unique.
  2. Semantic validation (:func:`validate`): every adapter is registered, every
     ``needs`` references a real stage, the dependency graph is acyclic, and each
     adapter accepts its static params.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from . import adapters
from .errors import UnknownAdapterError, ValidationError, WorkflowError
from .graph import DependencyGraph
from .models import Stage, Workflow

_RESERVED_VAR_KEYS = {"target"}


def parse_workflow(data: dict[str, Any]) -> Workflow:
    """Build a :class:`Workflow` from an already-loaded mapping."""
    if not isinstance(data, dict):
        raise WorkflowError("workflow root must be a mapping")

    name = data.get("name")
    if not name or not isinstance(name, str):
        raise WorkflowError("workflow requires a string 'name'")

    target = data.get("target")
    if target is not None and not isinstance(target, str):
        raise WorkflowError("workflow 'target' must be a string")

    raw_vars = data.get("vars", {}) or {}
    if not isinstance(raw_vars, dict):
        raise WorkflowError("workflow 'vars' must be a mapping")

    raw_stages = data.get("stages")
    if not raw_stages or not isinstance(raw_stages, list):
        raise WorkflowError("workflow requires a non-empty 'stages' list")

    stages: list[Stage] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_stages):
        if not isinstance(raw, dict):
            raise WorkflowError(f"stage #{index} must be a mapping")
        stage_id = raw.get("id")
        if not stage_id or not isinstance(stage_id, str):
            raise WorkflowError(f"stage #{index} requires a string 'id'")
        if stage_id in seen_ids:
            raise WorkflowError(f"duplicate stage id '{stage_id}'")
        seen_ids.add(stage_id)

        adapter = raw.get("adapter")
        if not adapter or not isinstance(adapter, str):
            raise WorkflowError(f"stage '{stage_id}' requires a string 'adapter'")

        params = raw.get("params", {}) or {}
        if not isinstance(params, dict):
            raise WorkflowError(f"stage '{stage_id}' 'params' must be a mapping")

        needs = raw.get("needs", []) or []
        if isinstance(needs, str):
            needs = [needs]
        if not isinstance(needs, list) or not all(isinstance(n, str) for n in needs):
            raise WorkflowError(
                f"stage '{stage_id}' 'needs' must be a string or list of strings"
            )

        timeout = raw.get("timeout")
        if timeout is not None:
            try:
                timeout = float(timeout)
            except (TypeError, ValueError) as exc:
                raise WorkflowError(
                    f"stage '{stage_id}' 'timeout' must be a number"
                ) from exc

        stages.append(
            Stage(
                id=stage_id,
                adapter=adapter,
                params=params,
                needs=list(needs),
                continue_on_error=bool(raw.get("continue_on_error", False)),
                timeout=timeout,
                description=str(raw.get("description", "")),
            )
        )

    return Workflow(name=name, target=target, vars=dict(raw_vars), stages=stages)


def load_workflow(path: str | Path) -> Workflow:
    """Load and parse a workflow YAML file from disk."""
    file_path = Path(path)
    if not file_path.is_file():
        raise WorkflowError(f"workflow file not found: {file_path}")
    try:
        data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise WorkflowError(f"failed to parse YAML in {file_path}: {exc}") from exc
    return parse_workflow(data)


def apply_overrides(
    workflow: Workflow,
    *,
    target: str | None = None,
    var_overrides: dict[str, Any] | None = None,
) -> Workflow:
    """Return a workflow with CLI-supplied target and var overrides applied."""
    if target is not None:
        workflow.target = target
    if var_overrides:
        for key, value in var_overrides.items():
            if key in _RESERVED_VAR_KEYS:
                raise WorkflowError(f"'{key}' is reserved and cannot be a var override")
            workflow.vars[key] = value
    return workflow


def validate(workflow: Workflow) -> DependencyGraph:
    """Run full semantic validation, returning the built dependency graph.

    Raises a :class:`ValidationError` subclass on the first problem found:
    unknown adapter, missing dependency, cycle, or bad adapter params.
    """
    for stage in workflow.stages:
        adapter = adapters.get(stage.adapter)
        if adapter is None:
            available = ", ".join(adapters.names())
            raise UnknownAdapterError(
                f"stage '{stage.id}' uses unknown adapter '{stage.adapter}'. "
                f"available adapters: {available}"
            )

    # Building the graph validates `needs` references and detects cycles.
    graph = DependencyGraph(workflow)
    graph.layers()

    # Validate static (non-templated) params per adapter where possible. Params
    # containing template references are skipped here and resolved at run time.
    for stage in workflow.stages:
        adapter = adapters.get(stage.adapter)
        assert adapter is not None  # guaranteed above
        if _has_template(stage.params):
            continue
        try:
            adapter.validate_params(stage.params)
        except ValidationError:
            raise
        except Exception as exc:  # AdapterError and friends
            raise ValidationError(f"stage '{stage.id}': {exc}") from exc

    return graph


def _has_template(value: Any) -> bool:
    if isinstance(value, str):
        return "${{" in value
    if isinstance(value, dict):
        return any(_has_template(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_template(v) for v in value)
    return False
