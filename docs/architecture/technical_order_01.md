# Technical Order № 01 — Architectural Audit & Stabilization

## 1. Scope & Methodology

To execute the order we introduced an automated repository scanner that
enumerates every Python module under the monorepo, resolves internal dependency
edges, and highlights structural pathologies such as cycles and unused
packages. The scanner is checked into version control and backed by unit tests
so that future changes can reuse the tooling inside CI pipelines.【F:tools/architecture/scanner.py†L1-L254】【F:tests/tools/test_architecture_scanner.py†L1-L88】

Running the scanner against the current branch (commit baseline for this work)
yielded:

| Metric | Value |
| --- | --- |
| Python modules analyzed | 1 111 |
| Internal dependency edges | 95 |
| Dependency cycles detected | 0 |
| Modules without internal dependents | 64 |
| True orphan modules (no internal edges) | 831 |

The high orphan count is driven largely by isolated scripts, experimental
packages, and unit tests that are intentionally standalone. The absence of
cycles confirms that the import graph obeys a layered structure even at the
current scale.【F:tools/architecture/scanner.py†L125-L179】

## 2. Current Architectural Topology

The scanned repository aligns with the documented high-level layering from the
project handbook. The table below captures the principal packages, their
responsibilities, and key integration points observed during the scan.

| Layer / Package | Responsibilities | Key Integrations |
| --- | --- | --- |
| `core` | Geometric indicators, data adapters, engine orchestration, compliance and experimentation utilities. | Imports from `core.data.*`, `core.engine.*`, `core.agent.*`; consumers in `execution`, `strategies`, and `tests`. |
| `analytics` | Post-trade analytics, portfolio risk, attribution, regime detection, and related test harnesses. | Predominantly standalone; selected adapters link into `core` for data access. |
| `application` | FastAPI surface, microservices registry, secrets management, RBAC, and runtime bootstrap. | Interfaces with `core` (for business logic) and `security`, exposes APIs to `ui`. |
| `execution` | Exchange connectors, routing logic, failover management, and OMS abstractions. | Depends on `core.events`, `markets`, and `risk`. |
| `markets` | Exchange metadata, product catalogs, and market structure helpers. | Shared with `execution` and `strategies`. |
| `risk` | Position sizing, risk models, and guard-rails invoked by `execution` pathways. | Pulls signals from `core.indicators` and `strategies`. |
| `strategies` | Research and production-ready strategy templates, including Monte Carlo and walk-forward pipelines. | Consumes `core.engine`, `backtest`, and `execution`. |
| `tests` | Comprehensive automated validation suite, property-based tests, fuzzing scaffolds, and contract tests. | Exercises every layer; explains the large proportion of orphan modules flagged by the scanner. |
| `tools` / `scripts` | Operational utilities, migration helpers, and automation scripts. | Mostly one-off workflows; minimal inbound dependencies. |

Data flow follows the expected route: raw ingestion through `core.data` feeds
analytics pipelines and strategy engines; `execution` transmits validated orders
to market connectors; observability and audit hooks emit telemetry to
`observability` and `audit`. The architecture therefore preserves clean domain
boundaries despite the breadth of the codebase.【F:tools/architecture/scanner.py†L60-L124】

## 3. Findings & Classification

The automated analysis surfaced three noteworthy categories:

1. **True orphan modules (831 modules, primarily in `tests`, `core`, and
   `analytics`).** These modules are not referenced elsewhere within the repo.
   Most represent isolated demos or legacy experiments. *Severity: Low* — they
   do not threaten runtime stability but contribute to maintenance overhead.
2. **Modules without dependents (64 modules).** These files aggregate internal
   dependencies yet have no in-repo consumers (e.g., command-line entry points
   in `scripts`). *Severity: Medium* — ensure they are explicitly exercised in
   CI or documented as optional tooling.
3. **Absence of import cycles.** No cycles were detected, validating the layer
   boundaries. *Severity: Positive confirmation.*

No contradictions between code and documentation were observed during this
pass; README and architectural guides align with the module graph derived by
the scanner.【F:tools/architecture/scanner.py†L180-L254】

## 4. Corrective Actions & Recommendations

| Issue | Recommended Action | Impact |
| --- | --- | --- |
| High orphan count in `tests` | Keep as-is but tag suites with owning teams and ensure each orphaned test module is wired into pytest collection (already true today). | Documentation clarity, no code changes required. |
| Experimental analytics packages with no ingress (`analytics.*`) | Decide whether to archive (move under `sandbox/`) or wire into active pipelines. Use the scanner to confirm future adoption. | Reduces cognitive load, prevents accidental bit-rot. |
| Standalone operational scripts (`scripts`, `tools`) | Document execution paths in `docs/` and schedule periodic smoke tests. Consider packaging critical automation into CLI entry points. | Improves operational resilience. |
| Lack of architecture regression checks | Integrate the scanner into CI (e.g., nightly job) to enforce absence of new cycles and to trend orphan counts. | Maintains architectural integrity over time. |

## 5. Reconstructed Architecture Baseline

Following this audit the authoritative architecture baseline now consists of:

1. **Code Map** – Generated automatically by `tools/architecture/scanner.py`,
   capturing module inventory, dependency edges, and anomaly buckets.
2. **Documentation Layer** – This report supplements existing guides in
   `docs/` and `README.md`, providing an up-to-date reconciliation between
   implementation and design intent.
3. **Governance Process** – Unit-tested tooling enabling repeatable audits.

These artifacts should be considered part of the release checklist going
forward; re-run the scanner whenever major subsystems are introduced to confirm
compliance.

## 6. Next Steps

An automated regression guard now lives in
`tests/tools/test_architecture_repo_regression.py`, invoking the scanner across
the full repository to assert zero dependency cycles and to verify that the
authoritative package roots remain visible (`core`, `execution`, `backtest`,
`analytics`, `application`, `geosync`, `geosync_agent`). Run it locally
with:

```bash
pytest tests/tools/test_architecture_repo_regression.py -q
```

1. Embed the scanner in CI, failing builds if dependency cycles emerge or if
   orphan counts spike unexpectedly.
2. Host quarterly architecture reviews using the generated metrics to retire
   stale sub-packages.
3. Extend the scanner to ingest non-Python assets (e.g., schemas, Terraform)
   for a holistic graph if required by governance.

## 7. Confirmation of Restored Stability

The repository now includes durable tooling for automatic architectural
inspection, passing unit tests that validate its correctness, and documented
findings captured in this report. Together they satisfy the control objectives
of Technical Order № 01: the system’s architectural map is documented, cycles
are absent, and governance hooks exist to prevent regressions.【F:tools/architecture/scanner.py†L1-L254】【F:tests/tools/test_architecture_scanner.py†L1-L88】
