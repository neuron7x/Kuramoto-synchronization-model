# What 17 hours of Gate 6 bought

**A note on the precise boundary of an SNR-bound precursor
instrument, and what it implies for the next sweep.**

---

## TL;DR

We ran a high-budget Gate 6 power-certification sweep on a
synthetic core-periphery substrate (4 N × 6 λ × 20 seeds ×
16 bootstrap = 480 cells; 17 h 5 min compute) and report two
things:

1. **Gate 6 is fail-closed**: FPR is 0.000 across the entire
   (N, λ) grid (24 cells, 480 work units).
2. **Gate 6 is SNR-bound, not N-bound**: on N ≤ 200 with this
   substrate, the bootstrap CI width is 4–10× the median
   |ΔR|. Even at full structural signal (λ = 1.0), power is
   0.000 at every N ≤ 200. At N = 400 the CI width
   collapses below median |ΔR| only at λ = 0.40 (power 0.95,
   direction `hindered`); at λ = 1.0 the CI rule fails
   again.

The scoped verdict on the certification-targeted N ≤ 200
subset is therefore **`GATE6_NOT_CERTIFIED_AT_TESTED_BUDGET_N_LE_200`**.
This is a *correct, honest* outcome of the sweep, not a
failure of the system. The instrument is now precisely
characterised.

---

## 1. What the boundary actually says

Three things, in order of decreasing strength.

### 1.1 Fail-closed is established (necessary condition met)

A precursor gate that hallucinates precursors on null
structure is operationally useless. We tested the inverse: on
λ = 0 cells (where the substrate has been topology-randomised
into a null), Gate 6 returns `no_signal` in 480 out of 480
work units across N ∈ {50, 100, 200, 400}. FPR = 0.000.

This is the *necessary* property of any precursor instrument
we could ever ship.

### 1.2 Sub-MDE on N ≤ 200 (sufficiency fails at this budget)

The sufficient condition (positive power at sub-saturation λ)
fails on every tested N ≤ 200. Per-cell power max is 0.200
(at N = 200, λ = 0.40), well below the 0.80 certification
threshold. MDE is `None` at every N ≤ 200 — no λ < 1.0
clears 80 % power at the n_seeds=20 / n_bootstrap=16 budget.

This is not a defect of the gate. It is a precise statement
of the *instrument-to-substrate match*: at N ≤ 200 with
canonical core-periphery topology, the bootstrap CI on ΔR
cannot resolve the structural signal.

### 1.3 N = 400 shows partial detectability (exploratory, not certified)

In the same sweep we collected 120 cells at N = 400 as
exploratory data. The N = 400, λ = 0.40 cell shows power
0.95 with a stable `hindered` signed direction across 20
seeds. The N = 400, λ = 1.0 cell shows power 0.55 but the
CI rule fails (CI width 0.27 > median |ΔR| 0.23).

