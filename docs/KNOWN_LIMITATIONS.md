# Known Limitations

This document is the honest counterweight to the README badges. Every claim
in the codebase that would benefit from a caveat lives here so that external
reviewers, auditors, and future contributors can calibrate their
expectations without hunting through source files.

## Scope and discipline

* Every limitation listed here is **declared before it is felt** — no one
  should discover these by surprise from production.
* When a limitation is closed, the corresponding bullet is removed **and**
  the fix is linked from the [changelog](../CHANGELOG.md) or the relevant
  ADR under [`docs/adr/`](adr/).
* `BASELINE.md` at the repo root is the quantitative companion — if a
  limitation is measurable, its number belongs there.

## L-1 · Execution surface is paper-trading only

The execution layer (`execution/`) ships smart routing, Kelly / MV sizing,
compliance checks, and a full order-lifecycle ledger, but the venues it
talks to in-repo are **paper connectors**. No credential in the public
source tree connects to a live exchange. Production deployment requires:

1. A private venue-credentials bundle that is *not* committed.
2. A staged rollout against a paper account first, reproducing the same
   order trace with `pytest tests/integration/` green.
3. An operator signing off on `runtime/kill_switch` defaults for that
   specific venue.

The README describes execution as a production-ready fabric. That is true
for the *platform*; it is **not** a live trading track record.

## L-2 · Strategy catalogue is intentionally thin

`strategies/` contains two first-party strategies (`neuro_geosync`,
`quantum_neural`) and a registry. The platform is capable of hosting
many more; the catalogue is deliberately thin because most strategies
the author researches live outside this repository.

Do **not** extrapolate platform maturity from strategy count. Treat the
two shipped strategies as reference implementations, not a catalogue.

## L-3 · Single performance record lives in `L2_ROBUSTNESS.json`

The one number referenced by the README — "Deflated Sharpe DSR = 15.1,
Pr(real) = 1.0" — lives in the `L2_ROBUSTNESS.json` artefact produced by
the L2 demo gate. It is **not** an annualised trading Sharpe on real
capital. Other Sharpe-like numbers scattered across docs (`docs/HPC_AI_V4.md`,
`docs/automated_risk_testing.md`, `docs/operations/PRODUCT_PAIN_SOLUTION.md`)
are illustrative values from their respective subsystems and are not
consolidated into a single performance ledger yet.

When a canonical live-performance ledger exists, it will live at
[`docs/PERFORMANCE_LEDGER.md`](PERFORMANCE_LEDGER.md) and this limitation
will close. Until then, **assume no live-capital track record**.

## L-4 · Dual Python tree (`core/` + `src/geosync/`)

The repository carries two parallel Python packages:

* `core/` — the legacy tree, predates the canonical layout.
* `src/geosync/` — the retired fork (see [ADR 0024](adr/0024-import-architecture-canonicalization.md)); top-level `geosync/` is now the canonical tree where new code must land.

For a long-lived migration, every module in `core/` should have a
thin shim that re-exports from `src/geosync/core/...` (see
`core/compat.py` for the reference pattern). Anywhere this shim is
absent, the duplication is a real risk of divergence under concurrent
edits. [ADR-0017](adr/0017-core-to-src-migration.md) captures the
migration plan and the acceptance criteria for retiring `core/`.

Until the migration closes, new code:

* imports from `geosync.core...` (canonical path);
* if legacy `core.X` must be touched, a shim is mandatory before any
  change is merged.

## L-5 · Bus factor = 1

The repository is authored by a single person with bot assistance
(dependabot, review bots). Independent review and outside contributors
are welcome and required for production use beyond the author's own
deployment. Until that external review layer is visible in the git
history, the bus factor is 1 and must be treated as such in any
risk / compliance analysis.

## L-6 · Organisational history before Sprint-0

Top-level layout before 2026-04 carried legacy subtrees (`legacy/`,
`handoff/`, `patches/`, `scope/`, `archive/`) that accumulated over
earlier iterations. After the grace window elapsed and verification
confirmed no production paths imported from them, the `archive/`,
`backlog/`, `stakeholders/` and `money_proof/` top-level trees were
removed as part of the repo-hygiene tier-1 cleanup. Git history
preserves their contents for any historical reference.

## L-7 · Frontend integration surface is undeclared (IERD Phase 0)

The repository ships a quantitative-trading kernel and a research
workbench. It does not currently ship a unified public HTTP API
surface that an external frontend can integrate against:

* No single OpenAPI 3.1 specification covers all exposed endpoints.
* No versioned routing scheme (`/v{N}/`) is enforced repository-wide.
* No standard error envelope (`{error_code, message, details, trace_id, recoverable}`) is enforced across services.
* Long-running computations are not exposed under a unified
  `job_id + status + WebSocket/SSE` async pattern.

This is registered in [`docs/CLAIMS.yaml`](CLAIMS.yaml) as the
`api-contract-openapi-coverage` entry with tier `UNKNOWN`. It is
re-classified to `ANCHORED` on Phase-3 entry of the IERD adoption
plan ([ADR 0020](adr/0020-ierd-adoption.md)). External-audit tracking:
`docs/yana-response.md` Q4.

