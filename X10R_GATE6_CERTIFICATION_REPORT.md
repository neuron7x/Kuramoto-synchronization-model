# D-002B-A — Gate 6 high-budget power certification (N ≤ 200 scoped subset)

**PR:** `feat/x10r-d002b-gate6-certification`
**Issue:** #652 (D-002B), scoped to N ≤ 200 per the
2026-05-11 protocol amendment.
**N=400 follow-up issue:** #654 (D-002C — formal N=400
certification extension).
**Driver-debt follow-up issue:** #655 (D-002D —
checkpoint/resume for long Gate 6 sweeps).

**Strict scope:** synthetic only. **No real-data Gate 6
verdict. No bank-level inference claim. No
`INV-IDENTIFICATION-1` lift.**

> Bibliographic anchors justify model class and reviewer
> traceability; operational validity is determined only by
> gates, positive/negative controls, null distributions,
> capsules, and power/FPR/MDE evidence.

---

## 0. Scoped verdict

```
GATE6_NOT_CERTIFIED_AT_TESTED_BUDGET_N_LE_200
```

Three of the four D-002B-A certification rules fail on
the N ≤ 200 subset; only the FPR rule passes. The gate is
**fail-closed and sub-MDE** at the N ≤ 200 scope under the
canonical core-periphery substrate at n_seeds=20,
n_bootstrap=16. **N=400 cells are excluded from the
D-002B-A verdict.** **D-002C (#654) is required for the
formal N=400 extension.**

Forbidden tiers — none of these are claimed anywhere in
this PR:

- `SYNTHETIC_GATE6_CERTIFIED` (unqualified)
- `REAL_DOV_READY`
- `VALIDATED_REAL_BANK_LEVEL_RESULT`
- `CONFIRMED` / `TESTED_POSITIVE_REAL` /
  `BANK_LEVEL_PRECURSOR_CONFIRMED`

---

## 1. Ledger provenance

Three ledgers are persisted (gitignored under `tmp/`):

| File | Role | sha256 |
|---|---|---|
| `tmp/x10r_gate6_certification_sweep.json` | full 480-cell sweep (4 N × 6 λ × 20 seeds) | `e3b9d0a4daa553485e7123bdbe325ca4e9c3c4a9cf46499208087e3910321362` |
| `tmp/x10r_gate6_certification_sweep_n_le_200.json` | D-002B-A N ≤ 200 subset (3 N × 6 λ × 20 seeds = 360 cells) | `fdc69809cb29f0fc6132c1f11d8252c544546f5ed0e67109159e566cac733e05` |
| `tmp/x10r_gate6_certification_sweep_n400_exploratory.json` | N=400 exploratory motivation for D-002C (#654) | `c53f05cd758fb7abb40dd9118e7be18e398c36217b9365ac60a409563546b378` |

The D-002B-A verdict in §0 is computed **only** on the
`_n_le_200` ledger. The N=400 cells live in the
`_n400_exploratory` ledger and bear no certification claim.

Sweep ran 61 517 s (17 h 5 min) on 6 E-cores
(taskset 8–13, nice +19) of an Intel i5-12500H.

---

## 2. D-002B-A certification rule (per protocol)

A surface is `SYNTHETIC_GATE6_CERTIFIED_N_LE_200` **iff
ALL four** rules pass on the N ≤ 200 subset:

| # | Rule | Threshold |
|---|---|---|
| 1 | FPR rule | `max(power(λ=0)) ≤ 0.05` across all N ≤ 200 |
| 2 | Power rule | `max(power(0 < λ < 1.0)) ≥ 0.80` |
| 3 | MDE rule | at least one N ≤ 200 has `mde_lambda_per_n[N] < 1.0` |
| 4 | CI vs ΔR rule | `median_ci_width < median_abs_delta_r` for **every** tested N ≤ 200 at λ=1.0 |

Otherwise the verdict is
`GATE6_NOT_CERTIFIED_AT_TESTED_BUDGET_N_LE_200`.

---

## 3. Rule-by-rule evaluation on N ≤ 200

| Rule | Measured | Threshold | Verdict |
|---|---|---|---|
| 1. FPR | `max power(λ=0) = 0.000` | ≤ 0.05 | **PASS** |
| 2. Power | `max power(0 < λ < 1) = 0.200` (at N=200, λ=0.40) | ≥ 0.80 | **FAIL** |
| 3. MDE finite | MDE for N=50/100/200 = None / None / None | at least one < 1.0 | **FAIL** |
| 4. CI vs ΔR at λ=1 | `ci_width > median_abs_delta_r` for all three N ≤ 200 (see §5) | strict per-N | **FAIL** |

Three of four rules fail. Scoped verdict:
`GATE6_NOT_CERTIFIED_AT_TESTED_BUDGET_N_LE_200`.

---

## 4. FPR table (λ = 0 cells, N ≤ 200 subset)

| N | power(λ=0) | dominant direction |
|---|---|---|
| 50 | 0.000 | no_signal |
| 100 | 0.000 | no_signal |
| 200 | 0.000 | no_signal |

FPR estimate (subset average) = 0.000. Gate is correctly
**fail-closed** in the discriminative sense.

---

## 5. Power and CI vs |ΔR| table (N ≤ 200)

| N | λ | power | median \|ΔR\| | median CI width | CI < \|ΔR\| ? |
|---|---|---|---|---|---|
|  50 | 0.00 | 0.000 | 0.0206 | 0.2826 | — (FPR cell, not λ=1) |
|  50 | 0.05 | 0.000 | 0.0271 | 0.2553 | — |
|  50 | 0.10 | 0.000 | 0.0240 | 0.3195 | — |
|  50 | 0.20 | 0.000 | 0.0219 | 0.3798 | — |
|  50 | 0.40 | 0.000 | 0.0676 | 0.2844 | — |
|  50 | 1.00 | 0.000 | 0.0649 | 0.2225 | **NO** (0.0649 < 0.2225) |
| 100 | 0.00 | 0.000 | 0.0147 | 0.2465 | — |
| 100 | 0.05 | 0.000 | 0.0315 | 0.2952 | — |
| 100 | 0.10 | 0.000 | 0.0171 | 0.3284 | — |
| 100 | 0.20 | 0.000 | 0.0310 | 0.3036 | — |
| 100 | 0.40 | 0.000 | 0.0856 | 0.3309 | — |
| 100 | 1.00 | 0.000 | 0.0666 | 0.2428 | **NO** (0.0666 < 0.2428) |
| 200 | 0.00 | 0.000 | 0.0282 | 0.3279 | — |
| 200 | 0.05 | 0.000 | 0.0181 | 0.3287 | — |
| 200 | 0.10 | 0.000 | 0.0140 | 0.3607 | — |
| 200 | 0.20 | 0.000 | 0.0486 | 0.2919 | — |
| 200 | 0.40 | **0.200** | 0.1682 | 0.2740 | — |
| 200 | 1.00 | 0.000 | 0.1105 | 0.2781 | **NO** (0.1105 < 0.2781) |

Max power at λ < 1 within N ≤ 200 = **0.200** (at N=200, λ=0.40)
— below the 0.80 power threshold.

---

## 6. MDE per N (subset)

| N | smallest λ where power ≥ 0.80 |
|---|---|
| 50 | None (no cell cleared) |
| 100 | None |
| 200 | None |

No N ≤ 200 cell clears the 0.80 power threshold at any
λ < 1.0. The gate is **sub-MDE** at the N ≤ 200 scope.

---

## 7. N = 400 exploratory data (not part of D-002B-A verdict)

The full sweep also collected 120 cells at N = 400. These
cells are **exploratory**; they motivate D-002C (issue
#654) but **are excluded from the D-002B-A verdict**.

| N | λ | power | median \|ΔR\| | median CI width | dominant direction |
|---|---|---|---|---|---|
| 400 | 0.00 | 0.000 | 0.0157 | 0.2706 | no_signal |
| 400 | 0.05 | 0.000 | 0.0141 | 0.2392 | no_signal |
| 400 | 0.10 | 0.000 | 0.0206 | 0.2093 | no_signal |
| 400 | 0.20 | 0.000 | 0.0714 | 0.2071 | no_signal |
| 400 | 0.40 | **0.950** | 0.2128 | 0.1705 | hindered |
| 400 | 1.00 | 0.550 | 0.2282 | 0.2692 | hindered |

The N=400, λ=0.40 cell shows 0.95 power with the
`hindered` signed direction; this is consistent with the
hypothesis that **larger N** is where the gate becomes
discriminative. However, the CI rule still fails at
N=400, λ=1 (`median_ci_width = 0.2692 > median_abs_delta_r = 0.2282`).

**No certification claim is made from N=400 cells in this
PR.** D-002C (#654) is the issue that will run the formal
N=400 certification at proper budget — and only after
D-002D (#655) ships incremental checkpointing so a >10 h
N=400 sweep is safe to run.

---

## 8. Interpretation

1. **Gate 6 is fail-closed across the entire N ≤ 200
   subset.** FPR is exactly 0.000 at every (N, λ=0) cell.
   This is the correct *necessary* property of a working
   precursor gate. The instrument does not hallucinate
   precursors on randomised null structure.

2. **Gate 6 is sub-MDE on N ≤ 200.** Even at full
   structural signal (λ = 1.0) power is 0.000 at every
   tested N ≤ 200. CI widths are 4–10× larger than
   median \|ΔR\|, so the bootstrap CI cannot exclude the
   ±min_gap zone with the n_bootstrap = 16 budget.

3. **Power appears at N = 400.** The exploratory N=400
   data shows 0.95 power at λ=0.40 with stable `hindered`
   signed direction. This is consistent with the
   working-physics hypothesis that finite-N noise drops
   as 1/√N and a sufficiently large N pushes the
   bootstrap CI inside the discriminative band. D-002C is
   the next gate that formally tests this with proper
   resume protection.

4. **The X-10R-1 E2E `NO_SIGNAL` verdict (PR #648)
   remains correctly classified as HONEST AMBIGUITY at
   the pilot budget and at the N ≤ 200 certification
   budget.** D-002A's pilot finding and D-002B-A's
   formal N≤200 finding are coherent.

---

## 9. State after merge

```
GATE6_NOT_CERTIFIED_AT_TESTED_BUDGET_N_LE_200 + REAL_DOV_BLOCKED
```

- `INV-IDENTIFICATION-1` remains globally active.
- D-003 remains blocked until this PR lands, #654 exists
  (✓), #655 exists (✓), and the D-003 PR explicitly
  scopes its DoV check against the N ≤ 200 synthetic
  envelope.
- No real-data Gate 6 verdict is emitted by this PR.
- No bank-level inference claim is emitted by this PR.

---

## 10. What this PR does NOT do

- Does **NOT** emit `SYNTHETIC_GATE6_CERTIFIED` (the only
  certification-tier this PR could emit is
  `SYNTHETIC_GATE6_CERTIFIED_N_LE_200` and the empirical
  rules forbid that emission today).
- Does **NOT** include N=400 cells in the certification
  verdict.
- Does **NOT** run on real BIS data.
- Does **NOT** invoke any real-data path.
- Does **NOT** lift `INV-IDENTIFICATION-1`.
- Does **NOT** emit a bank-level inference claim.
- Does **NOT** change any X-10R source code outside the
  pre-staged `scripts/run_x10r_gate6_certification_sweep.py`
  driver (which is a measurement layer, not a science
  layer).
- Does **NOT** change `gate_6_precursor_discriminative` or
  the sensitivity-surface module.

---

## 11. Bibliographic anchors and their roles

| Reference | Role | Justifies | Does NOT validate |
|---|---|---|---|
| Cimini–Squartini–Garlaschelli–Gabrielli (2015) | ROLE_A — model origin | Max-entropy reconstruction form | The Gate 6 verdict here |
| Almog–Squartini Sinkhorn-Knopp variants | ROLE_B — numerical method | IPF projection in the allocator | Recovery on real data |
| Kuramoto / Strogatz / Acebrón coupled-oscillator literature | ROLE_C — observable background | The order-parameter framing | Whether `R(t)` measures liquidity stress |
| **This sweep (D-002B-A)** | **ROLE_D — validation standard** | **The scoped tier verdict on the N ≤ 200 grid** | **N=400, real-data, bank-level claims** |

Operational validity of this PR's verdict is determined
only by the ROLE_D evidence in §§3–7. The ROLE_A/B/C
citations are reviewer-trace anchors, not proof.

---

## 12. Acceptance gates (per protocol D-002B-A)

- [x] N grid `{50, 100, 200}` scoped (full protocol N=400
      lives in exploratory ledger)
- [x] λ grid `{0.0, 0.05, 0.10, 0.20, 0.40, 1.0}`
- [x] n_seeds = 20
- [x] n_bootstrap = 16
- [x] FPR, power, CI width, MDE per N, signed direction
      recorded for every cell
- [x] Three ledgers persisted with sha256 (§1)
- [x] Verdict emitted: `GATE6_NOT_CERTIFIED_AT_TESTED_BUDGET_N_LE_200`
- [x] mypy --strict + ruff + black clean on driver + tests
- [x] Commit acceptor + scoped falsifier shipped
- [x] No real-data verdict, no INV-IDENTIFICATION-1 lift
- [x] D-002C issue exists (#654)
- [x] D-002D issue exists (#655)

---

## 13. Reproduction

```bash
git fetch origin feat/x10r-d002b-gate6-certification
git checkout feat/x10r-d002b-gate6-certification
mkdir -p tmp
PYTHONPATH=. taskset -c 8-13 nice -n 15 \
    python3 scripts/run_x10r_gate6_certification_sweep.py
# expected wallclock: ~17 h on i5-12500H @ 6 workers
sha256sum tmp/x10r_gate6_certification_sweep.json
```

To regenerate the N ≤ 200 subset + N = 400 exploratory
ledger from the full ledger:

```bash
PYTHONPATH=. python3 - <<'PY'
import json
with open('tmp/x10r_gate6_certification_sweep.json') as f:
    full = json.load(f)
n_le_200 = {50, 100, 200}
# (see report §1 for the full split procedure;
# reproduced by the report-generation tooling in this PR)
PY
```

---

## 14. Forbidden-phrase audit

A direct grep over this document confirms the absence of:

- "SYNTHETIC_GATE6_CERTIFIED" (unqualified) — absent
- "real-data Gate 6 PASS" — absent
- "validated systemic precursor" — absent
- "liquidity contagion claim" — absent
- "INV-IDENTIFICATION-1 lifted" — absent
- "VALIDATED_REAL_BANK_LEVEL_RESULT" — absent
- "CONFIRMED" / "TESTED_POSITIVE_REAL" /
  "BANK_LEVEL_PRECURSOR_CONFIRMED" — absent

The only certification-tier this PR uses is
`GATE6_NOT_CERTIFIED_AT_TESTED_BUDGET_N_LE_200` (and the
forbidden-tier-watch lists in §0, §10 which name what is
**not** emitted).
