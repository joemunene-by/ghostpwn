"""Shared pytest fixtures and helpers for the ghostpwn test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostpwn.loader import parse_workflow
from ghostpwn.models import Workflow

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def make_workflow(stages: list[dict], *, name: str = "test", target: str | None = None,
                  vars: dict | None = None) -> Workflow:
    """Build a Workflow from a list of stage dicts via the real parser."""
    return parse_workflow(
        {
            "name": name,
            "target": target,
            "vars": vars or {},
            "stages": stages,
        }
    )


@pytest.fixture
def examples_dir() -> Path:
    return EXAMPLES_DIR
