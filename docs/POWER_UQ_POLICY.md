<!-- Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab) -->
<!-- SPDX-License-Identifier: MIT -->
# Power, Effect-Size & Uncertainty Policy (RES-010)

Status: ACTIVE · Owner: remediation/wave8 · Scope: FLAGSHIP-RQ-001

- **Report (evidence):** `artifacts/research/power_uq_report.json`
- **Gate (enforcement):** `scripts/ci/check_power_uq.py`
- **Tests:** `tests/ci/test_power_uq.py`

This is the human-readable contract behind the machine-enforced power gate. It
governs how uncertainty is quantified and reported for the flagship research
question, and — critically — when a **binary claim must be refused**.

---

## 1. What the flagship outcome is (and is not)

FLAGSHIP-RQ-001 is an **infrastructure** question. Its outcome is an **integer
defect count** `D_marginal` — the number of latent first-party import defects
that the clean-archive wheel-contract check surfaces on the frozen snapshot and
that no pre-existing CI gate catches.

It is **NOT** a market return. There is no Sharpe, no PnL, no edge, no
out-of-sample alpha. The analysis is adapted honestly to a count outcome; any
review that expects a return-based power calculation is looking at the wrong
category (`PRODUCT_CATEGORY.md`, `FORBIDDEN_CLAIMS.md`).

On the pinned snapshot: `D_marginal = 70` defect rows across **66 distinct
modules**, collapsing to **11 independent import-root clusters**. Every baseline
(existing suite, ablated, shuffled, naive) catches `0` — the full 70 is marginal.

---

## 2. Smallest Effect of Interest (SESOI)

**SESOI = 1** genuinely-missed defect (`direction: at_least`).

The smallest effect worth acting on is a single unpackaged-namespace import that
raises `ModuleNotFoundError` on clean install and that no pre-existing gate
flags. Below `D_marginal = 1` the flagship check adds nothing. The SESOI is
pinned to the **preregistered margin** (`prereg_margin = 1`), not chosen after
seeing the data. Post-hoc adjustment voids the preregistration.

The report leads with an **effect size and an interval**, never a bare p-value.

---

## 3. Uncertainty for a count outcome

Each packaged module is treated as a Bernoulli detection trial; `D` is their
sum. We report several intervals, deliberately, because the honest answer
depends on the dependence assumption:

| Quantity | Method | 95% interval |
|---|---|---|
| `D` (rows) | exact Poisson (Garwood) | `[54.57, 88.44]` |
| `D` (independent clusters, n=11) | exact Poisson (Garwood) | `[5.49, 19.68]` |
| `D` (rows) | cluster bootstrap (20 000×, seed 20260719) | `[16.0, 154.0]` |
| detection rate `p = 66/1517` | Clopper–Pearson exact binomial | `[0.0338, 0.0550]` |

The **PRIMARY** report is the effect size **plus** interval — not a p-value.

### Dependence caveat (block / cluster)

The 70 module failures are **not independent**. They cluster on **11 distinct
import roots** (`research`=41, `runtime`=13, `geosync_hpc`=5, … ). One missing
top-level package fails every module that imports it at once, so the effective
number of independent defects is **~11, not 70**. Row-level intervals therefore
*understate* uncertainty; the **cluster-adjusted Poisson (on 11)** and the
**cluster bootstrap** are the honest-uncertainty framings.

### Census, not sample

This is a **census**: every packaged first-party module is enumerated, not
sampled from a larger universe. For the pinned snapshot, `D = 70` is **exact** —
a census carries **no sampling uncertainty**. The Poisson / binomial / bootstrap
intervals above are therefore **superpopulation / illustrative** devices, not
design-based sampling CIs. The genuine residual uncertainty is
**measurement / reproducibility**, addressed in §5.

---

## 4. Power / adequacy verdict

The count analysis is **adequately powered** with respect to the SESOI: every
interval places its lower bound far above 1 (min lower bound = 5.49 clusters /
16 rows). Power to detect `D >= 1` is effectively 1. `underpowered = false`,
`power_gate = PASS`.

**Adequate statistical power does not license a binary flagship verdict.** Power
here concerns the *magnitude* of the count; the binary verdict is gated
separately by reproducibility (§5).

---

## 5. Underpowered-refusal rule

**REFUSE any binary `SUPPORTED` / `REJECTED` claim** if **any** of:

1. a primary interval includes the SESOI-null “no marginal defect” (lower bound
   `< 1`); **or**
2. the census / sample is too small to resolve the SESOI; **or**
3. the same-snapshot reproducibility leg is unverified.

On the pinned snapshot: (1) **false**, (2) **false**, (3) **true**. Reruns at
HEAD are bit-identical (74 == 74), but the committed snapshot-S artifact reports
70 under a *different* `wheel_sha` (stale-vs-HEAD) and no same-S rerun was run.

**Decision: `BINARY_CLAIM_WITHHELD` → verdict `INSUFFICIENT_EVIDENCE`.** The
effect is large and well-bounded (**not** underpowered), but the RES-008
reproducibility gap keeps it short of a binary conclusion. This is exactly
consistent with RES-008 (`comparison_report.json` = `INSUFFICIENT_EVIDENCE`).

---

## 6. Sensitivity analysis

- **Dependence structure:** rows `[54.57, 88.44]`, clusters `[5.49, 19.68]`,
  bootstrap `[16.0, 154.0]` — every lower bound `>> 1`. The conclusion
  “marginal detection `>>` SESOI” is **insensitive** to the counting unit.
- **Snapshot choice:** S = 70 vs HEAD = 74 (drift 4, 5.7 %) — both `>>` SESOI.
  The magnitude conclusion is robust; the drift is a *reproducibility* issue
  (drives the withheld verdict), not a magnitude issue.
- **Detection-rate denominator `N`:** the rate’s lower bound stays `> 0` across
  plausible `N`; the count-based effect size needs no `N` and is unaffected.

---

## 7. What the gate enforces (fail-closed)

`scripts/ci/check_power_uq.py` returns **RED (non-zero)** iff **any**:

1. **binary-while-underpowered** — a binary `SUPPORTED`/`REJECTED` verdict while
   `power_adequacy.underpowered` is true;
2. **no effect-size + interval** — missing `effect_size.point_estimate` or no
   interval with numeric `lower`/`upper`;
3. **power field missing** — no `power_adequacy` block with `power_gate` and
   `underpowered`;
4. **binary-while-unreproducible** — a binary `SUPPORTED` claim while
   `reproducibility_verified_at_S` is not true (RES-008 consistency guard).

Exit codes: `0` pass · `1` policy violation · `2` missing/malformed report
(fail-closed). `INSUFFICIENT_EVIDENCE` and `WITHHELD` are **not** binary tokens.

---

## 8. Honesty boundary

The effect size is real and large, and this report **must not** be rewritten
into a binary “flagship proven” claim. The census removes sampling uncertainty
but not the measurement/reproducibility caveat; until the same-snapshot
reproducibility leg is verified, the verdict stays `INSUFFICIENT_EVIDENCE`.
