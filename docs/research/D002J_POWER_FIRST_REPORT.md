# D-002J-P7 — Power-First Canonical-Run Gate Report

**Phase:** D002J-P7
**Decision:** `POWER_GATE_REFUSED_UNDERPOWERED`
**canonical_run_authorized:** `false`
**Refused axis:** `effect_too_small`
**Parent:** D002J-P6 (`NULL_HIERARCHY_READY`)
**Artifacts:** `artifacts/d002j/power/power_report_v1.json`, `artifacts/d002j/power/power_summary_v1.json`

> This gate's whole purpose is to refuse a blind canonical sweep. The
> honest computation REFUSES. A truthful `POWER_GATE_REFUSED_UNDERPOWERED`
> is a scientific **win**, not a failure to fix — the same canon as
> D-002H REFUSED and D-002J-P1A REJECTED. Alpha was not loosened, the
> effect-size prior was not inflated, the cell grid was not shrunk.

---

## §0 Why power-first

D-002H REFUSED was diagnosed by D-002I (H_I3 CONFIRMED) as a **sub-threshold
signal run under insufficient grid power**: the canonical sweep used
`n_seeds = 20` against a median `n_min ≈ 93` at the Bonferroni-corrected
level `α = 0.05/216 = 2.31e-4`. D-002H *ran the sweep blind* — it never
asked, before spending the budget, whether power ≥ 0.8 was even reachable.

P7 exists so the D-002J lineage does **not** repeat that mistake. P7 is a
power-**design** gate placed *before* any canonical execution (P8). It
computes, per canonical cell, the minimum detectable effect (MDE), the
`n_min` for power ≥ 0.8, the multiple-testing-corrected α, a
runtime-budget projection grounded by a *measured* per-sim probe, and the
false-negative risk under a feasible budget cap — and it **refuses** if
the realistic budget cannot reach power ≥ 0.8 for the honest effect-size
priors.

## §1 Effect-size priors (honest, P4-sourced — no invention)

The only honest effect-size priors available are the P4 positive-control
ground-truth magnitudes. Each P5 substrate declares its P4 analogue in
`positive_control_analogues`; the prior is sourced from that control's
`pass_threshold.value` and mapped to a conservative standardized Cohen's
d via a documented, **monotone, shrink-only** attenuation. The attenuation
exists because D-002I diagnosed that the realistic per-cell
substrate-vs-null separation is markedly *sub-threshold* relative to the
idealized synthetic SNR planted in the controls; using the raw synthetic
z would trivially over-power and is exactly the self-deception D-002I
named. The attenuation can only *shrink* the effect, so it can only push
the gate toward REFUSED — never toward a manufactured PASS.

| P5 substrate | P4 source control | control_class | P4 pass magnitude | Cohen's d prior |
|---|---|---|---|---|
| `funding_liquidity_rollover` | `PC1_LIQUIDITY_SHOCK_INJECTION` | `liquidity_shock` | z = 5.0 | **0.50** |
| `cross_exposure_contagion_proxy` | `PC2_CONTAGION_CASCADE_INJECTION` | `contagion_cascade` | cascade = 0.30 | **0.30** |
| `volatility_credit_spread_regime` | `PC4_MARKET_WIDE_VOLATILITY_REGIME_SWITCH` | `volatility_regime_switch` | ratio = 2.0 | **0.40** |

A substrate whose declared P4 analogue is absent from the P4 manifest is
reported as a phase-coupling gap and fails closed — it is **never**
fabricated.

## §2 Alpha policy + Bonferroni denominator derivation

The multiple-testing correction is **Bonferroni**, the same correction
*class* that gave D-002H its `α = 0.05/216`. The denominator is the
explicit canonical-cell count:

```
Σ over the 3 P5 substrates of (applicable P6 nulls × P5-declared P2 windows × P5 metrics)
  funding_liquidity_rollover       : 6 nulls × 3 windows × 2 metrics = 36
  cross_exposure_contagion_proxy   : 7 nulls × 3 windows × 2 metrics = 42
  volatility_credit_spread_regime  : 6 nulls × 2 windows × 2 metrics = 24
  ----------------------------------------------------------------------
  TOTAL                                                              = 102 canonical cells
```