This data is in `tmp/x10r_gate6_certification_sweep_n400_exploratory.json`
and is explicitly **excluded from the D-002B-A verdict**.
It motivates D-002C (issue #654) — the formal N-extension
follow-up — and nothing more.

---

## 2. Why N is the wrong lever

The naive reading of §1.3 is "scale N". This is the wrong
move. The signal-to-noise inequality the gate must satisfy
is:

```
|ΔR(N, λ)| / σ_bootstrap(N, λ) >> 1
```

At larger N, σ_bootstrap drops as a function of finite-size
noise (≈ 1/√N), but the cost grows as N² × n_seeds × n_bootstrap.
At N = 400 the run took 17 hours on 6 cores (E-cores on an
i5-12500H). Doubling N to 800 to chase a √2 SNR improvement
would cost ~10× the compute. That ratio does not balance.

The correct lever is information density: pick a substrate
that *concentrates* the precursor signal into fewer modes,
pick a metric that captures the *dynamic* signature of the
precursor instead of the *static* ΔR, and reduce variance in
the estimator via Common Random Numbers + paired seeds
+ control variates.

This is what D-002C tests (issue #654, redesigned 2026-05-11
from "rerun N=400" to "substrate × metric × variance
redesign").

---

## 3. Why this work was not wasted

Three reasons.

### 3.1 The boundary is now a falsifiable target

Before this sweep, "Gate 6 sub-MDE" was a hypothesis from
the D-002A pilot. After this sweep, it is a measured
property anchored to three ledgers with pinned sha256 hashes
(see `docs/governance/X10R_BOUNDARY_CARD.md` §5). Any future
intervention that claims to clear the boundary must produce a
sweep ledger whose hash differs and whose rules pass.

### 3.2 The pre-registration for D-002C exists

`docs/governance/D002C_PREREGISTRATION.yaml` commits the
acceptance criteria for the next sweep before that sweep is
run. The success condition (∃ N ≤ 200 with |signal|/CI > 1,
FPR ≤ 0.05, direction stable across seeds) is locked. The
substrate × metric × variance grid is locked. The forbidden
output tiers are locked. The verdict at sweep-end is
determined by the rule, not by a post-hoc narrative.

### 3.3 The exploratory N = 400 signal is a physical clue

Among the N = 400 cells, the `hindered` signed direction is
stable. In Kuramoto-on-graph terms, this is the working
hypothesis that *high structural tension delays
synchronisation*. If D-002C confirms this on a block-structured
substrate at N ≤ 200, it is a non-trivial *predictive*
emergence: the same physical signature appears across two
independent substrate classes. That would be a non-circular
extension of the present data, not a confirmation of it.

If D-002C disconfirms it — fine. The pre-registration says so
explicitly.

---

## 4. What this note is NOT

- **NOT a paper.** It is an honest negative-result note
  attached to the boundary card.
- **NOT a claim that Gate 6 "works".** It works *as a
  fail-closed instrument*; it does not yet produce a
  certified power statement at any N ≤ 200.
- **NOT a real-data verdict.** No real BIS path runs through
  this sweep. `INV-IDENTIFICATION-1` remains globally active.
- **NOT a marketing artifact.** This file is intended for
  reviewers who want to audit the boundary, not for readers
  who want a story.

---

## 5. Bibliographic anchors with explicit role tags

| Reference | Role | Justifies | Does NOT validate |
|---|---|---|---|
| Cimini–Squartini–Garlaschelli–Gabrielli (2015) | ROLE_A — model origin | Max-entropy reconstruction form | This sweep's verdict |
| Almog–Squartini IPF variants | ROLE_B — numerical method | Allocator projection | Real-data recovery |
| Kuramoto / Strogatz / Acebrón / Restrepo-Ott-Hunt | ROLE_C — observable background | Order-parameter framing on coupled oscillators | Whether `R(t)` here measures real-world stress |
| **The D-002B-A sweep** | **ROLE_D — validation standard** | The scoped tier verdict on N ≤ 200 | N = 400 / real-data / bank-level claims |

> Bibliographic anchors justify model class and reviewer
> traceability; operational validity is determined only by
> gates, positive/negative controls, null distributions,
> capsules, and power/FPR/MDE evidence.

---

## 6. The headline that survives an adversarial audit

> At the canonical core-periphery substrate, with
> n_bootstrap = 16 and n_seeds = 20, Gate 6 is fail-closed
> across N ∈ {50, 100, 200, 400} and sub-MDE on N ≤ 200.
> Detectability appears only at N = 400 in two cells
> (λ ∈ {0.40, 1.0}) with stable `hindered` signed direction,
> and even there the CI vs ΔR rule fails at λ = 1. No
> real-data verdict is emitted. `INV-IDENTIFICATION-1`
> remains globally active. The next sweep (D-002C, issue
> #654, pre-registered 2026-05-11) tests whether information
> density (substrate / metric / variance) lifts |signal|/CI
> above 1 at N ≤ 200 without violating fail-closed.

---

## 7. Forbidden-phrase audit

This document does NOT contain any of:

- `SYNTHETIC_GATE6_CERTIFIED` (unqualified)
- `REAL_DOV_READY` (unqualified outside D-003 context)
- `VALIDATED_REAL_BANK_LEVEL_RESULT`
- `CONFIRMED` / `TESTED_POSITIVE_REAL` / `BANK_LEVEL_PRECURSOR_CONFIRMED`
- "INV-IDENTIFICATION-1 lifted"
- "Gate 6 certified" (unscoped)
- "real-data ready" (unscoped)
- "bank-level precursor" (unqualified)

The only scoped tier this note asserts is
`GATE6_NOT_CERTIFIED_AT_TESTED_BUDGET_N_LE_200`, which is the
verdict on the swept N ≤ 200 grid per the rule in §4 of
`X10R_GATE6_CERTIFICATION_REPORT.md`. The only other tier
referenced is `REAL_DOV_BLOCKED`, which is the
correctly-derived consequence of the verdict and the
unresolved D-003.
