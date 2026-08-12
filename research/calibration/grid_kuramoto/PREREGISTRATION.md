# PRE-REGISTRATION — CALIB-GRID-001

> **Status:** pre-registered, fail-closed. Committed on branch
> `feat/calib-grid-001` off `origin/main` sha
> `ab4555ed8819abea12ba5afa1eaa52e2f5929b6f`.
>
> The acceptance gates below are the single source of truth and are
> mirrored byte-for-numeric by
> `research.calibration.grid_kuramoto.gates`. `tests/research/
> calibration/test_grid_kuramoto.py::test_preregistration_matches_code`
> fails closed if this document and the code diverge. No threshold may
> be retuned after the result ledger is produced — a post-data edit
> invalidates the artifact.

## 1. Identifier

`CALIB-GRID-001` — external ground-truth **calibration** (not a
hypothesis) of GeoSync's Sakaguchi–Kuramoto coupling inverse-problem
stack against a proven, measured engineering benchmark.

## 2. What is being calibrated

The power-grid Kuramoto reduction (Dörfler & Bullo, *Synchronization in
complex oscillator networks and smart grids*, PNAS 2013,
110(6):2005–2010) on the canonical WSCC 3-machine 9-bus system
(Anderson & Fouad 2003, Ex. 2.6) gives a **double ground truth**:

1. *Numerical* — the published admittance / injection data yields the
   exact true coupling `K_true_ij = |V_i||V_j|B_ij` and the true
   natural frequency `ω_true_i = P_i / d_i`.
2. *Analytic* — Dörfler–Bullo Eq. (3) gives a closed-form critical
   coupling scale `s_crit = ‖B†ω‖_{E,∞}`.

We feed swing-equation phase data into GeoSync's estimator and measure
recovery of what is already known exactly.

## 3. Pre-registered configuration (frozen)

```json
{
  "system": "WSCC-9 (Anderson&Fouad-2003-Ex2.6)",
  "coupling_scale": 8.0,
  "dt": 0.01,
  "steps": 8000,
  "keep_frac": 0.6,
  "theta0_perturb": 0.6,
  "seed": 42,
  "noise_sigma": 0.02,
  "lambda_reg": 0.02,
  "penalty": "mcp",
  "topology_rel_threshold": 0.1,
  "integrator": "Störmer-Verlet (core.kuramoto.second_order)",
  "estimator": "core.kuramoto.coupling_estimator (MCP row regression)"
}
```

`theta0_perturb > 0` is mandatory and pre-registered: a frozen
synchronous equilibrium carries **no** identification signal
(persistent-excitation condition for second-order Kuramoto
identification). The early damped oscillatory transient (`keep_frac`
fraction of the trajectory) is the signal; this is fixed before data.

## 4. Pre-registered acceptance gates (frozen — mirror of `gates.py`)

### Noiseless regime (`noise_sigma = 0`)

| Gate | Metric | Operator | Threshold | Localises a miss to |
|---|---|---|---|---|
| `noiseless.frobenius` | `frobenius_rel_error` | `<=` | `0.1` | coupling_estimator row-regression bias / λ_reg |
| `noiseless.topology_f1` | `topology_f1` | `>=` | `0.95` | coupling_estimator sparse-support thresholding |
| `noiseless.critical_coupling` | `critical_coupling_rel_error` | `<=` | `0.15` | end-to-end (K_hat propagated through Dörfler–Bullo) |

### Noisy regime (`noise_sigma = 0.02`, additive Gaussian on wrapped θ)

| Gate | Metric | Operator | Threshold | Localises a miss to |
|---|---|---|---|---|
| `noisy.frobenius` | `frobenius_rel_error` | `<=` | `0.25` | coupling_estimator noise robustness / standardisation |
| `noisy.topology_f1` | `topology_f1` | `>=` | `0.9` | coupling_estimator support stability under σ |

## 5. Decision rule

`verdict = PASS` iff **every** gate passes; otherwise `verdict =
NEGATIVE`. A `NEGATIVE` verdict is **informative**, not a defect of the
artifact: the failing gate's `localises_to` field names the exact
GeoSync estimator stage to refine next. No promotion language
("validated" / "calibrated" / "passed") is permitted on partial
success; the only admissible terminal labels are `PASS` and `NEGATIVE`.

## 6. Replication

| Field | Value |
|---|---|
| Tolerance class | `deterministic_with_drift` |
| Determinism | all RNG seeded from `seed=42`; integrator deterministic |
| Capsule | `RESULTS.json` (`ledger_sha256` over `sort_keys=True` JSON) |

## 7. Maintenance-hierarchy role

Layer 4 diagnostic. The instrument **never** takes execution action; it
emits a calibration verdict that points at the next refinement target.