**Bonferroni α = 0.05 / 102 = 4.90e-4.**

(The applicable-null counts come from P6 `applicable_substrates`; the
windows from each P5 substrate's declared `crisis_windows` ⊆ the P2
crisis-window registry; the metrics from each P5 substrate's
`observable_outputs`. This is phase-coupling P7 → {P5, P6, P2}.)

## §3 Per-cell power table

Test family: a permutation / two-sample comparison of a scalar substrate
detection statistic against its null-surrogate distribution. Under the
large-sample normal approximation,
`n_min = ⌈ 2·((z_{1−α/2} + z_{power}) / d)² ⌉` and
`MDE = (z_{1−α/2} + z_{power})·√(2/n)` (textbook Cohen / Lehr; scipy
supplies the Gaussian quantiles exactly — deterministic, no clipping).

| substrate (all cells in group identical) | Cohen's d | n_min @ power 0.8, α=4.90e-4 | MDE @ feasible cap | power @ n_min |
|---|---|---|---|---|
| `funding_liquidity_rollover` (36 cells) | 0.50 | **150** | 0.612 | 0.801 |
| `volatility_credit_spread_regime` (24 cells) | 0.40 | **235** | 0.612 | 0.802 |
| `cross_exposure_contagion_proxy` (42 cells) | 0.30 | **417** | 0.612 | 0.801 |

**n_min distribution over all 102 cells:** min **150**, median **235**,
p90 **417**, max **417**.

The full 102-row per-cell table is in
`artifacts/d002j/power/power_report_v1.json` (`per_cell`).

## §4 Runtime budget (measured, not guessed)

A tiny local timing probe of one P5
`FundingLiquidityRolloverSubstrate.simulate()` call (one warmup discarded,
median of 7 timed calls) measured **per-sim ≈ 4.3e-5 s** wallclock.

| projection | assumption | hours |
|---|---|---|
| local | 16-core box @ 70% parallel efficiency | **≈ 0.05 h** |
| cloud | GCP c3-highcpu 88-core, **CPU-bound (NOT GPU)**, $300 GCP credit context @ 85% | **≈ 0.01 h** |

**Runtime is NOT the binding constraint.** The full canonical sweep at
`n_seeds = 100`, `n_shuffles = 5000` over 102 cells projects to well under
an hour locally. The refusal is therefore *not* a budget-infeasibility
refusal — it is purely an effect-size refusal (see §5–§7).

## §5 Refusal rule (verbatim)

> POWER-FIRST FAIL-CLOSED RULE: `canonical_run_authorized` is True IFF,
> for EVERY designated canonical benchmark cell,
> `n_min(effect_prior, alpha_bonferroni, power=0.8) ≤ feasible_cap_n_seeds`
> AND the total runtime budget at `feasible_cap_n_seeds` is finite. The
> effect-size prior comes ONLY from P4 positive-control ground-truth
> magnitudes under a documented shrink-only attenuation; alpha is the
> Bonferroni split over the explicit canonical-cell count; the cell grid
> is the full P5×P6×P2×metric product. If any benchmark cell has
> `n_min > feasible_cap_n_seeds` the gate emits
> `POWER_GATE_REFUSED_UNDERPOWERED`, status `TERMINAL_REFUSED`,
> `canonical_run_authorized` False, halts the lineage at P7 (next legal =
> a fresh D-002K pre-registration), and retains this report as a truthful
> negative artifact. The gate NEVER loosens alpha, inflates the effect
> prior, or shrinks the grid to manufacture a PASS — that is the exact
> self-deception D-002I diagnosed as the D-002H root cause.

