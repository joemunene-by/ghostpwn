# Changelog

All notable changes to ghostpwn are documented in this file.

The format is based on Keep a Changelog, and this project adheres to semantic
versioning.

## [0.1.0] - 2026-06-20

### Added

- Initial release of the ghostpwn orchestration engine.
- Workflow model: YAML workflows with a target, shared variables, and a list of
  stages, each with an adapter, templated params, and `needs` dependencies.
- Dependency DAG with deterministic topological ordering, cycle detection, and
  layered parallel scheduling.
- Asyncio orchestrator with bounded concurrency, per-stage timeouts, data passing
  between stages, and a failure policy (`continue_on_error`, dependent skipping).
- Safe `${{ vars.x }}` / `${{ stages.id.outputs.x }}` templating with no eval or
  exec, just a restricted dictionary walk.
- Adapter interface plus a process-wide registry. Built-in adapters:
  - `mock`: deterministic, side-effect-free adapter for demos and tests.
  - `command`: run any external CLI safely (argument vector, no shell, timeout,
    optional JSON parsing) to wire in tools like nmap, ghostrecon, and ghostmap.
  - `http_probe`: real HTTP probe with security-header findings (httpx).
  - `dns_recon`: real DNS record resolution (dnspython).
- Consolidated reporting: rich console summary (per-stage status table and a
  findings rollup), JSON report, and persisted per-run artifacts.
- Typer CLI: `run`, `validate`, `graph`, `adapters`, `version`, with
  `--target`, `--var`, `--output`, `--format`, `--concurrency`, `--dry-run`.
- Example workflows under `examples/` and a fully offline test suite.
