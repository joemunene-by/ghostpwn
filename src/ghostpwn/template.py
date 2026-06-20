"""Safe template substitution for stage parameters.

Stage params may reference workflow variables and prior-stage outputs using a
restricted ``${{ ... }}`` syntax, for example::

    ${{ vars.target }}
    ${{ stages.recon.outputs.hosts }}
    ${{ target }}

Resolution is a pure dictionary walk: there is no ``eval``, ``exec``, attribute
access, or arbitrary expression evaluation. Only dotted key paths into the
provided context are supported, plus integer indices for list access. Unknown
references raise :class:`TemplateError` so typos fail loudly instead of silently
producing empty strings.
"""

from __future__ import annotations

import re
from typing import Any

from .errors import TemplateError

# Matches ${{ some.path.here }} with arbitrary surrounding whitespace.
_PATTERN = re.compile(r"\$\{\{\s*(?P<expr>[^}]+?)\s*\}\}")

# A path component is a bare identifier or a non-negative integer index.
_PATH_PART = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$|^[0-9]+$")


def _resolve_path(expr: str, context: dict[str, Any]) -> Any:
    """Walk a dotted ``expr`` into ``context`` and return the referenced value."""
    parts = expr.split(".")
    current: Any = context
    walked: list[str] = []
    for part in parts:
        part = part.strip()
        if not part or not _PATH_PART.match(part):
            raise TemplateError(
                f"invalid template reference '{expr}': bad path component '{part}'"
            )
        walked.append(part)
        if isinstance(current, dict):
            if part not in current:
                trail = ".".join(walked)
                raise TemplateError(
                    f"unknown template reference '{expr}': '{trail}' not found"
                )
            current = current[part]
        elif isinstance(current, (list, tuple)):
            if not part.isdigit():
                raise TemplateError(
                    f"invalid template reference '{expr}': '{part}' is not a list index"
                )
            index = int(part)
            if index >= len(current):
                raise TemplateError(
                    f"unknown template reference '{expr}': index {index} out of range"
                )
            current = current[index]
        else:
            trail = ".".join(walked[:-1])
            raise TemplateError(
                f"unknown template reference '{expr}': '{trail}' is not indexable"
            )
    return current


def render_string(value: str, context: dict[str, Any]) -> Any:
    """Render a single string.

    If the whole string is exactly one template expression, the resolved value is
    returned with its native type preserved (so a list output stays a list). When
    the expression is embedded in surrounding text, the resolved value is coerced
    to ``str`` and interpolated.
    """
    full = _PATTERN.fullmatch(value.strip())
    if full:
        return _resolve_path(full.group("expr"), context)

    def _replace(match: re.Match[str]) -> str:
        resolved = _resolve_path(match.group("expr"), context)
        return str(resolved)

    return _PATTERN.sub(_replace, value)


def render(value: Any, context: dict[str, Any]) -> Any:
    """Recursively render templates inside strings, dicts, and lists."""
    if isinstance(value, str):
        return render_string(value, context)
    if isinstance(value, dict):
        return {key: render(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [render(item, context) for item in value]
    return value
