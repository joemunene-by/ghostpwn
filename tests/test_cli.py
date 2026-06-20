"""CLI tests via Typer's test runner against the example workflows."""

from __future__ import annotations

from typer.testing import CliRunner

from conftest import EXAMPLES_DIR
from ghostpwn.cli import app

runner = CliRunner()
MOCK_WF = str(EXAMPLES_DIR / "mock_recon.yaml")


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "ghostpwn" in result.stdout


def test_adapters_lists_builtins():
    result = runner.invoke(app, ["adapters"])
    assert result.exit_code == 0
    for name in ("mock", "command", "http_probe", "dns_recon"):
        assert name in result.stdout


def test_validate_ok():
    result = runner.invoke(app, ["validate", MOCK_WF])
    assert result.exit_code == 0
    assert "valid" in result.stdout


def test_graph_prints_order_and_layers():
    result = runner.invoke(app, ["graph", MOCK_WF])
    assert result.exit_code == 0
    assert "topological order" in result.stdout
    assert "layer" in result.stdout


def test_run_mock_workflow_console():
    result = runner.invoke(app, ["run", MOCK_WF])
    assert result.exit_code == 0
    assert "PASS" in result.stdout
    assert "Stage results" in result.stdout


def test_run_json_format():
    result = runner.invoke(app, ["run", MOCK_WF, "--format", "json"])
    assert result.exit_code == 0
    assert '"workflow"' in result.stdout
    assert "mock-recon-demo" in result.stdout


def test_run_persists_output(tmp_path):
    out = tmp_path / "run1"
    result = runner.invoke(app, ["run", MOCK_WF, "--output", str(out)])
    assert result.exit_code == 0
    assert (out / "report.json").exists()


def test_run_with_var_override():
    result = runner.invoke(app, ["run", MOCK_WF, "--var", "scope=custom-scope"])
    assert result.exit_code == 0


def test_run_dry_run():
    result = runner.invoke(app, ["run", MOCK_WF, "--dry-run"])
    assert result.exit_code == 0


def test_run_invalid_workflow_exits_nonzero(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: x\nstages:\n  - id: a\n    adapter: nope\n")
    result = runner.invoke(app, ["run", str(bad)])
    assert result.exit_code == 1


def test_bad_var_format_rejected():
    result = runner.invoke(app, ["run", MOCK_WF, "--var", "noequals"])
    assert result.exit_code != 0
