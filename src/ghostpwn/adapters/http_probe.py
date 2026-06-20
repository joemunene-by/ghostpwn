"""HTTP probing adapter built on httpx.

A real, non-mock built-in stage: it issues an HTTP request to a URL (or to the
workflow target), records the status code, final URL after redirects, and a
curated set of response headers, then raises findings for missing common
security headers. This makes ghostpwn useful out of the box against an
authorized web target without any external binaries.
"""

from __future__ import annotations

from typing import Any

from ..errors import AdapterError
from ..models import Finding, Severity, StageResult, StageStatus
from .base import Adapter, StageContext

# Headers whose absence is worth flagging on an authorized assessment.
_SECURITY_HEADERS = {
    "strict-transport-security": Severity.MEDIUM,
    "content-security-policy": Severity.MEDIUM,
    "x-frame-options": Severity.LOW,
    "x-content-type-options": Severity.LOW,
    "referrer-policy": Severity.INFO,
}


class HttpProbeAdapter(Adapter):
    """Probe an HTTP endpoint and assess basic security headers.

    Supported params:
      - ``url`` (str): target URL. Falls back to the workflow target if omitted.
      - ``method`` (str): HTTP method (default GET).
      - ``timeout`` (float): request timeout in seconds (default 10).
      - ``follow_redirects`` (bool): follow redirects (default true).
      - ``verify`` (bool): verify TLS certificates (default true).
    """

    name = "http_probe"

    def validate_params(self, params: dict[str, Any]) -> None:
        method = params.get("method")
        if method is not None and not isinstance(method, str):
            raise AdapterError("http_probe 'method' must be a string")

    def run(self, context: StageContext) -> StageResult:
        params = context.params
        url = params.get("url") or context.target
        if not url:
            return StageResult(
                stage_id=context.stage_id,
                adapter=self.name,
                status=StageStatus.ERROR,
                error="http_probe requires a 'url' param or a workflow target",
            )
        if not str(url).startswith(("http://", "https://")):
            url = f"https://{url}"

        method = str(params.get("method", "GET")).upper()
        timeout = float(params.get("timeout", 10))
        follow = bool(params.get("follow_redirects", True))
        verify = bool(params.get("verify", True))

        if context.dry_run:
            return StageResult(
                stage_id=context.stage_id,
                adapter=self.name,
                status=StageStatus.SUCCESS,
                outputs={"url": url, "method": method, "dry_run": True},
            )

        import httpx

        try:
            with httpx.Client(
                follow_redirects=follow, verify=verify, timeout=timeout
            ) as client:
                response = client.request(method, url)
        except httpx.HTTPError as exc:
            return StageResult(
                stage_id=context.stage_id,
                adapter=self.name,
                status=StageStatus.ERROR,
                outputs={"url": url, "method": method},
                error=f"request failed: {exc}",
            )

        headers = {k.lower(): v for k, v in response.headers.items()}
        outputs: dict[str, Any] = {
            "url": url,
            "final_url": str(response.url),
            "status_code": response.status_code,
            "method": method,
            "server": headers.get("server", ""),
            "content_type": headers.get("content-type", ""),
            "headers": headers,
        }

        findings: list[Finding] = []
        is_https = str(response.url).startswith("https://")
        for header, severity in _SECURITY_HEADERS.items():
            if header == "strict-transport-security" and not is_https:
                continue
            if header not in headers:
                findings.append(
                    Finding(
                        title=f"missing security header: {header}",
                        severity=severity,
                        description=(
                            f"response from {response.url} did not set the "
                            f"'{header}' header"
                        ),
                        metadata={"header": header, "url": str(response.url)},
                    )
                )

        return StageResult(
            stage_id=context.stage_id,
            adapter=self.name,
            status=StageStatus.SUCCESS,
            outputs=outputs,
            findings=findings,
        )
