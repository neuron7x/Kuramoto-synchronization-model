# THRESHOLD_PROVENANCE — swing identifiability front-gate

> **Pre-committed before any calibration validation was run.** This file
> fixes the identifiability score formula and the REFUSE threshold from
> numerical / statistical theory alone. It contains **no** measured
> calibration value. A no-peek drift test
> (`test_threshold_provenance_no_peek`) asserts the constants in
> `core.kuramoto.identifiability` equal the theory values committed here;
> changing either side without changing both fails CI.
>
> Lineage: upgrade #2 on top of CALIB-GRID-001 (PR #749) and its R1
> swing-aware refinement (PR #751). This is **reliability / instrument
> honesty infrastructure**, not a science claim. It does **not** close
> the frozen `noisy.frobenius` gate; it makes the instrument *declare*
> that it fails there.

## 1. What is being graded

The merged R1 swing path solves the linear identity, per node `i`,

    m_i θ̈_i(t) + d_i θ̇_i(t)  =  P_i + Σ_{j≠i} (−K_ij) sin(θ_i(t) − θ_j(t)) ,

stacked over all nodes into one global least-squares problem
`D_std · c_std ≈ y` on the **column-standardised** design `D_std`
(scale factors `s_p`), with `K̂` recovered as `K = −c / s`,
`c = c_std / s`.

The merged persistent-excitation guard is **binary**: it raises
`PersistentExcitationError` only when the *reciprocal condition number*
of `D_std` falls below a hard floor. It is blind to the dominant
calibration failure mode (see § 4): additive phase noise, after double
differentiation, inflates the residual variance by ~5 orders of
magnitude and biases `K̂` by ~20× while *improving* the design
conditioning. Conditioning alone therefore cannot self-report the
noisy-regime failure. The graded layer below propagates **both** the
design conditioning **and** the measurement-noise floor.

## 2. Identifiability score (theory-derived, not a tuned knob)

Linearised ordinary-least-squares covariance of the standardised
solution (Gauss–Markov; the swing identity is linear in
`(K, P)` once `(θ̇, θ̈)` are fixed):

    σ̂²       = ‖y − D_std ĉ_std‖²  /  (n_obs − n_param)        (1)
    Cov(ĉ_std) = σ̂² · (D_stdᵀ D_std)⁺                          (2)
    SE(K̂_p)   = sqrt( [Cov(ĉ_std)]_{pp} )  /  s_p              (3)

Equation (1) is the residual-variance (noise-floor) estimate; (2) is
the Cramér–Rao bound for the linear Gaussian model (`(D_stdᵀD_std)⁺` is
the inverse Fisher information up to σ̂²); (3) back-transforms to
physical units. The Moore–Penrose pseudo-inverse is used so a
rank-deficient design degrades gracefully into the existing hard PE
guard rather than raising inside the covariance.

**Interpretation — this is a CRLB *lower bound*, not a
coverage-calibrated interval (honest scoping).** The dominant error of
the merged R1 swing path in the *noiseless* regime is a **deterministic
Savitzky–Golay derivative bias**, not estimation variance: `σ̂² → 0`
while `‖K̂ − K‖ ≠ 0`. The residual-variance covariance therefore
*under*-states the true error there — a Monte-Carlo over the matched
recovery regime shows empirical coverage far below nominal when the
fit is near-exact (verified, reported in `RESULTS.md`). Consequently
`SE(K̂_p)` is used **only** as what the Cramér–Rao theorem proves it to
be: a *lower bound* on the standard error of any unbiased estimator
(`SE_true ≥ SE_CRLB`). It is **never** promoted as a 95 % coverage
interval. The front-gate is built so its verdict does **not** depend on
CI calibration:

* the **precision leg** uses `w_p = |K̂_p|/SE_CRLB` as an *optimistic
  upper bound* on the true Wald ratio. "Even the best-case (smallest
  possible) SE leaves the CI straddling zero" is then a **sufficient**
  (sound, conservative) REFUSE condition — it can only ever
  *under*-trigger REFUSE on precision, never falsely ACCEPT a
  variance-unidentifiable edge;