## L-8 · UX state contracts not declared (IERD Phase 0)

Endpoints today do not declare the six required UX states (`success`,
`empty`, `partial`, `validation_error`, `server_error`, `timeout`)
nor a frontend rendering for each. UX Readiness Score (UXRS) is
therefore not computable at Phase 0.

Tracked under `ux-readiness-state-coverage` (tier `UNKNOWN`).
Re-classified on Phase-4 entry of the IERD adoption plan.

## L-9 · End-to-end latency budget instrumented only at server layer

Server-side latency is measured under `bench/`, `benchmarks/`, and
`loadtests/` with HPC kernel determinism guards. The client_render
(Web Vitals / Lighthouse), network_TTFB, and db_io layers are not
covered by repository-level regression-gated CI. End-to-end latency
budget compliance (FCP, TTFB, server p95, interactive p95) is
therefore `UNKNOWN`.

Tracked under `e2e-latency-budget-compliance` (tier `UNKNOWN`).
Re-classified on Phase-4 entry of the IERD adoption plan.

## L-10 · UX-level edge cases not in a tracked matrix

Kernel-level edge cases (NaN/Inf input, constant input, rank-deficient
input, divergent simulation) are tested heavily — see `INV-DRO5`,
`INV-HPC2`, `INV-FE2`, etc. UX-level edge cases (empty result set,
partial result, server timeout, network failure, validation error,
simulation divergence presented to a human) are not covered by a
formal `(endpoint × state × test_id)` matrix.

Tracked under `edge-case-coverage-matrix` (tier `UNKNOWN`).
Re-classified on Phase-4 entry of the IERD adoption plan.

## L-11 · No independent replication of physics-kernel attest results

The PAI = 1.00 and FPS_audit = 1.00 metrics, the 67-invariant
registry in `CLAUDE.md`, the `tests/unit/physics/test_T*.py`
suite, and the cross-asset Kuramoto walk-forward bundle frozen
under `results/cross_asset_kuramoto/PARAMETER_LOCK.json` (with
`_spike_commit` sha-256 lock) **have not been replicated by an
external party**. The artefact integrity of the bundle is anchored
by the sha-256 lock; the *result* (Sharpe, fold count, robust=True)
has been verified only by the original author.

By scientific method this means:

* the gate is closed against silent file tampering,
* the gate is **not** closed against single-author confirmation bias,
* an independent replicator running `pytest tests/unit/physics/`
  on a clean clone with the documented seed (42) **should**
  reproduce the same numerical results, but **has not**.

This is the institutional companion to L-5 (bus factor = 1):
discipline applied by one author cannot substitute for cross-author
replication. Closure path: Phase-1 entry per [ADR 0021](adr/0021-falsifier-required-anchored-claims.md)
includes the option for a third party to attest the falsifier
fingerprint of every ANCHORED claim, breaking the closed loop.

## L-12 · Reset-wave numerical model is single-process synchronous

The four numerical invariants of `geosync.neuroeconomics.reset_wave_engine`
(see `docs/reset_wave_validation_report.md` and the
`reset-wave-phase-synchronization` claim in `docs/CLAIMS.yaml`) hold
**only under ideal computational conditions**: single-process,
synchronous input, no clock skew, no dropped updates, no concurrent
writers.

In real distributed asynchronous environments — financial market data
feeds, IoT meshes, multi-process simulators — the following failure
modes break the potential-non-increase guarantee:

1. Clock-jitter on update arrival (`V` can spike before the next damped step).
2. Dropped or out-of-order updates (silent drift between θ_t and θ_baseline).
3. Partial node failure (a subset of nodes is silently stale).
4. Re-entry after failure (recovered node injects an old phase).
5. Concurrent writers (two callers interleave updates and step).

`geosync.neuroeconomics.reset_wave_distributed` adds five fail-closed
guards (`JitterEnvelope`, `StalenessGate`, `ConcurrencyGuard`,
`PartialFailureDetector`, `DiscontinuityMonitor`) that **refuse to
compute** when an async failure mode is detected; this is documented
under the `reset-wave-distributed-resilience` claim with tier
`EXTRAPOLATED`.

What the resilience adapter does **NOT** provide:

* CAP-theorem-level distributed consensus,
* distributed clock synchronisation (no NTP / PTP integration),
* automatic recovery from a failed node — the operator-side response
  is still required.

The adapter turns silent divergence into an explicit safety lock with
`fail_reason`. It does not turn a partitioned async network into a
synchronous one. Closure path: a future Phase-2 ADR will integrate
with an existing distributed runtime (e.g. the GeoSync `runtime/`
deterministic scheduler) to lift the EXTRAPOLATED tier to ANCHORED
once the integration test surface exists.

---

If you find a limitation of the platform that is not listed here, that
is itself a limitation. File it, even as a paragraph, before relying
on the affected surface in production.
