# CALIB-GRID Supersession Record (append-only)

> **Status:** append-only epistemic-integrity governance layer. This
> document and its machine-readable twin `SUPERSESSIONS.yaml` record
> that a sha-pinned CALIB-GRID artifact encodes a causal premise a
> *later* sha-pinned lineage has falsified. **No frozen artifact is
> edited, recomputed or rewritten.** The historical NEGATIVE/FAIL
> records are immutable and stay byte-identical; the supersession
> resolves **forward** (lineage #6+), it does not retroactively rewrite
> the record. The single source of truth for the machine contract is
> `SUPERSESSIONS.yaml`; this file is the rationale.

## Why this layer exists

R1's sha-pinned `r1/RESULTS.md` asserts a **causal** claim about *why*
the frozen σ=0.02 noisy regime fails: a "double-differentiation
second-derivative SNR / persistent-excitation boundary" and, verbatim,
"**No consistent estimator exists for the noisy regime at this
trajectory length and excitation level**". That is an estimator-class /
differentiation-operator attribution.

CALIB-GRID-002 (a *later* pre-registered lineage, merge sha
`e71d1915`) **falsified that attribution**. An estimator that *never*
double-differentiates the phase (the integral / weak form) still fails
the same frozen σ=0.02 regime at ≈0.95. CALIB-GRID-002's sha-pinned
`cg002/RESULTS.md` measures the regressor directly and shows the clean
`sin(θ_i−θ_j)` coupling signal sits **below the σ=0.02 measurement
noise on every edge (regressor SNR < 0.6, 0.085 on edge (0,2))
before any estimator touches the data**. The corrected, sha-pinned
attribution is therefore:

> **a class-independent regressor-level SNR floor at the frozen
> θ₀/record-length, NOT a differentiation-operator/estimator-class
> defect.** The double-differentiation operator made the error *worse*
> (16.6) but is not the cause.

Without this layer, a future lineage (#6+) reading `r1/RESULTS.md` as
ground truth inherits a **falsified premise** (it would chase an
estimator-class fix for a regressor-floor boundary). The forcing
function `test_superseded_claims_resolve_via_registry` fails closed if
any artifact references the superseded R1 claim/sha without resolving
this registry.

## SUPERSEDE-001 — enumerated artifacts (grep-evidenced, file:line)

### The exactly FOUR sha-pinned artifacts that ENCODE the stale claim

| # | Artifact | Line | Verbatim anchor |
|---|---|---|---|
| 1 | `r1/RESULTS.md` | 74 | `second-derivative SNR / persistent-excitation` |
| 1 | `r1/RESULTS.md` | 79 | `No consistent estimator exists for the noisy regime` |
| 2 | `r1/RESULTS.md` | 97 | `double-differentiation SNR boundary in the noisy regime` |
| 3 | `r1/RESULTS.json` | 100 | `coupling_estimator noise robustness / standardisation` (machine-readable `localized_refinement_targets` encoding the same estimator-class attribution for the noisy gates) |
| 4 | `r1/ATTEMPT.md` | 77 | `one regime gate now passes, three still fail` (anchors the R1 noisy attribution by reference into the lineage attempt record) |

(Artifact 1 = `r1/RESULTS.md` — the prose claim, two grep hits on lines
74 and 79; artifact 2 = the `r1/RESULTS.md` summary restatement on line
97; artifact 3 = `r1/RESULTS.json` machine-readable encoding; artifact
4 = `r1/ATTEMPT.md` lineage record.)

### The TWO downstream sha-pinned artifacts that CITE the stale claim

| # | Artifact | Line | Verbatim anchor |
|---|---|---|---|
| 5 | `identifiability/THRESHOLD_PROVENANCE.md` | 103 | `after double differentiation, measurement noise can inflate` (inherits R1's double-differentiation attribution as a design premise) |
| 6 | `cg002/PROVENANCE_002.md` | 55 | `CALIB-GRID-001 R1 RESULTS.md: the swept Savitzky–Golay verification` (cites R1's attribution directly) |

## Supersession relation (sha-pinned)

| Field | Value |
|---|---|
| `superseded_lineage` | `CALIB-GRID-001-R1` |
| `superseded_sha` | `a5527708833df308e67536aaa690b4f16e88dccd` (PR #751, R1 merge — verified commit ancestor) |
| `superseding_lineage` | `CALIB-GRID-002` |
| `superseding_sha` | `e71d1915233283452f3fb219aafabd2f19035371` (PR #757, CG002 merge — verified commit ancestor) |
| `superseding_artifact` | `research/calibration/grid_kuramoto/cg002/RESULTS.md` |
| Evidence anchor | CG002 ledger `ledger_sha256 = d0f89e24341b0995…` |

## What this record does *not* do

It does **not** edit, recompute or rewrite any frozen artifact.
`r1/RESULTS.md`, `r1/RESULTS.json`, `r1/ATTEMPT.md` and every other
sha-pinned file stay **byte-identical**. R1's `NEGATIVE` verdict and
its differential-class boundary record remain the true historical
record. Only the *causal attribution* of the noisy failure is
superseded **forward**: R1 stands as the differential-class boundary
record, CALIB-GRID-002 as the class-independent regressor-floor
boundary record. The historical record stays honest as-is.
