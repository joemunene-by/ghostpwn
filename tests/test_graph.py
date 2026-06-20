"""Tests for the dependency graph: ordering, cycles, and missing deps."""

from __future__ import annotations

import pytest

from conftest import make_workflow
from ghostpwn.errors import CycleError, MissingDependencyError
from ghostpwn.graph import DependencyGraph


def _stage(stage_id: str, needs: list[str] | None = None) -> dict:
    return {"id": stage_id, "adapter": "mock", "needs": needs or []}


def test_topological_order_respects_needs():
    wf = make_workflow(
        [
            _stage("c", ["a", "b"]),
            _stage("a"),
            _stage("b", ["a"]),
        ]
    )
    order = DependencyGraph(wf).topological_order()
    assert order.index("a") < order.index("b")
    assert order.index("b") < order.index("c")
    assert order.index("a") < order.index("c")


def test_topological_order_is_deterministic():
    wf = make_workflow([_stage("a"), _stage("b"), _stage("c")])
    graph = DependencyGraph(wf)
    assert graph.topological_order() == ["a", "b", "c"]
    # Stable across repeated calls.
    assert graph.topological_order() == graph.topological_order()


def test_layers_group_parallel_stages():
    wf = make_workflow(
        [
            _stage("root"),
            _stage("left", ["root"]),
            _stage("right", ["root"]),
            _stage("join", ["left", "right"]),
        ]
    )
    layers = DependencyGraph(wf).layers()
    assert layers[0] == ["root"]
    assert set(layers[1]) == {"left", "right"}
    assert layers[2] == ["join"]


def test_cycle_detection_raises():
    wf = make_workflow(
        [
            _stage("a", ["c"]),
            _stage("b", ["a"]),
            _stage("c", ["b"]),
        ]
    )
    graph = DependencyGraph(wf)
    with pytest.raises(CycleError):
        graph.topological_order()
    with pytest.raises(CycleError):
        graph.layers()


def test_missing_dependency_raises():
    wf = make_workflow([_stage("a", ["does_not_exist"])])
    with pytest.raises(MissingDependencyError):
        DependencyGraph(wf)


def test_self_dependency_raises():
    wf = make_workflow([_stage("a", ["a"])])
    with pytest.raises(MissingDependencyError):
        DependencyGraph(wf)


def test_dependents_lookup():
    wf = make_workflow([_stage("a"), _stage("b", ["a"]), _stage("c", ["a"])])
    graph = DependencyGraph(wf)
    assert set(graph.dependents("a")) == {"b", "c"}
    assert graph.dependents("b") == []
