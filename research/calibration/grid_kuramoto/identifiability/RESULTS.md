# RESULTS — CALIB-GRID-001 identifiability front-gate (upgrade #2)

> **This is reliability / instrument-honesty infrastructure, not a
> science claim, and it does NOT close the frozen `noisy.frobenius`
> gate.** The frozen pre-registered noisy regime **stays NEGATIVE**.
> The upgrade is that the instrument now *knows* it fails there and
> *says so* (typed `REFUSE`), instead of silently emitting the
> ~20×-biased point estimate the parent lineages exposed. No promotion
> language; no gate retuned; no frozen file touched.
>
> Parents: PR #749 (CALIB-GRID-001), PR #751 (R1 swing path).
> Theory + pre-committed REFUSE threshold: `THRESHOLD_PROVENANCE.md`
> (committed *before* this validation; bound by a no-peek drift test).
> Source ledger: `RESULTS.json`
> (`ledger_sha256 = 4787f012a6135293…`), frozen pre-registration sha
> `d170d48afa5066c13edeb40b2c1904b3fd708516`, parent ledger
> `ed8d409b7b222eb0…`. Reproduce: `PYTHONPATH=. python -m
> research.calibration.grid_kuramoto.identifiability.validate`.

## Before → after: binary PE guard vs graded self-knowledge

Tier **MEASURED**. Metric = the graded front-gate output. Procedure =
the *exact* frozen CALIB-GRID-001 / R1 pipeline (WSCC-9, Anderson &
Fouad Ex. 2.6 → `K_true = |V_i||V_j|B_ij` ×8 → swing-equation
trajectory, published inertia/damping, frozen θ₀ perturbation, seed 42,
σ=0.02) → R1 symmetric swing estimator → **the new front-gate**. The
only change vs the merged R1 path is the additive graded layer.

| Quantity | Noiseless | Noisy (σ=0.02) |
|---|---|---|
| reciprocal condition `1/cond(D_std)` | 8.16e-02 | **4.78e-01** |
| binary PE guard (merged, threshold 1e-3) | passes | **passes** |
| graded front-gate verdict | **ACCEPT** | **REFUSE** |
| identifiability score | 0.96999 | 0.16299 |
| model adequacy `R²` | 0.99142 | 0.16299 |
| `‖K̂−K‖_F/‖K‖_F` (frozen R1 metric) | 0.0666 | 16.6071 |
| `‖K̂‖_F` vs `‖K‖_F` (true 18.19) | 18.86 | **313.41** |

**The defect the binary guard cannot see.** The reciprocal condition
number is *higher* (the design is *better* conditioned) in the noisy
case than the noiseless one — additive phase noise adds variance to the
sine regressors. So the merged binary persistent-excitation guard
**passes the noisy regime** while the recovered `K̂` is biased ~20×
(`[143, 169, −17]` for a true `[7.7, 5.2, 8.9]`). The graded layer
propagates the *measurement-noise floor* via the bias-sensitive `R²`:
0.991 (adequate) noiseless vs 0.163 (noise-dominated) noisy — a clean
separation across the pre-committed `R2_FLOOR = ½`.

## The two pre-registered validation cases (MEASURED)

**Noiseless WSCC-9 → ACCEPT.** Score 0.970 ≥ refuse threshold 0.6622;
`R² = 0.991`; every edge's CRLB band excludes zero; `‖K̂‖_F = 18.86`
vs true `18.19`. The instrument correctly reports it is in envelope.

**σ=0.02 noisy WSCC-9 → REFUSE.** Score 0.163 < 0.6622; `R² = 0.163`
(< ½, noise-dominated fit); reason emitted: *"model adequacy: R²<½ —
the linear swing fit is noise-dominated; the per-edge Wald CIs are
tight around a biased K̂ (confidently wrong, not imprecise)"*. **No
point estimate is promoted as trustworthy.** The instrument declares
itself out of envelope — exactly the failure the parent lineage
silently exposed.

## Honest scoping of the CRLB band (non-coverage)

The per-edge band is the Cramér–Rao **lower bound** on the SE of any
unbiased estimator (provenance § 2), **not** a 95 % coverage interval.
On the noiseless case the band covers **0/3** true entries — reported,
not hidden — because the merged R1 swing path is *bias*-dominated
(deterministic Savitzky–Golay derivative bias ≈ 6.7 % Frobenius, the
frozen R1 residual), and a variance lower bound legitimately does not
cover a biased estimate's distance to truth. The front-gate verdict
**does not depend on band coverage**: the decisive leg is the
bias-sensitive `R²` adequacy test; the precision (Wald/CRLB) leg is
used only as a sound one-sided sufficient REFUSE condition. A
Monte-Carlo over the matched-recovery regime (`σ ∈ {0, 1e-4}`,
nrep=120) confirms the band is a lower bound, not nominal-coverage:
empirical coverage is ≈0.03 when the fit is near-exact (band far
tighter than the residual bias) and only ≈0.95 when noise has already
inflated the SE into a (correctly) REFUSED estimate. This is documented
as a limitation, not masked.

## What this artifact does *not* claim

It does **not** claim the inverse stack is validated or calibrated. It
does **not** close the frozen `noisy.frobenius` gate — that gate is
still NEGATIVE (`‖K̂−K‖_F/‖K‖_F = 16.6 ≫ 0.25`). It claims, at
`MEASURED` tier against the exact external ground truth, exactly one
thing: the instrument's self-knowledge went from **binary** (rank-
deficient → raise, blind to the noisy-bias failure) to **graded** (the
front-gate ACCEPTs the in-envelope noiseless case and REFUSEs the
out-of-envelope σ=0.02 case, with a typed reason and per-edge CRLB
band). Failure is now self-evident instead of silent.
