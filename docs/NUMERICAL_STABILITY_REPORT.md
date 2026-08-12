# Numerical Stability Report — ARC-017

**Scope:** hardening and validation of the numerical stability of the Lyapunov
and DFA/Hurst estimators.
**Estimators validated (importable + exercised):**

| # | Estimator | Module | Algorithm |
|---|-----------|--------|-----------|
| 1 | `maximal_lyapunov_exponent` | `core/physics/lyapunov_exponent.py` | Rosenstein (1993) MLE, cKDTree neighbors |
| 2 | `RosensteinLyapunov` | `geosync/estimators/lyapunov_estimator.py` | Rosenstein MLE, brute-force neighbors (coarse) |
| 3 | `lyapunov_spectrum` | `core/physics/lyapunov_spectrum.py` | Benettin–Galgani–Strelcyn QR on JAX variational flow |
| 4 | `DFAGammaEstimator` | `geosync/estimators/dfa_gamma_estimator.py` | DFA-1 Hurst + db4 wavelet cross-check |

No estimator source was modified. This task adds only the validation gate,
tests, golden vectors, and this report. **No existing invariant bound was
loosened** — INV-LY1/LY2 keep their `1e-3` tolerance, INV-LE3 keeps
`R2_MIN = 0.80`, DFA keeps `min_quality = 0.95`. The `0.05` acceptance bands
below apply only to the *trusted-baseline recovery* (ln2 / known Hurst); they
are strictly wider than every measured residual and strictly tighter than a
sign/regime confusion.

Evidence (regenerate with `python scripts/ci/check_numerical_stability.py --freeze`):
`artifacts/numerical/validation_report.json`, `artifacts/numerical/golden_vectors.json`.
Gate: `python scripts/ci/check_numerical_stability.py` (exit 0 GREEN / 1 RED / 2 malformed).

---

## 1. Reference cross-checks vs a trusted numerical baseline

All values are the **actual achieved** numbers from a fresh run — not idealised.

| Cross-check | Estimator | Expected | Achieved | Abs error | Tol | Derivation of tol | Verdict |
|-------------|-----------|----------|----------|-----------|-----|-------------------|---------|
| Logistic map r=4 → ln2 | `maximal_lyapunov_exponent` (dim=5, τ=1, N=1500) | ln2 = 0.6931472 | **0.6939148** | 7.68e-4 | 0.05 abs | logistic r=4 has analytic MLE = ln2; Rosenstein small-data slope carries finite-sample bias + ensemble sampling noise (literature: few-% of ln2 at N~10³). 0.05 ≈ 7% ln2 ≫ observed, ≪ sign confusion | PASS (R²=0.99999 ≥ 0.80) |
| Logistic map r=4 → chaotic sign | `RosensteinLyapunov` (m=3, N=500) | λ > 0, valid | **0.617715** (valid, chaotic) | 0.0754 vs ln2 | band [0.45, 0.85] | coarse estimator (m=3 fixed, first-10-step fit, small data) recovers the chaotic *sign* but systematically underestimates ln2 by ~11%. Cross-check is the INV-LE2 sign/band test, not exact ln2 | PASS |
| Linear ẋ=Ax → Re(eig A) | `lyapunov_spectrum` (dt=0.01, T=50) | [-0.2, -0.5, -1.0] | **[-0.1999999, -0.4999979, -0.9999832]** | 1.68e-5 | 1e-3 (**INV-LY1**) | invariant bound, unchanged; achieved 1.68e-5 ≪ 1e-3 | PASS |
| Harmonic osc. → Σλ = 0 | `lyapunov_spectrum` (ω·dt=0.05, ~16 periods) | 0 | **3.12e-5** | 3.12e-5 | 1e-3 (**INV-LY2**) | invariant bound, unchanged. Non-symplectic tangent integrator ⇒ Σλ error grows **O((ω·dt)⁴)** (measured slope 3.998, CLAUDE.md); bound holds only when the fastest mode is time-resolved (ω·dt ≲ 0.05) | PASS |
| fGn Hurst recovery | `DFAGammaEstimator` (N=8192) | H ∈ {0.3, 0.5, 0.7} | **0.30692 / 0.49940 / 0.69512** | ≤ 6.9e-3 | 0.05 abs | DFA-1 finite-sample Hurst bias is O(0.01–0.02) at N~8k (Kantelhardt 2001); spectral-synthesis fGn is itself approximate. 0.05 brackets observed ≤ 7e-3. γ = 2H+1 derived to < 1e-5; DFA `min_quality` R² ≥ 0.95 enforced | PASS |

**Honest residuals.** The coarse `RosensteinLyapunov` underestimates ln2 by
~11% (0.618 vs 0.693) — an accepted property of the small-data, fixed-`m=3`,
first-10-step-fit design, not a bug. DFA-1 on a short (N=4096) white-noise
series recovers H = 0.4394 rather than 0.5 (short-series low bias); this is
stored as a *regression anchor*, not an accuracy claim.

---

## 2. Adversarial inputs → explicit refusal (23/23)

Each estimator must refuse NaN / ±Inf / constant / all-zero / too-short /
rank-deficient (two-value collapse) input with an **explicit** signal, never a
silent number.

| Estimator | Refusal mechanism | nan | inf | constant | all-zero | too-short | rank-deficient |
|-----------|-------------------|-----|-----|----------|----------|-----------|----------------|
| `maximal_lyapunov_exponent` | `ValueError` (INV-LE1) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `RosensteinLyapunov` | `is_valid=False` sentinel (INV-LE3) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `DFAGammaEstimator` | `ValueError` **or** `_invalid_estimate` sentinel (INV-DRO5 family) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `lyapunov_spectrum` | `ValueError` (INV-LY3) on dt≤0 / n_steps≤0 / qr_every∤n_steps / x0 non-1D / n_exp>n | 5/5 contract violations refused |

