# X-10R Boundary Card

**Class.** Reproducibility-grade transparency artifact.
**Date.** 2026-05-11.
**Scope.** Synthetic Gate 6 instrument calibration, X-10R-1
country-level reconstruction. No real-data verdict. No
bank-level inference claim.
**Hard invariant.** `INV-IDENTIFICATION-1` globally active.

> Bibliographic anchors justify model class and reviewer
> traceability; operational validity is determined only by
> gates, positive/negative controls, null distributions,
> capsules, and power/FPR/MDE evidence.

---

## 1. Single-page state

| Item | Value |
|---|---|
| Scoped state | `GATE6_NOT_CERTIFIED_AT_TESTED_BUDGET_N_LE_200 + REAL_DOV_BLOCKED` |
| `INV-IDENTIFICATION-1` | Globally active. Not liftable by any artifact below. |
| Real-data Gate 6 verdict | NOT emitted. |
| Bank-level inference claim | NOT emitted. |
| Forbidden tier `VALIDATED_REAL_BANK_LEVEL_RESULT` | NOT emitted. |

---

## 2. The four landed claims

| ID | Claim | Tier | Anchor |
|---|---|---|---|
| D-001 | `allocate_weights` row/col L1 ≤ 0.05 in ≥ 3/4 Cimini-calibrated densities (`sigma=1.0, N=80, seed=42`); total mass conserved to relative drift 1e-7 | `D001_FULLY_REPAID` | PRs #649 + #650 merged |
| D-002A | Gate 6 sensitivity-surface infrastructure + pilot at `n_bootstrap=4, n_seeds=5`; FPR = 0.000, MDE = None on N ∈ {50, 80, 120}; gate is fail-closed and sub-MDE at pilot budget | `D002A_PILOT_INFRASTRUCTURE_MERGED` | PR #651 merged (sha `e782f22`) |
| D-002B-A | High-budget certification scoped to N ≤ 200; FPR PASS (0.000), power FAIL (0.200 < 0.80), MDE finite FAIL, CI<\|ΔR\|@λ=1 FAIL | `GATE6_NOT_CERTIFIED_AT_TESTED_BUDGET_N_LE_200` | PR #656 |
| CI infra | python-fast-tests job-level `timeout-minutes` 20 → 25 | (CI hygiene) | PR #653 merged (sha `18c7a57`) |

---

## 3. Sweep parameters that produced the D-002B-A verdict

| Parameter | Value |
|---|---|
| N grid | `(50, 100, 200, 400)` (full grid swept; verdict scoped to N ≤ 200) |
| λ grid | `(0.0, 0.05, 0.10, 0.20, 0.40, 1.0)` |
| n_seeds | 20 |
| n_bootstrap | 16 |
| substrate seed | 42 (canonical core-periphery, `core_frac=0.30`) |
| executor | `ProcessPoolExecutor`, 6 E-cores (i5-12500H), `taskset 8-13`, `nice +19` |
| wallclock | 61 517 s (17 h 5 min) |
| total cells | 480 |

---

## 4. The certification rule applied to N ≤ 200

A surface is `SYNTHETIC_GATE6_CERTIFIED_N_LE_200` iff ALL four:

| # | Rule | Threshold | Measured | Verdict |
|---|---|---|---|---|
| 1 | FPR | `max(power(λ=0))` ≤ 0.05 | 0.000 | PASS |
| 2 | Power | `max(power(0 < λ < 1))` ≥ 0.80 | 0.200 (at N=200, λ=0.40) | FAIL |
| 3 | MDE finite | ∃ N ≤ 200 with `mde_lambda_per_n[N]` < 1.0 | None at every N ≤ 200 | FAIL |
| 4 | CI vs \|ΔR\| | `median_ci_width` < `median_abs_delta_r` for EVERY N ≤ 200 at λ=1 | CI dominates \|ΔR\| at every N ≤ 200 | FAIL |

Otherwise `GATE6_NOT_CERTIFIED_AT_TESTED_BUDGET_N_LE_200`.

Three of four rules fail → verdict `GATE6_NOT_CERTIFIED_AT_TESTED_BUDGET_N_LE_200`.

---

## 5. Three ledger SHA256

