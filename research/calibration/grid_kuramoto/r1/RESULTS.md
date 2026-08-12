# RESULTS — CALIB-GRID-001 R1 (sha-pinned NEGATIVE artifact)

> **Verdict: `NEGATIVE`.** One of the five frozen gates now passes
> (`noiseless.frobenius`); three still fail. This is the informative
> outcome of an external-ground-truth calibration, **not** a defect of
> the artifact and **not** a "validated" / "calibrated" result. R1 is an
> estimator-only change; the pre-registered gates, data, seeds, σ and θ₀
> are the frozen ground truth from PR #749 and were not touched.
>
> Source ledger: `r1/RESULTS.json`
> (`ledger_sha256 = c32011b89fc879ec…`). Parent ledger
> `ed8d409b7b222eb0…`, frozen pre-registration sha
> `d170d48afa5066c13edeb40b2c1904b3fd708516`.
> Reproduce:
> `PYTHONPATH=. python -m research.calibration.grid_kuramoto.run --system wscc9 --r1`.

## Before → after, all five frozen gates (tier: MEASURED)

Metric = the exact frozen-gate output. Procedure = WSCC-9
(Anderson & Fouad Ex. 2.6) → `K_true = |V_i||V_j|B_ij` ×8 →
swing-equation trajectory (Störmer-Verlet, published inertia/damping,
frozen θ₀ perturbation, seed 42) → estimator → frozen gates. The only
change between the two columns is the estimator path.

| Gate | Metric | Threshold | Parent (first-order) | R1 (swing) | R1 pass |
|---|---|---|---|---|---|
| `noiseless.frobenius` | `‖K̂−K‖_F/‖K‖_F` | ≤ 0.10 | 1.0459 | **0.0666** | ✅ |
| `noiseless.topology_f1` | edge-support F1 | ≥ 0.95 | 1.0000 | 1.0000 | ✅ |
| `noiseless.critical_coupling` | rel. err. vs Dörfler–Bullo | ≤ 0.15 | 1.0000 | **0.4942** | ❌ |
| `noisy.frobenius` (σ=0.02) | `‖K̂−K‖_F/‖K‖_F` | ≤ 0.25 | 0.9901 | 16.6071 | ❌ |
| `noisy.topology_f1` (σ=0.02) | edge-support F1 | ≥ 0.90 | 0.8000 | 0.8000 | ❌ |

Supporting diagnostics (not gates):

| Quantity (noiseless) | Parent | R1 |
|---|---|---|
| antisymmetric residual `‖(K̂−K̂ᵀ)/2‖_F` | 15.905 | **0.000** |
| absolute Frobenius error `‖K̂−K‖_F` | 19.023 | **1.211** |
| `ω` relative error `‖ω̂−ω‖/‖ω‖` | 1.0000 | **0.4711** |
| recovered `s_crit_hat` (true 0.0196) | 0.0000 | 0.0099 |

## What R1 fixed (numeric deltas, no promotion language)

1. **Inertial-bias removal — `noiseless.frobenius` 1.046 → 0.067
   (now PASS).** Regressing the full swing identity instead of the
   first-order one removes the unmodelled `m_i θ̈_i` term. Combined
   with the symmetric joint solve the **antisymmetric residual
   collapses from 15.9 to 0.0** — the parent's headline localization
   ("first-order identifier on second-order data") is closed.
2. **Natural frequency — `ω` rel. err. 1.000 → 0.471.** `ω̂ = P̂/d`
   from the recovered injection replaces the phase-locked-blind
   frequency-median; the per-node frequency is now partially
   identified rather than ≈ 0.
3. **Critical coupling — 1.000 → 0.494.** Improved but still failing
   (see below).

## Where the remaining error localizes (next defect)

The verdict is still `NEGATIVE`. Two distinct boundaries remain, both
already anticipated by PREREGISTRATION § 3:

1. **`noiseless.critical_coupling` (0.494, gate ≤ 0.15) — propagation
   through an ill-conditioned pseudo-inverse.** The Dörfler–Bullo
   `s_crit = ‖B†ω‖_{E,∞}` involves the Moore–Penrose pseudo-inverse of
   the weighted incidence map. Near the locking boundary this map is
   ill-conditioned, so the residual ~7 % Frobenius / ~47 % `ω` error
   amplifies to ~49 % `s_crit` error. Localizes to the **joint
   coupling+ω accuracy feeding `dorfler_bullo_critical_coupling`**, not
   to the analytic formula (verified exact to 1e-12 in
   `test_dorfler_bullo_*`) and no longer to the antisymmetric model
   class. Next lever: a symmetry- and Laplacian-consistency-constrained
   solve that ties `K̂` and `ω̂` to a single connected synchronised
   manifold.
2. **`noisy.*` (σ=0.02) — second-derivative SNR / persistent-excitation
   boundary.** A swept verification over Savitzky–Golay
   `window ∈ {7…501}, polyorder ∈ {3,4,5}` shows the noisy Frobenius
   error never drops below ≈ 0.61: narrow windows amplify the
   double-differentiation noise (error → 16), wide windows over-smooth
   the short over-damped transient (error → 1.0). **No consistent
   estimator exists for the noisy regime at this trajectory length and
   excitation level** — this is the persistent-excitation / SNR
   boundary PREREGISTRATION § 3 named, now confirmed quantitatively for
   the second-order path. Closing it requires changing the *frozen*
   experiment (longer record, larger θ₀, lower σ), which R1 is not
   permitted to do, **or** a state-space (Kalman/EM) swing identifier
   that does not differentiate the phase twice.

## What this artifact does *not* claim

It does **not** claim the GeoSync inverse stack is validated or
calibrated. It claims, at `MEASURED` tier against an exact external
ground truth, that the R1 swing-aware symmetric estimator **closes the
first-order / antisymmetric model-class defect** (noiseless Frobenius
1.046 → 0.067, antisymmetric residual 15.9 → 0.0, one frozen gate
flipped to PASS) but that two further boundaries — pseudo-inverse
ill-conditioning in the critical-coupling propagation and the
double-differentiation SNR boundary in the noisy regime — keep the
overall verdict `NEGATIVE`, and it names the next refinement targets.
