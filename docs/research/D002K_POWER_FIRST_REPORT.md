# D-002K-P4 — Power-First Gate Before the Event-Conditioned Benchmark Run

**Node:** `D002K-P4` · **Phase:** P4 · **Parent:** `D002K-P3`
**Decision:** `POWER_GATE_REFUSED_UNDERPOWERED` · **canonical_run_authorized:** `false`
**Schema:** `D002K-POWER-DESIGN-v1` / `D002K-POWER-SUMMARY-v1`

This document is the human-readable companion to
`artifacts/d002k/power/power_design_v1.json`. It computes definitions
and arithmetic only. **It scores no data, runs no model, and executes
no canonical run.**

---

## §0 Why power-first

D-002H REFUSED because a sub-threshold signal was run under an
*insufficient grid power* budget. D-002I diagnosed that root cause
(`n_seeds=20` vs median `n_min≈93`). D-002J-P7 then made the lesson a
hard gate: it computed power *before* authorising any canonical run and
correctly REFUSED on `effect_too_small` (102 cells, Bonferroni
α=0.05/102=4.9e-4, `n_min ∈ {150,235,417}` vs feasible cap 100). Running
a blind or underpowered sweep is the exact failure this stack exists to
prevent. D-002K-P4 applies the same discipline to the *narrowed* D-002K
design: it asks, honestly, whether the K-P0/P1/P2/P3-locked 3-hypothesis
event-conditioned design can reach power ≥ 0.8 for a plausible,
conservative effect before any P5 run is permitted.

A `POWER_GATE_REFUSED_UNDERPOWERED` verdict here is **the gate working,
not breaking** — a retained truthful negative, identical in canon to
D-002J-P7.

---

## §1 Effect-size prior (honest, conservative, explicitly NOT inflated)

**Assumed standardised effect: Cohen's d = 0.80.**

Provenance (K-P0 `effect_prior_source` rule — only literature-implied
magnitude or a conservative bound is admissible; inflation forbidden):

- Copeland, Duffie & Yang, *"Reserves Were Not So Ample"* (2021) — the
  September-2019 SOFR/repo spike (CW3 class).
- Avalos, Ehlers & Eren, *BIS Quarterly Review* (Dec-2019) — same repo
  dislocation.
- Bank of England, *"The Bank's response to the gilt market crisis"*
  (Dec-2022) — the 2022 LDI gilt episode (CW5 class).

These report pre/post standardised funding-stress shifts of **many
baseline standard deviations** — large-to-extreme standardised effects
for the `pre_post_standardized_mean_shift` metric family. The honest
move is **not** to plug in those large point estimates (that would
trivially over-power and is the precise self-deception the gate exists
to prevent). The prior is pinned to the **conservative lower edge**:
d = 0.80, the conventional floor of a "large" Cohen's d (Cohen 1988).
This is deliberately the *smallest* value the literature could justify;
it can only push the gate toward REFUSED, never toward a manufactured
PASS. `not_inflated: true` by construction. Using the literature point
estimate (multiples of σ) would be inflation and is forbidden.

---

## §2 Alpha policy (Bonferroni denominator = 3) — anti-laundering

α_per = 0.05 / (n_windows × n_primary_metrics) = 0.05 / (3 × 1)
= **0.016667**.