All ledgers gitignored under `tmp/`; hashes pinned here so any
reviewer can `sha256sum` against this card.

| File | sha256 |
|---|---|
| `tmp/x10r_gate6_certification_sweep.json` | `e3b9d0a4daa553485e7123bdbe325ca4e9c3c4a9cf46499208087e3910321362` <!-- pragma: allowlist secret --> |
| `tmp/x10r_gate6_certification_sweep_n_le_200.json` | `fdc69809cb29f0fc6132c1f11d8252c544546f5ed0e67109159e566cac733e05` <!-- pragma: allowlist secret --> |
| `tmp/x10r_gate6_certification_sweep_n400_exploratory.json` | `c53f05cd758fb7abb40dd9118e7be18e398c36217b9365ac60a409563546b378` <!-- pragma: allowlist secret --> |

---

## 6. N=400 exploratory data (NOT in any verdict)

Surfaced in `_n400_exploratory.json` only. Motivates D-002C
issue #654; bears no certification claim.

| N | λ | power | median \|ΔR\| | median CI width | direction |
|---|---|---|---|---|---|
| 400 | 0.00 | 0.000 | 0.0157 | 0.2706 | no_signal |
| 400 | 0.05 | 0.000 | 0.0141 | 0.2392 | no_signal |
| 400 | 0.10 | 0.000 | 0.0206 | 0.2093 | no_signal |
| 400 | 0.20 | 0.000 | 0.0714 | 0.2071 | no_signal |
| 400 | 0.40 | **0.950** | 0.2128 | 0.1705 | **hindered** |
| 400 | 1.00 | 0.550 | 0.2282 | 0.2692 | hindered |

Two cells show non-zero power with consistent `hindered`
signed direction; the CI rule still fails at λ=1. Read as
motivation for the D-002C redesign, not as evidence-grade
finding.

---

## 7. Claim tier lattice

```
INSTRUMENTED  (X-10R-1 epic close, 2026-05-10)
      │
      ├── D001_FULLY_REPAID  (operational regime)
      │
      ├── D002A_PILOT_INFRASTRUCTURE_MERGED  (pilot calibration)
      │
      ├── GATE6_NOT_CERTIFIED_AT_TESTED_BUDGET_N_LE_200
      │       (high-budget scoped to N ≤ 200, this PR)
      │
      ├── REAL_DOV_BLOCKED  (until D-003 returns WITHIN)
      │
      └── (D-002C, D-002D, D-003 pending)

FORBIDDEN (no artifact below this card emits any of these):
  SYNTHETIC_GATE6_CERTIFIED  (unqualified)
  REAL_DOV_READY  (until D-003 returns WITHIN)
  VALIDATED_REAL_BANK_LEVEL_RESULT
  CONFIRMED / TESTED_POSITIVE_REAL / BANK_LEVEL_PRECURSOR_CONFIRMED
  "INV-IDENTIFICATION-1 lifted"
```

---

## 8. Open follow-ups

| Issue | Title | Blocker |
|---|---|---|
| #654 | D-002C — Signal Amplification Sweep (substrate × metric × variance) | D-002B-A merge + D-002D shipped |
| #655 | D-002D — checkpoint/resume for long Gate 6 sweeps | D-002B-A merge |
| (PR pending) | D-003 — real BIS DoV-only dry run | D-002B-A merge |

---

## 9. What the card is NOT

This card is not a paper, not a system-level claim, not a
marketing artifact. It is a single-page record that a
reviewer can hash, diff, and falsify. Every numeric here
traces to a ledger sha256; every verdict here is a rule
evaluation on a deterministic computation; every forbidden
phrase is enforced absent by the acceptor's audit cert.

If a reader wants the long-form: see
`X10R_HONEST_MINIMUM_PROGRESS_REPORT.md` (snapshot) and
`X10R_GATE6_CERTIFICATION_REPORT.md` (the empirical D-002B-A
report).

---

## 10. Reproducibility one-liner

```bash
git fetch origin && \
git log origin/main --oneline | head -10 && \
sha256sum tmp/x10r_gate6_certification_sweep*.json
```

The boundary moves only when:
- a new sha256 lands in §5, AND
- the rule evaluation in §4 changes, AND
- the new tier is one of the allowed scoped tiers in §7.

No other path advances the boundary.
