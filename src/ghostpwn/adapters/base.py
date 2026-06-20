"""Adapter base class and execution context.

An adapter wraps one security tool or operation behind a uniform interface. The
orchestrator hands each adapter a :class:`StageContext` (resolved params plus the
target and outputs of prior stages) and expects a :class:`StageResult` back.

Adapters may implement ``run`` as either a synchronous or an ``async`` method.
The orchestrator detects which and dispatches appropriately, running synchronous
adapters in a worker thread so they never block the event loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import StageResult


@dataclass
class StageContext:
    """Everything an adapter needs to execute one stage."""

    stage_id: str
    target: str | None
    params: dict[str, Any] = field(default_factory=dict)
    vars: dict[str, Any] = field(default_factory=dict)
    # Resolved outputs of already-completed stages, keyed by stage id.
    prior_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    output_dir: str | None = None
    dry_run: bool = False

    def param(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)

    def require(self, key: str) -> Any:
        if key not in self.params:
            raise KeyError(f"missing required param '{key}'")
        return self.params[key]


class Adapter:
    """Base class for all adapters.

    Subclasses set ``name`` and implement ``run``. They may override
    ``validate_params`` to reject malformed configuration before a run begins.
    """

    #: Unique registry name, referenced from workflow YAML as ``adapter: <name>``.
    name: str = ""

    def validate_params(self, params: dict[str, Any]) -> None:
        """Validate static stage params. Override to enforce requirements.

        Raise :class:`ghostpwn.errors.AdapterError` to signal a configuration
        problem. The default implementation accepts any params.
        """

    def run(self, context: StageContext) -> StageResult:  # pragma: no cover - abstract
        raise NotImplementedError
