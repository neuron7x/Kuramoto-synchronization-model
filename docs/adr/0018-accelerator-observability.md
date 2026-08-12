# ADR-0018 · Accelerator Observability: From Exception to Contract

* **Status**: Accepted
* **Date**: 2026-04-19
* **Deciders**: neuron7xLab
* **Supersedes**: —
* **Superseded by**: —
* **Related**: PR #322 (strict-backend hardening), PR #325 (telemetry), PR #326 (master class)

## Context

The Sprint-1 hardening landed in [PR #322](https://github.com/neuron7xLab/GeoSync/pull/322) introduced ``strict_backend`` and ``BackendSynchronizationError`` as the *mechanism* for fail-closed accelerator dispatch. What it did **not** ship was the *contract* around that mechanism:

* the exception carried only a free-text message;
* downgrades in fail-open mode were silent (a ``WARNING`` log, drowned in production noise);
* ``strict_backend=True`` was per-call opt-in, with no process-wide switch;
* no invariant linked the strict and default code paths.

Each of these is a failure mode waiting to happen. An operator reading a production alert that says "Rust sliding_windows failed with strict_backend=True" cannot tell:

* which backend,
* why — build broken, data corrupt, env missing NumPy?
* how many times this happened before,
* when the last healthy dispatch ran.

The exception, in other words, **did not answer the questions an operator actually asks**.

## Decision

Elevate accelerator observability from mechanism to contract by shipping four elements **as one coherent release** rather than drip-fed:

1. **Structured exception payload.** ``BackendSynchronizationError`` carries ``backend``, ``reason``, ``last_healthy_epoch_ns``, ``downgrade_count`` fields and a ``to_dict()`` method for audit-ledger serialisation.
2. **Downgrade counter.** A module-level, thread-safe ``Counter[(from, to, reason)]`` plus ``downgrade_counts()`` / ``reset_downgrade_counter()`` surface. Silent degradation is no longer silent; any scraper (Prometheus exporter, cron job) can read the delta without a new dependency.
3. **Process-wide strict-backend default.** ``GEOSYNC_STRICT_BACKEND=1`` in the environment flips ``strict_backend`` from opt-in to default-on without touching call sites. Production deployments adopt fail-closed with a single env line; dev stays on fail-open.
4. **BackendHealth span.** A context-manager-based observability scope that records ``(wall_duration_s, downgrade_delta, last_healthy_per_backend)`` for the enclosed block. Returns a frozen ``BackendHealthReport`` with ``to_dict()``. Two spans can nest without contaminating each other.

## Consequences

### Positive

* An operator reading a ``BackendSynchronizationError`` trace can answer every triage question without grepping the application log.
* Downgrade counts become dashboardable — the team sees the trend, not only the spike.
* Production deployments can flip to fail-closed *without* a code change.
* ``BackendHealth`` turns a batch pipeline's accelerator behaviour into a first-class audit record, reusable across tools (replay comparison, SLO reporting, forensic analysis).
* Every future Tier-3 feature (strict-zone registry, zero-downgrade CI budget) is a one-liner on top of this foundation.

### Negative

* Telemetry adds a tiny per-call lock (microsecond overhead). The accelerator path is already allocation-heavy, so the cost is lost in the noise, but the lock is technically a new contention point.
* ``strict_backend: bool | None = None`` broadens the keyword's type from ``bool``. Any type annotation depending on the old signature must be updated. Call sites passing ``bool`` literal values are unchanged.

### Neutral

* The exception remains a ``RuntimeError`` subclass. Legacy except-handlers that caught the bare class continue to work.
* Downgrades are counted; whether any downgrade is acceptable is a *policy* decision deferred to Tier-3 (zero-downgrade CI budget on release-gate runs).

## Implementation

Landed in PR #326 as one commit sequence:

| File | Nature |
|------|--------|
| ``core/accelerators/numeric.py`` | ``BackendSynchronizationError`` extended, ``BackendHealth`` context manager added, env flag honoured |
| ``tests/unit/test_accelerator_telemetry.py`` | Tier-1 parity + payload + counter (PR #325 carry-over) |
| ``tests/unit/test_accelerator_masterclass.py`` | Env flag contract + ``BackendHealth`` span contract |
| ``docs/accelerator_observability.md`` | Architectural story, Mermaid diagram, before/after |
| ``docs/adr/0018-accelerator-observability.md`` | This document |

## Rollback

Environment flag:
* Unset ``GEOSYNC_STRICT_BACKEND`` → strict_backend default returns to ``False``; every caller reverts to fail-open without code changes.
* A full revert of the commit restores the pre-masterclass state; the ``BackendSynchronizationError`` defaults keep legacy constructors working throughout.

## Tracking

* Tier-3 strict-zone registry → separate ADR when that PR lands.
* Zero-downgrade CI budget → separate workflow + ADR.
* Release provenance → separate PR under ``docs/security/``.
