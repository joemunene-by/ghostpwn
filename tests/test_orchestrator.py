"""End-to-end orchestrator tests using the deterministic mock adapter."""

from __future__ import annotations

import time

from conftest import make_workflow
from ghostpwn.graph import DependencyGraph
from ghostpwn.models import StageStatus
from ghostpwn.orchestrator import Orchestrator


def _run(stages, *, concurrency=4, target=None, vars=None):
    wf = make_workflow(stages, target=target, vars=vars)
    graph = DependencyGraph(wf)
    return Orchestrator(wf, graph, concurrency=concurrency).run()


def test_multi_stage_run_succeeds():
    report = _run(
        [
            {"id": "a", "adapter": "mock", "params": {"outputs": {"x": 1}}},
            {"id": "b", "adapter": "mock", "needs": ["a"]},
        ]
    )
    assert report.succeeded
    assert {r.stage_id for r in report.results} == {"a", "b"}
    assert all(r.status == StageStatus.SUCCESS for r in report.results)


def test_data_passes_between_stages():
    report = _run(
        [
            {
                "id": "discover",
                "adapter": "mock",
                "params": {"outputs": {"hosts": ["h1", "h2"]}},
            },
            {
                "id": "use",
                "adapter": "mock",
                "needs": ["discover"],
                "params": {
                    "echo": "${{ stages.discover.outputs.hosts }}",
                    "outputs": {"first": "${{ stages.discover.outputs.hosts.0 }}"},
                },
            },
        ]
    )
    use = next(r for r in report.results if r.stage_id == "use")
    assert use.outputs["echo"] == ["h1", "h2"]
    assert use.outputs["first"] == "h1"


def test_findings_are_aggregated():
    report = _run(
        [
            {
                "id": "a",
                "adapter": "mock",
                "params": {
                    "findings": [
                        {"title": "f1", "severity": "high"},
                        {"title": "f2", "severity": "low"},
                    ]
                },
            }
        ]
    )
    assert len(report.all_findings) == 2
    assert report.severity_counts()["high"] == 1
    assert report.severity_counts()["low"] == 1


def test_independent_stages_run_in_parallel():
    # Two 0.25s sleeping stages with no deps should finish in well under 0.5s
    # when concurrency allows them to overlap.
    start = time.time()
    report = _run(
        [
            {"id": "a", "adapter": "mock", "params": {"sleep": 0.25}},
            {"id": "b", "adapter": "mock", "params": {"sleep": 0.25}},
        ],
        concurrency=2,
    )
    elapsed = time.time() - start
    assert report.succeeded
    assert elapsed < 0.45, f"stages did not overlap, took {elapsed:.2f}s"


def test_concurrency_one_serializes():
    start = time.time()
    _run(
        [
            {"id": "a", "adapter": "mock", "params": {"sleep": 0.2}},
            {"id": "b", "adapter": "mock", "params": {"sleep": 0.2}},
        ],
        concurrency=1,
    )
    elapsed = time.time() - start
    assert elapsed >= 0.4, f"expected serialized run, took {elapsed:.2f}s"


def test_failed_required_stage_skips_dependents():
    report = _run(
        [
            {"id": "a", "adapter": "mock", "params": {"fail": True}},
            {"id": "b", "adapter": "mock", "needs": ["a"]},
            {"id": "c", "adapter": "mock", "needs": ["b"]},
        ]
    )
    by_id = {r.stage_id: r for r in report.results}
    assert by_id["a"].status == StageStatus.FAILED
    assert by_id["b"].status == StageStatus.SKIPPED
    assert by_id["c"].status == StageStatus.SKIPPED
    assert not report.succeeded


def test_continue_on_error_lets_dependents_run():
    report = _run(
        [
            {
                "id": "a",
                "adapter": "mock",
                "continue_on_error": True,
                "params": {"fail": True},
            },
            {"id": "b", "adapter": "mock", "needs": ["a"]},
        ]
    )
    by_id = {r.stage_id: r for r in report.results}
    assert by_id["a"].status == StageStatus.FAILED
    assert by_id["b"].status == StageStatus.SUCCESS


def test_independent_stage_runs_despite_other_failure():
    report = _run(
        [
            {"id": "a", "adapter": "mock", "params": {"fail": True}},
            {"id": "x", "adapter": "mock"},
        ]
    )
    by_id = {r.stage_id: r for r in report.results}
    assert by_id["a"].status == StageStatus.FAILED
    assert by_id["x"].status == StageStatus.SUCCESS


def test_stage_timeout_marks_error():
    report = _run(
        [{"id": "slow", "adapter": "mock", "params": {"sleep": 1.0}, "timeout": 0.1}]
    )
    slow = report.results[0]
    assert slow.status == StageStatus.ERROR
    assert "timed out" in (slow.error or "")


def test_target_threaded_into_outputs():
    report = _run([{"id": "a", "adapter": "mock"}], target="example.com")
    assert report.target == "example.com"
    assert report.results[0].outputs["target"] == "example.com"


def test_report_serializes_to_dict():
    report = _run([{"id": "a", "adapter": "mock"}])
    data = report.to_dict()
    assert data["workflow"] == "test"
    assert data["succeeded"] is True
    assert isinstance(data["results"], list)
