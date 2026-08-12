# RESULTS — CALIB-GRID-001 (sha-pinned NEGATIVE artifact)

> **Verdict: `NEGATIVE`.** This is the informative outcome of an
> external-ground-truth calibration, **not** a defect of the artifact.
> No promotion language is used: the WSCC-9 grid coupling is *not*
> recovered by the current estimator, and the miss is localized below.
>
> Source ledger: `RESULTS.json`
> (`ledger_sha256 = ed8d409b7b222eb0…`, branch sha
> `d170d48afa5066c13edeb40b2c1904b3fd708516`, Python 3.12.3).
> Reproduce:
> `PYTHONPATH=. python -m research.calibration.grid_kuramoto.run --system wscc9`.

## Numeric verdict per gate (tier: MEASURED on a known ground truth)

| Gate | Metric | Observed | Threshold | Pass |
|---|---|---|---|---|
| `noiseless.frobenius` | `‖K̂−K‖_F/‖K‖_F` | **1.0459** | ≤ 0.10 | ❌ |
| `noiseless.topology_f1` | edge-support F1 | **1.0000** | ≥ 0.95 | ✅ |
| `noiseless.critical_coupling` | rel. err. vs Dörfler–Bullo | **1.0000** | ≤ 0.15 | ❌ |
| `noisy.frobenius` (σ=0.02) | `‖K̂−K‖_F/‖K‖_F` | **0.9901** | ≤ 0.25 | ❌ |
| `noisy.topology_f1` (σ=0.02) | edge-support F1 | **0.8000** | ≥ 0.90 | ❌ |

Procedure: WSCC-9 (Anderson & Fouad Ex. 2.6) → `K_true = |V_i||V_j|B_ij`
scaled ×8 → swing-equation trajectory (Störmer-Verlet, published
inertia/damping, pre-registered θ₀ perturbation) → `core.kuramoto.
coupling_estimator` (MCP row regression) → metrics. Every numeric is
the frozen-gate output; no threshold was retuned post-data.

## Where the error localizes (engineering deliverable)

The estimator **recovers the topology support exactly in the noiseless
regime** (F1 = 1.0 — it finds *which* generator pairs are coupled) but
**does not recover the signed edge weights**:

1. **Frobenius miss → `coupling_estimator` row regression is a
   first-order identifier applied to second-order data.** The estimator
   solves `θ̇_i − ω̄_i = Σ β_ij sin(θ_j−θ_i)` (the *first-order*
   Kuramoto identity). The WSCC swing model is *second-order*:
   `m_i θ̈_i + d_i θ̇_i = ω_i − Σ K_ij sin(θ_i−θ_j)`. The inertial
   term `m_i θ̈_i` is unmodeled, so β is a biased projection of `K/d`
   plus an inertial residual. Observed antisymmetric residual
   `‖(K̂−K̂ᵀ)/2‖_F = 15.9` on a physically *symmetric* truth confirms
   the row solver is not constrained to the correct (symmetric,
   second-order) model class.

2. **Identifiability boundary — strong coupling phase-locks the
   trajectory.** At `K_max ≈ 8` the system synchronises within a few
   cycles; thereafter `θ_j−θ_i → const`, the design columns
   `sin(θ_j−θ_i)` become near-constant and collinear, and the
   row regression is rank-deficient. A diagnostic coupling-strength
   sweep (`test_grid_kuramoto.py::test_identifiability_sweep_weak_regime`)
   shows the estimator *does* recover `K` (Frobenius rel. err. ≈ 0.17)
   in its design regime — weak coupling, non-phase-locked, persistently
   excited. The instrument is therefore sound; the WSCC-9 miss is a
   genuine persistent-excitation / model-class boundary, not a bug.

3. **`ω_rel_error = 1.0` → per-node natural frequency is unobservable
   from a phase-locked second-order trajectory.** Once the rotors lock
   to the common synchronous frequency Ω, `median(θ̇_i) = Ω` for every
   `i`; after mean-centring `ω̂ ≈ 0`. `ω_i` survives only in the
   *steady-state phase offsets*, which the estimator's
   `omega_nat = median(dθ/dt)` does not read. This localizes to
   `core.kuramoto.natural_frequency` (offset-based, not
   frequency-median, estimator), not to `coupling_estimator`.

4. **Critical-coupling miss is downstream of (1).** With `K̂ ≈ 0`
   (noiseless) the recovered Laplacian is rank-deficient → `s_crit_hat
   → 0` → rel. err. = 1.0. The Dörfler–Bullo formula itself is exact
   (verified to 1e-12 in `test_dorfler_bullo_*`); the miss propagates
   entirely from the coupling stage.

## Localized refinement targets (next work, priority order)

1. **`coupling_estimator`: add a second-order / inertial design.**
   Augment the row model with an acceleration term `m_i θ̈_i` (or fit
   the over-damped reduction `K/d` and back-scale by published `d`).
   Single biggest lever — recovers Frobenius and critical-coupling.
2. **`coupling_estimator`: persistent-excitation guard.** Reject /
   warn when the design Gram matrix is rank-deficient (phase-locked
   input) instead of returning a silent biased `K̂`. Fail-closed.
3. **`natural_frequency`: phase-offset estimator** for `ω_i` from the
   locked steady state, not the frequency median.

## What this artifact does *not* claim

It does **not** claim the GeoSync inverse stack is validated or
calibrated. It claims, at `MEASURED` tier against an exact external
ground truth, that the current `coupling_estimator` recovers grid
*topology* but **not** grid *coupling weights or natural frequencies*
in the strongly-coupled phase-locked second-order regime, and it names
the three estimator changes that would close the gap.
