"""Adapter package: base interface, registry, and built-in adapters.

Importing this package registers every built-in adapter exactly once, so the
registry is populated as soon as ``ghostpwn.adapters`` is imported anywhere.
"""

from __future__ import annotations

from .base import Adapter, StageContext
from .command import CommandAdapter
from .dns_recon import DnsReconAdapter
from .http_probe import HttpProbeAdapter
from .mock import MockAdapter
from .registry import all_adapters, get, has, names, register

_BUILTINS = [
    MockAdapter(),
    CommandAdapter(),
    HttpProbeAdapter(),
    DnsReconAdapter(),
]


def _register_builtins() -> None:
    for adapter in _BUILTINS:
        if not has(adapter.name):
            register(adapter)


_register_builtins()

__all__ = [
    "Adapter",
    "StageContext",
    "CommandAdapter",
    "DnsReconAdapter",
    "HttpProbeAdapter",
    "MockAdapter",
    "register",
    "get",
    "has",
    "names",
    "all_adapters",
]
