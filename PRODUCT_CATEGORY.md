<!-- Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab) -->
<!-- SPDX-License-Identifier: MIT -->

# Product Category — Single Claim-Boundary

> **Canonical, machine-enforced statement of what GeoSync *is* and *is not*.**
> Enforced by `scripts/ci/check_claim_boundary.py` over every document on the
> canonical surface (top-level `*.md` + `docs/`). This file, `README.md`,
> `CLAIMS.md`, and `FORBIDDEN_CLAIMS.md` are the only authorities for product
> positioning; all other docs MUST conform.

## What GeoSync is

**GeoSync is a verification-first quantitative research platform for falsifiable
market-structure hypotheses.** Every claim is admissible only when bound to an
explicit invariant, a data contract, a falsifier, and a reproducible artifact,
and is promoted no further than its declared evidence tier (`CLAIMS.md`).

## What GeoSync is NOT

| Not a… | Because |
| --- | --- |
| **live-trading product / system** | The repository ships an *execution-realism harness* (paper / replay) used to study fill, slippage, and latency realism. It is research instrumentation, not a promise of live-venue trading. |
| **alpha engine / signal product** | Geometric and phase-synchrony observables are studied as *market-microstructure descriptors*. No out-of-sample edge is asserted; promotion beyond `INSTRUMENTED` requires a real-data artifact with hashes, seed, and null-baseline result. |
| **investment advice** | Outputs are research observables, never recommendations to buy, sell, or allocate capital. |
| **proof of a market "law"** | Mechanisms are sourced from peer-reviewed literature and tested as hypotheses; the platform proves *invariants of its own computation*, not laws of markets. |

## Mechanism is not a claim

The boundary forbids product-level *promises*, not the existence of subsystems.
GeoSync legitimately contains an order-management system, a `Signal` dataclass,
a `/v1/signals` endpoint, `live/` execution-mode configs, and operational
runbooks. These are **mechanism** — internal substrate described in engineering
docs — and are recorded as reviewed exceptions in
[`.github/claim_boundary_allow.json`](.github/claim_boundary_allow.json), each
with a stated reason (mechanism / ops-runbook / research-disclaimer /
honest-negation). New, unreviewed product-category phrasing on the canonical
surface fails CI.

## Enforcement

```bash
python scripts/ci/check_claim_boundary.py   # 0 = boundary held, 1 = drift
```

Wired into [`.github/workflows/claim-boundary-gate.yml`](.github/workflows/claim-boundary-gate.yml)
and mirrored by `tests/scripts/test_check_claim_boundary.py`. Status wording is
additionally firewalled by [`FORBIDDEN_CLAIMS.md`](FORBIDDEN_CLAIMS.md).