**Refusal-semantics note (honest).** `maximal_lyapunov_exponent` raises on the
whole adversarial set. `RosensteinLyapunov` never raises — it fails closed via
the frozen `is_valid=False` sentinel (λ=0.0, is_valid=False), which a caller
*must* check. `DFAGammaEstimator` raises on the two-value/rank-deficient case
but returns the documented `_invalid_estimate` sentinel (`r_squared=0.0`, empty
`dfa_fluctuations`, `scale_range=(0,0)`) for NaN/Inf/constant/all-zero/too-short.
That sentinel carries a legal-looking `gamma=1.0`; the gate treats it as a
refusal **only** because `r_squared==0.0` and the fluctuation record is empty —
the INV-DRO5 fail-closed contract. All three refusal channels are asserted in
the gate and tests.

---

## 3. Error bounds documented

| Invariant | Bound | Meaning |
|-----------|-------|---------|
| INV-LE1 | `ValueError` on NaN/Inf/constant/degenerate/too-short | MLE is finite for any non-degenerate bounded finite series; fail-closed otherwise, never NaN/±Inf, never a spurious λ=0 |
| INV-LE3 | log-divergence fit **R² ≥ 0.80** | Rosenstein slope is λ only on the linear scaling region; below the floor → fail-closed 0.0 sentinel (never a silent slope). `diagnostics` exposes `r_squared/slope/n_fit/scaling_ok` |
| INV-LY1 | `‖spectrum − Re(eig A)‖∞ ≤ 1e-3` | linear-system spectrum equals eigenvalue real parts |
| INV-LY2 | `|Σλ| ≤ 1e-3`, error **O((ω·dt)⁴)** | Hamiltonian pairing; non-universal, holds only for a time-resolved fastest mode |
| INV-LY4 | `max\|QᵀQ−I\| ≤ 1e-10`, `min\|R_kk\|/max\|R_kk\| > eps_f64` | QR conditioning fail-closed → `FloatingPointError`, never a 1e-30-floored garbage exponent |
| INV-DRO1 | `\|γ − (2H+1)\| < 1e-5`; DFA `min_quality` R² ≥ 0.95 | γ is DERIVED from the DFA Hurst, never assigned; unreliable scaling fit → `ValueError` |

---

## 4. Golden vectors (6)

Frozen deterministic input → exact expected output, so a future numerical
regression turns the gate RED. Inputs are pure recurrences (logistic map) or
bit-reproducible PCG64 draws (`numpy.random.default_rng`), so the vectors are
cross-platform stable.

| Vector | Deterministic input | Frozen output | Reproduce atol |
|--------|---------------------|---------------|----------------|
| `mle_core_logistic` | `logistic_series(1500)` | λ = 0.6939148, R² = 0.9999946 | 1e-4 |
| `mle_geosync_logistic` | `logistic_series(500)` | λ = 0.617715, valid, chaotic | 1e-4 |
| `spectrum_linear` | A (3×3), dt=0.01, 5000 steps | [-0.1999999, -0.4999979, -0.9999832] | 1e-6 |
| `spectrum_harmonic` | A=[[0,1],[-1,0]], dt=0.05, 2011 steps | [1.5625e-5, 1.5625e-5], Σ=3.125e-5 | 1e-6 |
| `dfa_fgn_h05` | `fgn_series(8192, 0.5, seed=42)` | H = 0.499403, γ = 1.998806, R² = 0.994023 | 1e-4 |
| `dfa_white_noise` | `default_rng(20260719).standard_normal(4096)` | H = 0.439422, γ = 1.878844, R² = 0.982167 | 1e-4 |

---

## 5. Closure (tests/ci/test_numerical_stability.py)

**Positive:** all 5 cross-checks within tol; 23/23 adversarial refusals fire;
6/6 golden vectors reproduce; the gate exits GREEN.

**Negative (falsifiability):**
1. a golden vector mutated by 1e-2 (≫ its 1e-4 atol) makes `verify_golden`
   report that vector `ok=False` (RED), while the untouched vectors stay green;
2. a hypothetical fail-open estimator that returns `0.0` on a NaN series is
   flagged non-refusing by the exact predicate the gate uses, while the real
   `maximal_lyapunov_exponent` raises `INV-LE1` on the same input.

Run:

```
python -m pytest tests/ci/test_numerical_stability.py -q --timeout=120
python scripts/ci/check_numerical_stability.py
python -m ruff check scripts/ci/check_numerical_stability.py
```

---

## Acceptance

- [x] Cross-check vs trusted baseline passes with documented tolerance (ln2:
      0.6939 vs 0.6931, tol 0.05; INV-LY1: 1.68e-5 ≤ 1e-3; DFA H recovered ≤ 7e-3).
- [x] Error bounds documented (R² ≥ 0.80 Rosenstein gate; O((ω·dt)⁴) INV-LY2;
      1e-3 INV-LY1; γ=2H+1 to 1e-5; INV-LY4 conditioning).
- [x] Unstable/underpowered input returns an explicit refusal, not a number
      (23/23 across ValueError / is_valid=False / _invalid_estimate sentinels).
- [x] Golden vectors freeze reference inputs → exact outputs (6 vectors).
- [x] No existing invariant bound loosened.