* the **decisive leg is model adequacy `R²`** (below), which is
  *bias-sensitive* and is what actually separates the two frozen
  calibration regimes.

The per-edge band is reported as a CRLB variance band for transparency,
explicitly flagged non-coverage-calibrated.

Identifiability has **two independent legs**, both required (a point
estimate is trustworthy only if it is both *precise* and *adequate*):

**(A) Per-edge precision — Wald / inverse-coefficient-of-variation
ratio.**

    w_p = |K̂_p| / SE(K̂_p)                                      (4)
    w_min = min_p w_p

`w` → 0 as an edge becomes variance-unidentifiable (`SE ≫ |K̂|`, e.g.
near phase-locked).

**(B) Model adequacy — coefficient of determination of the linear
swing fit.** The swing identity is *exact* in the noiseless limit, so
the linear model must explain the target; the standard a-priori
model-adequacy statistic is

    R² = 1 − SSR / SST ,  SSR = ‖y − D_std ĉ_std‖² ,
         SST = ‖y − ȳ‖²                                          (5)

Leg (B) is essential because leg (A) alone is **blind to bias**: after
double differentiation, measurement noise can inflate both `|K̂_p|` and
`SE(K̂_p)` so that `w_p` stays large while `K̂` is grossly wrong (the
fit is confidently incorrect, not imprecise). `R²` detects exactly this:
when the un-modelled residual dominates, `R² → 0` even though the
per-coefficient Wald ratios remain finite.

The scalar **identifiability score** combines both legs, each mapped
into a bounded, monotone range and conjoined by the minimum (a chain is
as strong as its weakest leg):

    s_A = w_min / (1 + w_min)            (precision leg, ∈ [0, 1))
    s_B = max(R², 0)                      (adequacy leg, ∈ [0, 1])
    IDENTIFIABILITY = min(s_A, s_B)       (∈ [0, 1])              (6)

`IDENTIFIABILITY` → 0 if *either* the weakest edge is variance-
unidentifiable *or* the linear model fails to explain the data. It is
**scale-free** and both legs are derived from the linear Gaussian
model's Fisher information and residual noise floor — there is no
fitted constant.

**Monotonicity scope (empirically corrected, no-peek-safe).** The
adequacy leg is **not** a globally monotone function of σ. Because the
swing target `y = m θ̈ + d θ̇` is itself a *differentiated* signal,
additive phase noise inflates **both** the residual `SSR` *and* the
total `SST`, so `R² = 1 − SSR/SST` collapses sharply away from σ = 0
and then merely *fluctuates inside a low noise-dominated floor* — it
does not decrease strictly. The defensible, verified property — and the
only one the reliability contract needs — is the **coarse separation**:

* at σ = 0 (and the noiseless calibration case) the score is **high**
  and **above** `REFUSE_SCORE` (ACCEPT);
* for any non-trivial measurement noise the score **collapses below**
  `REFUSE_SCORE` (REFUSE) and stays there.

Correcting this over-claim changes **no threshold and no constant**
(`REFUSE_SCORE = z/(1+z)`, `R2_FLOOR = ½` are untouched); it only
restates the monotonicity property to what is empirically true, before
any RESULTS were produced. The record-length property holds in the
expected direction (a longer matched record under persistent excitation
does not push an ACCEPT into REFUSE) and is asserted as such.

## 3. REFUSE threshold (numerical + statistical theory)

Two theory-derived REFUSE legs, **either** of which triggers REFUSE
(fail-closed conjunctive trust — the gate accepts only if both pass):

**Leg A — precision floor.** A coupling entry is not statistically
identifiable when its two-sided 95 % Wald confidence interval contains
zero, i.e.

    |K̂_p|  ≤  z_{0.975} · SE(K̂_p) ,    z_{0.975} = 1.959963984540054

