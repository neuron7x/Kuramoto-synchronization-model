# SEMANTIC RISK MAP — Kuramoto coupling (Stream 1)

Scope of this pilot: the **coupling representation** path of the core Kuramoto
engine. One real, currently-unguarded semantic failure was found and closed.

## Confirmed failure: coupling scale can enter the dynamics twice

The Kuramoto RHS summed by the engine is `dθ_i/dt = ω_i + Σ_j C_ij·sin(θ_j−θ_i)`.

`core/kuramoto/engine.py::_resolve_adjacency` builds `C` from `KuramotoConfig`:

| Branch                      | Effective `C`        | Normalization |
|-----------------------------|----------------------|---------------|
| `adjacency is None` (global)| `C_ij = K / N`       | divided by N  |
| `adjacency is not None`     | `C_ij = K · A_ij`    | **none**      |

`core/kuramoto/config.py` documents the second branch as `C = K·A` but **nothing
enforces what `A` means**. Two distinct, silent defects follow:

1. **Convention inconsistency.** The same all-to-all topology yields different
   dynamics depending on the branch: global gives per-edge `K/N`; an all-ones
   `adjacency` gives per-edge `K`, i.e. an N× stronger coupling. The scale is
   not invariant across representations.

2. **Double-scaling (primary).** `core/kuramoto/coupling_estimator.py` emits a
   full physical weight matrix `W` (the `CouplingMatrix.K` field — itself
   confusingly named). If `W` is passed as `adjacency` while the scalar
   `KuramotoConfig.K` is left at any non-unit value, the engine computes
   `C = K · W` — the coupling strength is applied **twice**. The trajectory is
   plausible, the existing tests stay green, and the reported coupling is wrong.

This violates the CLAUDE.md / Stream-1 first principle **"coupling appears
exactly once"** and risks promoting a mis-scaled descriptor into a physical
synchronization claim (INV-K2/K3 critical-coupling reasoning assumes the
reported `K` is the real one).

## Remediation (this PR)

`core/kuramoto/coupling_spec.py` — `CouplingSpec`, a Layer-A object owning the
representation:

* explicit `CouplingMode` (global-K-with-normalized-A / full-weight-W /
  signed / repulsive) — the convention is part of the model, not a comment;
* **anti-double-scaling guard**: full-weight modes (`W`) require `K == 1.0`,
  fail-closed;
* **sign discipline**: negative `K` only in `REPULSIVE_OR_SIGNED_MODE`; negative
  weights only in signed modes;
* **claim boundary**: signed/repulsive couplings return `CLAIM_SIGNED` and can
  never advertise `CLAIM_ATTRACTIVE` — the attractive synchronization theorems
  are gated off once repulsion is present;
* `effective_matrix()` applies the scale exactly once and zeroes the diagonal;
* `KuramotoConfig.from_coupling_spec()` pins `K=1.0` and stores the effective
  matrix, so the engine's `K·adjacency` reproduces `C` with no second scaling.

## Out of scope (not touched — see NEGATIVE_EVIDENCE.md)

Streams 2–8 (attractive/signed regime split beyond coupling, Ricci sign
preservation, phase provenance, multiscale relabeling, weighted Forman split,
second-order stability audit, higher-order representation). The existing
`phase_extractor.py` already uses analytic-signal (Hilbert) phase with Q1–Q4
gates, so the order's premise of an `arctan2(std, mean)` proxy is **stale** for
this repository — no such proxy exists in `core/`.
