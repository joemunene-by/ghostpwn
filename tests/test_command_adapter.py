"""Tests for the command adapter: capture, JSON parsing, timeout, no injection."""

from __future__ import annotations

import sys

import pytest

from ghostpwn.adapters.base import StageContext
from ghostpwn.adapters.command import CommandAdapter
from ghostpwn.errors import AdapterError
from ghostpwn.models import StageStatus


def _ctx(params, **kwargs):
    return StageContext(stage_id="cmd", target=None, params=params, **kwargs)


def test_runs_command_and_captures_stdout():
    adapter = CommandAdapter()
    result = adapter.run(
        _ctx({"cmd": sys.executable, "args": ["-c", "print('hello world')"]})
    )
    assert result.status == StageStatus.SUCCESS
    assert result.outputs["returncode"] == 0
    assert "hello world" in result.outputs["stdout"]


def test_parses_json_output():
    adapter = CommandAdapter()
    result = adapter.run(
        _ctx(
            {
                "cmd": sys.executable,
                "args": ["-c", "import json; print(json.dumps({'ok': True, 'n': 3}))"],
                "parse_json": True,
            }
        )
    )
    assert result.outputs["json"] == {"ok": True, "n": 3}


def test_nonzero_exit_is_failure_by_default():
    adapter = CommandAdapter()
    result = adapter.run(
        _ctx({"cmd": sys.executable, "args": ["-c", "import sys; sys.exit(2)"]})
    )
    assert result.status == StageStatus.FAILED
    assert result.outputs["returncode"] == 2


def test_allow_nonzero_keeps_success():
    adapter = CommandAdapter()
    result = adapter.run(
        _ctx(
            {
                "cmd": sys.executable,
                "args": ["-c", "import sys; sys.exit(2)"],
                "allow_nonzero": True,
            }
        )
    )
    assert result.status == StageStatus.SUCCESS


def test_timeout_marks_error():
    adapter = CommandAdapter()
    result = adapter.run(
        _ctx(
            {
                "cmd": sys.executable,
                "args": ["-c", "import time; time.sleep(5)"],
                "timeout": 0.3,
            }
        )
    )
    assert result.status == StageStatus.ERROR
    assert "timed out" in (result.error or "")


def test_missing_executable_is_error():
    adapter = CommandAdapter()
    result = adapter.run(_ctx({"cmd": "this_binary_does_not_exist_ghostpwn"}))
    assert result.status == StageStatus.ERROR
    assert "not found" in (result.error or "")


def test_no_shell_injection_surface():
    # The arg is a literal string passed in the argv vector, never interpreted by
    # a shell, so this prints the metacharacters verbatim instead of executing.
    adapter = CommandAdapter()
    payload = "; echo INJECTED"
    result = adapter.run(
        _ctx({"cmd": sys.executable, "args": ["-c", "import sys; print(sys.argv[1])", payload]})
    )
    assert "INJECTED" in result.outputs["stdout"]
    # No second command ran: stdout is exactly the payload echoed once.
    assert result.outputs["stdout"].strip() == payload


def test_validate_params_requires_cmd():
    adapter = CommandAdapter()
    with pytest.raises(AdapterError):
        adapter.validate_params({"args": ["x"]})


def test_dry_run_does_not_execute():
    adapter = CommandAdapter()
    result = adapter.run(
        _ctx({"cmd": sys.executable, "args": ["-c", "print('x')"]}, dry_run=True)
    )
    assert result.status == StageStatus.SUCCESS
    assert result.outputs["dry_run"] is True
    assert "stdout" not in result.outputs
