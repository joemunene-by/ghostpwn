"""DNS reconnaissance adapter built on dnspython.

A second real, non-mock built-in stage: it resolves a configurable set of record
types for a domain and returns the answers as structured outputs. Useful as an
early recon stage whose outputs (resolved addresses) later stages can template.
"""

from __future__ import annotations

from typing import Any

from ..errors import AdapterError
from ..models import Finding, Severity, StageResult, StageStatus
from .base import Adapter, StageContext

_DEFAULT_RECORDS = ["A", "AAAA", "MX", "NS", "TXT"]


class DnsReconAdapter(Adapter):
    """Resolve DNS records for a domain.

    Supported params:
      - ``domain`` (str): the domain to resolve. Falls back to the workflow
        target if omitted.
      - ``records`` (list[str]): record types to query (default A/AAAA/MX/NS/TXT).
      - ``timeout`` (float): per-query timeout in seconds (default 5).
    """

    name = "dns_recon"

    def validate_params(self, params: dict[str, Any]) -> None:
        records = params.get("records")
        if records is not None and not isinstance(records, list):
            raise AdapterError("dns_recon 'records' must be a list of record types")

    def run(self, context: StageContext) -> StageResult:
        params = context.params
        domain = params.get("domain") or context.target
        if not domain:
            return StageResult(
                stage_id=context.stage_id,
                adapter=self.name,
                status=StageStatus.ERROR,
                error="dns_recon requires a 'domain' param or a workflow target",
            )
        domain = str(domain).replace("https://", "").replace("http://", "").strip("/")
        records = params.get("records") or _DEFAULT_RECORDS
        timeout = float(params.get("timeout", 5))

        if context.dry_run:
            return StageResult(
                stage_id=context.stage_id,
                adapter=self.name,
                status=StageStatus.SUCCESS,
                outputs={"domain": domain, "records": records, "dry_run": True},
            )

        import dns.exception
        import dns.resolver

        resolver = dns.resolver.Resolver()
        resolver.lifetime = timeout
        resolver.timeout = timeout

        answers: dict[str, list[str]] = {}
        errors: dict[str, str] = {}
        addresses: list[str] = []
        for record_type in records:
            try:
                response = resolver.resolve(domain, record_type)
                values = [r.to_text() for r in response]
                answers[record_type] = values
                if record_type in ("A", "AAAA"):
                    addresses.extend(values)
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
                answers[record_type] = []
            except dns.exception.DNSException as exc:
                errors[record_type] = str(exc)

        findings: list[Finding] = []
        if not addresses:
            findings.append(
                Finding(
                    title=f"no address records resolved for {domain}",
                    severity=Severity.INFO,
                    description="neither A nor AAAA records were returned",
                    metadata={"domain": domain},
                )
            )

        outputs: dict[str, Any] = {
            "domain": domain,
            "records": answers,
            "addresses": addresses,
        }
        if errors:
            outputs["errors"] = errors

        return StageResult(
            stage_id=context.stage_id,
            adapter=self.name,
            status=StageStatus.SUCCESS,
            outputs=outputs,
            findings=findings,
        )
