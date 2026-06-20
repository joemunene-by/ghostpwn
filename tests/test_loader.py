"""Tests for workflow loading and validation errors."""

from __future__ import annotations

import pytest

from conftest import make_workflow
from ghostpwn.errors import (
    CycleError,
    MissingDependencyError,
    UnknownAdapterError,
    ValidationError,
    WorkflowError,
)
from ghostpwn.loader import (
    apply_overrides,
    load_workflow,
    parse_workflow,
    validate,
)


def test_parse_minimal_workflow():
    wf = parse_workflow(
        {"name": "x", "stages": [{"id": "a", "adapter": "mock"}]}
    )
    assert wf.name == "x"
    assert wf.stages[0].id == "a"


def test_missing_name_raises():
    with pytest.raises(WorkflowError):
        parse_workflow({"stages": [{"id": "a", "adapter": "mock"}]})


def test_missing_stages_raises():
    with pytest.raises(WorkflowError):
        parse_workflow({"name": "x"})


def test_stage_missing_adapter_raises():
    with pytest.raises(WorkflowError):
        parse_workflow({"name": "x", "stages": [{"id": "a"}]})


def test_duplicate_stage_id_raises():
    with pytest.raises(WorkflowError):
        parse_workflow(
            {
                "name": "x",
                "stages": [
                    {"id": "a", "adapter": "mock"},
                    {"id": "a", "adapter": "mock"},
                ],
            }
        )


def test_needs_string_is_normalized_to_list():
    wf = parse_workflow(
        {
            "name": "x",
            "stages": [
                {"id": "a", "adapter": "mock"},
                {"id": "b", "adapter": "mock", "needs": "a"},
            ],
        }
    )
    assert wf.stages[1].needs == ["a"]


def test_unknown_adapter_raises():
    wf = make_workflow([{"id": "a", "adapter": "does_not_exist"}])
    with pytest.raises(UnknownAdapterError):
        validate(wf)


def test_missing_dependency_raises():
    wf = make_workflow([{"id": "a", "adapter": "mock", "needs": ["ghost"]}])
    with pytest.raises(MissingDependencyError):
        validate(wf)


def test_cycle_raises():
    wf = make_workflow(
        [
            {"id": "a", "adapter": "mock", "needs": ["b"]},
            {"id": "b", "adapter": "mock", "needs": ["a"]},
        ]
    )
    with pytest.raises(CycleError):
        validate(wf)


def test_bad_command_params_raise_validation_error():
    # command adapter with no cmd and no template ref fails validation up front.
    wf = make_workflow([{"id": "a", "adapter": "command", "params": {"args": ["x"]}}])
    with pytest.raises(ValidationError):
        validate(wf)


def test_templated_params_skip_static_validation():
    # cmd is templated, so static param validation is deferred to run time.
    wf = make_workflow(
        [{"id": "a", "adapter": "command", "params": {"cmd": "${{ vars.bin }}"}}],
        vars={"bin": "echo"},
    )
    validate(wf)  # must not raise


def test_apply_overrides_sets_target_and_vars():
    wf = make_workflow([{"id": "a", "adapter": "mock"}], vars={"k": "v"})
    apply_overrides(wf, target="new.example", var_overrides={"k": "v2", "extra": "1"})
    assert wf.target == "new.example"
    assert wf.vars["k"] == "v2"
    assert wf.vars["extra"] == "1"


def test_apply_overrides_rejects_reserved_key():
    wf = make_workflow([{"id": "a", "adapter": "mock"}])
    with pytest.raises(WorkflowError):
        apply_overrides(wf, var_overrides={"target": "x"})


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(WorkflowError):
        load_workflow(tmp_path / "nope.yaml")


def test_load_examples(examples_dir):
    for name in ("mock_recon.yaml", "web_assessment.yaml", "ghost_tools.yaml"):
        wf = load_workflow(examples_dir / name)
        validate(wf)
        assert wf.stages