**feasible_cap_n_seeds = 100.** Justification: D-002H ran at `n_seeds = 20`
and REFUSED; D-002I diagnosed the median `n_min ≈ 93`. The cap of 100 is
set *just above* the D-002I median anchor (93) and 5× the D-002H budget
(20) — the most generous per-cell budget that is still
runtime-affordable. It is **not** inflated to manufacture a PASS.

## §6 Decision + canonical_run_authorized

**Decision: `POWER_GATE_REFUSED_UNDERPOWERED`.**
**`canonical_run_authorized: false`.**

All **102 / 102** canonical cells have `n_min ∈ {150, 235, 417}`, every
one above `feasible_cap_n_seeds = 100`. Equivalently: the **global MDE at
the feasible cap is 0.612**, and even the *largest* honest effect-size
prior (d = 0.50 for `funding_liquidity_rollover`) is *below* that MDE — so
the budget cannot detect even the strongest substrate's honest effect at
power ≥ 0.8 under the Bonferroni-corrected α. The **false-negative risk at
the capped budget is ≈ 0.91** for the worst cell — this is precisely the
D-002H blind spot, now quantified rather than discovered after a wasted
sweep.

The lineage **halts at P7**. The P7 verdict capsule is retained with
`status = TERMINAL_REFUSED`, `allowed_next_nodes = []`. P8 must **not** be
dispatched. `canonical_run_authorized_anywhere` stays `false` in the DAG.

## §7 If REFUSED — which axis, and what a fresh D-002K must address

**Refused axis: `effect_too_small`** (not `budget_infeasible`, not
`both`). The runtime probe proves the sweep is cheap; the binding
constraint is that the realistic per-cell substrate-vs-null separation,
sourced honestly from the P4 ground-truth magnitudes, is simply too small
to reach power ≥ 0.8 at the Bonferroni-corrected α within any feasible
per-cell seed budget. This is the **same failure mode D-002I diagnosed for
D-002H**: sub-threshold signal + insufficient grid power.

A fresh **D-002K pre-registration** is the only legal forward move. It must
be designed *against the `effect_too_small` axis*, e.g.:

1. **A higher-SNR observable** — a substrate detection statistic whose
   honest P4-grounded standardized effect is materially larger (≥ ~0.63 at
   the current Bonferroni α, the d implied by the D-002I median anchor
   `n_min ≈ 93`).
2. **A window-conditioned / regime-conditioned statistic** that
   concentrates the substrate signal where it is strongest, raising the
   per-cell effect without inflating the prior.
3. **A substantively re-derived effect-size prior backed by new ground
   truth** — e.g. additional positive-control families with larger
   planted, *honestly justified* separations — NOT a relaxed α and NOT an
   inflated attenuation of the existing P4 priors.

What D-002K must **not** do (the exact D-002I-diagnosed failure modes):
loosen the Bonferroni α, inflate the P4-sourced effect prior, or shrink
the canonical cell grid to force `n_min ≤ cap`.

---

### Phase-coupling verification (P7 → {P5, P6, P2, P4})

- **P7 → P5:** every per-cell `substrate` is a P5
  `substrate_candidate_manifest_v1.json` substrate; every P5 substrate
  appears in the grid.
- **P7 → P6:** every per-cell `null` is a P6
  `null_hierarchy_manifest_v1.json` null family whose
  `applicable_substrates` includes the paired substrate.
- **P7 → P2:** every per-cell `window` is in the P2
  `crisis_window_registry_v1.json` and is declared by the paired P5
  substrate's `crisis_windows`.
- **P7 → P4:** every effect-size prior `source_pc_id` is a real P4
  `positive_control_manifest_v1.json` control family; no effect size is
  invented; the prior never inflates the P4 pass magnitude.

### Scope boundary

P7 is a power-DESIGN gate. It does **not** execute a canonical run (P8),
promote any claim (P9), fit real data, or edit the D-002J
pre-registration. It does **not** rescue D-002H — D-002H REFUSED remains
the truthful canonical verdict. The only new source code is under
`tools/systemic_risk/`; P7 adds no files under `research/systemic_risk/`.
