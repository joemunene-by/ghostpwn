"""Dependency graph construction, cycle detection, and topological ordering.

The orchestrator schedules stages by their ``needs`` edges. This module turns a
workflow into a directed acyclic graph, validates that every dependency exists,
rejects cycles with a clear message, and produces both a flat topological order
and a layered order (groups of stages that may run in parallel).
"""

from __future__ import annotations

from .errors import CycleError, MissingDependencyError
from .models import Workflow


class DependencyGraph:
    """A directed dependency graph over stage ids built from a workflow."""

    def __init__(self, workflow: Workflow) -> None:
        self.workflow = workflow
        self.nodes: list[str] = workflow.stage_ids()
        self._node_set = set(self.nodes)
        # edges[node] = set of ids that `node` depends on (must run first).
        self.edges: dict[str, set[str]] = {}
        self._build()

    def _build(self) -> None:
        if len(self.nodes) != len(self._node_set):
            seen: set[str] = set()
            for node in self.nodes:
                if node in seen:
                    raise MissingDependencyError(f"duplicate stage id '{node}'")
                seen.add(node)
        for stage in self.workflow.stages:
            deps = set(stage.needs)
            for dep in deps:
                if dep == stage.id:
                    raise MissingDependencyError(
                        f"stage '{stage.id}' cannot depend on itself"
                    )
                if dep not in self._node_set:
                    raise MissingDependencyError(
                        f"stage '{stage.id}' needs unknown stage '{dep}'"
                    )
            self.edges[stage.id] = deps

    def dependents(self, node: str) -> list[str]:
        """Return ids that depend (directly) on ``node``."""
        return [n for n in self.nodes if node in self.edges.get(n, set())]

    def topological_order(self) -> list[str]:
        """Return a flat topological ordering, raising on cycles.

        Uses Kahn's algorithm. Ties are broken by the stage's declaration order so
        the ordering is deterministic across runs.
        """
        indegree: dict[str, int] = {n: len(self.edges[n]) for n in self.nodes}
        position = {n: i for i, n in enumerate(self.nodes)}
        ready = sorted((n for n in self.nodes if indegree[n] == 0), key=position.get)
        order: list[str] = []
        while ready:
            node = ready.pop(0)
            order.append(node)
            for dependent in self.dependents(node):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    ready.append(dependent)
                    ready.sort(key=position.get)
        if len(order) != len(self.nodes):
            remaining = [n for n in self.nodes if n not in set(order)]
            raise CycleError(
                "dependency cycle detected among stages: " + ", ".join(sorted(remaining))
            )
        return order

    def layers(self) -> list[list[str]]:
        """Return stages grouped into parallelizable layers.

        Each layer contains stages whose dependencies are all satisfied by earlier
        layers; stages within a layer have no ordering constraints between them and
        may execute concurrently. Validates acyclicity as a side effect.
        """
        # Force cycle detection up front for a clean error.
        self.topological_order()
        position = {n: i for i, n in enumerate(self.nodes)}
        remaining = set(self.nodes)
        done: set[str] = set()
        result: list[list[str]] = []
        while remaining:
            layer = sorted(
                (n for n in remaining if self.edges[n] <= done),
                key=position.get,
            )
            if not layer:
                raise CycleError(
                    "dependency cycle detected among stages: "
                    + ", ".join(sorted(remaining))
                )
            result.append(layer)
            done.update(layer)
            remaining.difference_update(layer)
        return result