**The anti-laundering paragraph (the ethical spine of D-002K).** The
smaller Bonferroni denominator (3, vs D-002J-P7's 102) is the
**legitimate consequence of there being honestly fewer PRE-REGISTERED
hypotheses** — K-P0 locked exactly 1 mechanism
(`funding_liquidity_rollover`) × 3 windows (CW3/CW4/CW5) × 1 primary
metric (`pre_post_standardized_mean_shift`) = 3 hypotheses. It is **NOT
alpha relaxation at a fixed hypothesis count.** D-002J-P7's
α = 0.05/102 = 4.9e-4 was *correctly refused* and is **NOT being
undone**: fewer hypotheses ⟹ a legitimately smaller denominator;
loosening alpha at a fixed hypothesis count would be forbidden
laundering. Narrowing scope is not relaxing statistics. D-002K does not
un-refuse D-002J. The design JSON records this distinction explicitly
under `alpha_policy.denominator_derives_from` and
`comparison_to_d002j_p7.narrowing_is_scope_not_alpha_relaxation`.

---

## §3 n_min computation + test family

**Test family.** The K-P3 confirmatory contrast is
`Delta = metric_crisis − mean(metric over the 5 K-P2 matched placebos)`
per crisis window. This is a two-independent-group standardised-mean
comparison: crisis arm size `n_crisis`, reference (matched-placebo) arm
size `n_placebo_ref = 5`. Two-sided power at level α_per:

```
ncp   = d / sqrt(1/n_crisis + 1/n_placebo_ref)
power = Phi(ncp − z_{1−α_per/2})
```

The small-n exact non-central-t power is strictly *lower* than this
normal approximation, so the normal bound is **optimistic** — a REFUSE
under it is conservative and honest.

**n_min (design transparency).** Smallest crisis-side replicate count
(reference arm scaling at the K-P2 1:5 ratio) for power ≥ 0.8 at α_per
for d = 0.80: **n_min = 20 crisis-side replicates per window**.

**Power at the feasible sample.** At the feasible event-conditioned
sample (n_crisis = 1, n_placebo_ref = 5) for d = 0.80:
**power = 0.0481** (false-negative risk 0.9519). The minimum detectable
effect at the feasible sample for power 0.8 is **Cohen's d ≈ 3.54** — an
implausibly large standardised effect, well above any conservative
prior.

---

## §4 Feasibility (binding constraint = effect detectability)

D-002K is **real-public-data event-conditioned**, not a synthetic 102-
cell sweep. Runtime is trivial; it is **not** the binding constraint.
The binding constraint is **effect detectability under an irreducible
sample**: CW3 (US repo spike 2019), CW4 (COVID dash-for-cash 2020) and
CW5 (UK gilt LDI 2022) are *unique historical events*. Each crisis
window has exactly **one** realisation in recorded history; it cannot be
re-run, re-seeded or resampled the way D-002J-P7's synthetic substrates
could (its feasible cap was `n_seeds=100`). The crisis-side replication
count is therefore physically capped at **n1 = 1 per window** — a hard
data-availability bound, the *most generous* value physically available
(one realisation per event), and explicitly **not** inflated to
manufacture a PASS.

---

## §5 DECISION

**`POWER_GATE_REFUSED_UNDERPOWERED`.**

At the K-P0-locked α_per = 0.016667 with the conservative honest effect
prior d = 0.80, the crisis-vs-matched-placebo-reference contrast reaches
power **0.0481** at the feasible event-conditioned sample (n1 = 1,
n2 = 5) — far below the K-P0 power target of 0.8. The
design-transparency n_min for power ≥ 0.8 is 20 crisis-side replicates
per window, which an event-conditioned design **cannot supply** (a
crisis window happens once). `canonical_run_authorized = false`. P5 is
forbidden.

Honest narrowing of *scope* (Bonferroni 102 → 3, raising α_per from
4.9e-4 to 0.016667) was insufficient because the binding constraint is
**structural underpower of an irreproducible single-realisation
event-conditioned design**, not multiple-testing. No amount of
K-P0-conformant alpha or conservative effect prior closes that gap.

---

## §6 Refused — exact axis and the only legal forward motion

- **Refused axis:** `effect_too_small_event_conditioned`.
- **Forward motion is a fresh `D-002L` pre-registration.** NOT P5
  (forbidden), NOT a D-002J resurrection. A future lineage must design
  *against this axis* — e.g. a windowed within-event observable that
  yields more than one independent crisis-side observation, or a
  theoretically anchored effect target that an event-conditioned design
  can actually detect at n1 = 1.
- This negative is **retained verbatim** as a truthful artifact, in the
  same canon as D-002J-P7 and D-002J-P1A.

---

## §7 No-rescue / frozen reminder

- **D-002J stays `TERMINAL_REFUSED` and retained.** D-002K-P4 does not
  rescue, reopen, or amend D-002J. D-002J-P7's capsule is byte-exact
  unchanged and remains in `rejected_nodes_retained`.
- **D-002J + K-P0 + K-P1 + K-P2 + K-P3 are FROZEN byte-exact.** This PR
  edits none of: `artifacts/d002j/**`,
  `artifacts/d002k/{prereg,observables,placebo,metrics}/**`,
  `docs/governance/D002J_PREREGISTRATION.yaml`,
  `docs/governance/D002K_PREREGISTRATION.yaml`.
- No data scoring, no model run, no canonical sweep, no systemic-risk
  prediction, no bank-level claim. Power **design** only.
