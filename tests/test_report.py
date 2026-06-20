"""Tests for consolidated reporting: JSON, console rendering, persistence."""

from __future__ import annotations

import json

from rich.console import Console

from conftest import make_workflow
from ghostpwn import report
from ghostpwn.graph import DependencyGraph
from ghostpwn.orchestrator import Orchestrator


def _run_report():
    wf = make_workflow(
        [
            {
                "id": "a",
                "adapter": "mock",
                "params": {"findings": [{"title": "f", "severity": "high"}]},
            },
            {"id": "b", "adapter": "mock", "needs": ["a"]},
        ],
        target="example.com",
    )
    return Orchestrator(wf, DependencyGraph(wf)).run()


def test_to_json_is_valid_and_complete():
    rep = _run_report()
    data = json.loads(report.to_json(rep))
    assert data["workflow"] == "test"
    assert data["target"] == "example.com"
    assert data["severity_counts"]["high"] == 1
    assert len(data["results"]) == 2


def test_render_console_does_not_crash():
    rep = _run_report()
    console = Console(record=True, width=120)
    report.render_console(rep, console)
    text = console.export_text()
    assert "Stage results" in text
    assert "Findings rollup" in text
    assert "PASS" in text


def test_persist_writes_artifacts(tmp_path):
    rep = _run_report()
    path = report.persist(rep, tmp_path)
    assert path.exists()
    assert path.name == "report.json"
    data = json.loads(path.read_text())
    assert data["workflow"] == "test"
    stage_files = list((tmp_path / "stages").glob("*.json"))
    assert {p.stem for p in stage_files} == {"a", "b"}
