"""Adapter registry.

Holds a process-wide mapping of adapter name to adapter instance. Built-in
adapters register themselves on import; third-party code can register additional
adapters via :func:`register`. Workflows resolve ``adapter: <name>`` through
:func:`get`.
"""

from __future__ import annotations

from .base import Adapter

_REGISTRY: dict[str, Adapter] = {}


def register(adapter: Adapter, *, replace: bool = False) -> Adapter:
    """Register an adapter instance under its ``name``."""
    if not adapter.name:
        raise ValueError("adapter must define a non-empty name")
    if adapter.name in _REGISTRY and not replace:
        raise ValueError(f"adapter '{adapter.name}' already registered")
    _REGISTRY[adapter.name] = adapter
    return adapter


def get(name: str) -> Adapter | None:
    """Return the registered adapter for ``name``, or None."""
    return _REGISTRY.get(name)


def has(name: str) -> bool:
    return name in _REGISTRY


def names() -> list[str]:
    """Return all registered adapter names, sorted."""
    return sorted(_REGISTRY)


def all_adapters() -> dict[str, Adapter]:
    return dict(_REGISTRY)
