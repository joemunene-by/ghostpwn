"""Tests for safe templating: resolution, type preservation, no code execution."""

from __future__ import annotations

import pytest

from ghostpwn.errors import TemplateError
from ghostpwn.template import render, render_string


@pytest.fixture
def context() -> dict:
    return {
        "vars": {"scope": "in-scope", "ports": 1000},
        "target": "example.com",
        "stages": {
            "discover": {"outputs": {"hosts": ["10.0.0.5", "10.0.0.6"], "count": 2}},
        },
    }


def test_resolves_var(context):
    assert render_string("${{ vars.scope }}", context) == "in-scope"


def test_resolves_target(context):
    assert render_string("${{ target }}", context) == "example.com"


def test_resolves_prior_stage_output(context):
    assert render_string("${{ stages.discover.outputs.count }}", context) == 2


def test_whole_expression_preserves_type(context):
    result = render_string("${{ stages.discover.outputs.hosts }}", context)
    assert result == ["10.0.0.5", "10.0.0.6"]
    assert isinstance(result, list)


def test_embedded_expression_coerces_to_string(context):
    result = render_string("scanning ${{ target }} with ${{ vars.ports }} ports", context)
    assert result == "scanning example.com with 1000 ports"


def test_list_index_access(context):
    assert render_string("${{ stages.discover.outputs.hosts.0 }}", context) == "10.0.0.5"


def test_unknown_var_raises(context):
    with pytest.raises(TemplateError):
        render_string("${{ vars.missing }}", context)


def test_unknown_stage_raises(context):
    with pytest.raises(TemplateError):
        render_string("${{ stages.nope.outputs.x }}", context)


def test_index_out_of_range_raises(context):
    with pytest.raises(TemplateError):
        render_string("${{ stages.discover.outputs.hosts.9 }}", context)


def test_no_code_execution(context):
    # An attempt at an expression is treated as a (failing) path lookup, never run.
    with pytest.raises(TemplateError):
        render_string("${{ __import__('os').system('echo pwned') }}", context)


def test_render_recurses_dicts_and_lists(context):
    template = {
        "url": "https://${{ target }}",
        "hosts": "${{ stages.discover.outputs.hosts }}",
        "nested": [{"k": "${{ vars.scope }}"}],
    }
    result = render(template, context)
    assert result["url"] == "https://example.com"
    assert result["hosts"] == ["10.0.0.5", "10.0.0.6"]
    assert result["nested"][0]["k"] == "in-scope"


def test_non_string_values_pass_through(context):
    assert render(42, context) == 42
    assert render(True, context) is True
    assert render(None, context) is None
