"""Exception hierarchy for ghostpwn.

All errors raised by the engine derive from GhostpwnError so callers can catch a
single base type. Each subclass maps to a distinct failure class surfaced by the
CLI and validation layers with clear, actionable messages.
"""

from __future__ import annotations


class GhostpwnError(Exception):
    """Base class for every error raised by ghostpwn."""


class WorkflowError(GhostpwnError):
    """A workflow file is malformed or semantically invalid."""


class ValidationError(WorkflowError):
    """A workflow failed schema or reference validation."""


class UnknownAdapterError(ValidationError):
    """A stage references an adapter that is not registered."""


class MissingDependencyError(ValidationError):
    """A stage `needs` an id that does not exist in the workflow."""


class CycleError(ValidationError):
    """The stage dependency graph contains a cycle."""


class TemplateError(GhostpwnError):
    """A `${{ ... }}` template reference could not be resolved."""


class AdapterError(GhostpwnError):
    """An adapter failed to validate its parameters."""