(standard-normal 0.975 quantile; large-sample Wald CI for the linear
Gaussian model). Equivalently `w_p ≤ z_{0.975}`. Mapping the binding
edge through `s_A`, the precision-REFUSE level is

    s_A  <  REFUSE_SCORE
    REFUSE_SCORE  =  z / (1 + z)  with  z = 1.959963984540054
                  =  0.6621580515090663…                          (7)

i.e. REFUSE when the weakest coupling entry's 95 % CI straddles zero.

**Leg B — adequacy floor.** The linear swing identity is exact in the
noiseless limit. Information about the coupling survives only while the
*explained* variance is at least the *unexplained* variance — once the
un-modelled residual dominates, no estimator (biased or unbiased) can
recover `K`. The canonical "signal at least as large as noise" boundary
is therefore

    R²  <  R2_FLOOR  =  0.5                                       (8)

`R² = ½` is exactly `SSR = SST/2` (explained = unexplained). This is
the same ½-information argument as the √eps mantissa floor (7): below
it more than half the target variance is noise. `R2_FLOOR` is a fixed
theory constant, **not** fitted to any calibration value.

Because `IDENTIFIABILITY = min(s_A, s_B)` and `s_B = max(R², 0)`, the
single REFUSE rule is

    IDENTIFIABILITY  <  REFUSE_SCORE  with  REFUSE_SCORE = z/(1+z)

provided `R2_FLOOR ≤ REFUSE_SCORE` (0.5 ≤ 0.662 ✓): any `R² < 0.5`
forces `s_B < 0.5 < REFUSE_SCORE`, so the adequacy failure alone trips
the same threshold. The gate is thus a single bounded comparison while
remaining the conjunction of the precision and adequacy legs. It is the
smallest theory point at which a point estimate is *misleading rather
than imprecise*.

Conjoined numerical floor (kept as the **hard** fail, unchanged from the
merged code): the reciprocal condition number of `D_std` below

    PE_HARD_FLOOR  =  sqrt(eps_float64)  =  1.4901161193847656e-08    (9)

means the linear solve has lost more than half of the float64 mantissa
(`eps ≈ 2.22e-16`; losing ½ the 52-bit mantissa ⇒ relative error
≳ √eps). That extreme remains `PersistentExcitationError` (fail-closed).
The graded REFUSE in (6) sits **above** that hard floor: it is the
statistical envelope, not the numerical catastrophe.

Decision lattice (fail-closed, evaluated in this order):

1. reciprocal cond `< PE_HARD_FLOOR`  → `PersistentExcitationError`
   (unchanged hard fail).
2. else `IDENTIFIABILITY < REFUSE_SCORE` → typed `REFUSE` verdict +
   score + reason + the offending edge + its CI. **No point estimate is
   promoted as trustworthy.**
3. else → `ACCEPT` with `K̂`, per-edge SE and 95 % CIs.

## 4. Why conditioning alone is insufficient (motivation, not a gate)

The reciprocal condition number of the standardised design is *larger*
(better) in the σ=0.02 calibration case than in the noiseless one,
because additive phase noise adds variance to the sine regressors. The
merged binary PE guard therefore passes the noisy case while the
recovered `K̂` is biased ~20×. The residual variance σ̂² (eq. 1) is the
quantity that separates the regimes by ~5 orders of magnitude; that is
why the score is built on the *noise-aware* regression covariance (2),
not on conditioning. (The specific calibration numbers belong in
`RESULTS.md`, produced **after** this provenance was committed.)

## 5. Frozen-gate discipline

Nothing here changes `PREREGISTRATION.md`, `gates.py`, the five frozen
acceptance thresholds, the embedded IEEE data, the seeds, σ, the θ₀
perturbation or the decision rule of CALIB-GRID-001 / R1. The first-
order and R1 swing point estimates are bit-identical when the new
covariance fields are ignored (additive `SwingCouplingEstimate` fields;
verified by the existing R1 bit-stability test plus a new ignore-fields
regression test). The frozen `noisy.frobenius` gate **stays NEGATIVE**;
the only change is that the instrument now self-reports that it fails
there instead of silently emitting a misleading `K̂`.
