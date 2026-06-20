"""Tests for the adapter registry and built-in adapter offline behaviour."""

from __future__ import annotations

import pytest

from ghostpwn import adapters
from ghostpwn.adapters import registry
from ghostpwn.adapters.base import Adapter, StageContext
from ghostpwn.adapters.dns_recon import DnsReconAdapter
from ghostpwn.adapters.http_probe import HttpProbeAdapter
from ghostpwn.adapters.mock import MockAdapter
from ghostpwn.models import StageStatus


def test_builtins_registered():
    names = adapters.names()
    assert {"mock", "command", "http_probe", "dns_recon"} <= set(names)


def test_get_returns_instance():
    assert isinstance(adapters.get("mock"), MockAdapter)
    assert adapters.get("nope") is None


def test_register_rejects_duplicate():
    with pytest.raises(ValueError):
        registry.register(MockAdapter())


def test_register_requires_name():
    class Nameless(Adapter):
        pass

    with pytest.raises(ValueError):
        registry.register(Nameless())


def test_mock_adapter_deterministic():
    ctx = StageContext(stage_id="s", target="t", params={"outputs": {"k": "v"}})
    r1 = MockAdapter().run(ctx)
    r2 = MockAdapter().run(ctx)
    assert r1.outputs == r2.outputs
    assert r1.outputs["k"] == "v"
    assert r1.status == StageStatus.SUCCESS


def test_http_probe_requires_url_or_target():
    ctx = StageContext(stage_id="s", target=None, params={})
    result = HttpProbeAdapter().run(ctx)
    assert result.status == StageStatus.ERROR


def test_http_probe_dry_run_no_network():
    ctx = StageContext(
        stage_id="s", target="example.com", params={}, dry_run=True
    )
    result = HttpProbeAdapter().run(ctx)
    assert result.status == StageStatus.SUCCESS
    assert result.outputs["dry_run"] is True


def test_dns_recon_requires_domain_or_target():
    ctx = StageContext(stage_id="s", target=None, params={})
    result = DnsReconAdapter().run(ctx)
    assert result.status == StageStatus.ERROR


def test_dns_recon_dry_run_no_network():
    ctx = StageContext(
        stage_id="s", target="example.com", params={}, dry_run=True
    )
    result = DnsReconAdapter().run(ctx)
    assert result.status == StageStatus.SUCCESS
    assert result.outputs["dry_run"] is True
    assert result.outputs["domain"] == "example.com"
