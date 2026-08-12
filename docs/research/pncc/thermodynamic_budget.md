# PNCC-A — Thermodynamic Budget (Landauer-cost proxy)

**Status:** experimental / opt-in. No production default activation. The
module is a pure-functional accounting layer; no global state, no RNG,
no I/O. It is composed by an external orchestrator behind an explicit
config flag.

**Module:** `core/physics/thermodynamic_budget.py`
**Tests:** `tests/unit/physics/test_thermodynamic_budget.py`

---

## The 7 CANONS (PNCC)

(Inline; a shared `docs/research/pncc/CANONS.md` will replace this block
when the coordination PR lands.)

1. Information processing has thermodynamic cost.
2. Erasure and irreversible decisions must be minimized.
3. Every irreversible action requires evidence.
4. High uncertainty increases free energy.
5. Robust decisions must dominate nominal under distribution shift.
6. Operator state is constraint, not oracle.
7. No CNS-performance claim is valid without baseline + intervention +
   control + measured effect.

This module implements canon 1 (cost accounting) and supplies the
quantitative substrate for canon 2 (erasure minimization). Canons 3, 5,
and 7 are enforced by sibling PNCC modules (`evidence_ledger`,
`reversible`, etc.) via separate PRs.

---

## No-bio-claim disclaimer

> This module measures system-level proxy costs. It does NOT measure or
> improve human cognition. Any claim of cognitive improvement requires
> a registered EvidenceClaim with baseline, intervention, control, and
> 95% confidence interval (see `tacl/evidence_ledger.py`).

---

## Formula proxies

All costs are *dimensionless* — not joules. They form a unified penalty
currency for orchestration policy.

| Component | Formula | Notes |
|---|---|---|
| `TokenCost.proxy_cost` | `n_input + 4·n_output` | Output weight 4 reflects decode-dominance (autoregressive forward pass per output token). |
| `LatencyCost.proxy_cost` | `log1p(wall_time_ns / 1e6)` | `log1p` ⇒ 0 ns gives 0 cost exactly; saturates softly at second / minute scales. |
| `EntropyCost.proxy_cost` | `bits_erased · ln(2)` | Landauer-mapping in dimensionless units. `bits_consumed` recorded for accounting only. |
| `IrreversibleActionCost.proxy_cost` | `is_irreversible ? penalty · score : 0` | `score ∈ [0, 1]`. Reversible actions are cost-free in this dimension. |
| `BudgetEntry.total_proxy_cost` | sum of the four above | Aggregated per action. |
| `BudgetLedger.total_cost(...)` | Σ entries | Pure aggregation; empty ledger ⇒ 0.0 exactly. |

All component constructors fail-closed on negative or non-finite inputs
(no silent clamp, no silent NaN repair).

---

## Inputs / Outputs

### Inputs (per action)

- `n_input_tokens: int ≥ 0`, `n_output_tokens: int ≥ 0`
- `wall_time_ns: int ≥ 0`, `p99_ns: int ≥ 0`
- `bits_consumed: float ≥ 0`, `bits_erased: float ≥ 0` (both finite)
- `is_irreversible: bool`, `irreversibility_score: float ∈ [0, 1]`
- `action_id: str` (non-empty), `timestamp_ns: int ≥ 0`

### Outputs

- Frozen, slotted dataclasses: `TokenCost`, `LatencyCost`, `EntropyCost`,
  `IrreversibleActionCost`, `BudgetEntry`, `BudgetLedger`.
- All immutable — ledger entries are evidence, not state.

### Configuration (`ThermodynamicBudgetConfig`)

- `irreversibility_penalty: float = 1.0` (≥ 0)
- `max_horizon_ns: int = 60_000_000_000` (60 s)
- `fail_on_negative_cost: bool = True` (no silent repair)

---

## Invariants

### INV-LANDAUER-PROXY (P0, universal)

> For any irreversible action's cost `C_irr` and the cost `C_rev` of its
> hypothetical reversible alternative with **identical** token, latency,
> and entropy components:
>
> ```
> C_irr ≥ C_rev
> ```
>
> with strict `>` whenever `irreversibility_score > 0`.

This is the dimensionless analogue of Landauer's bound: erasure-coupled
work cannot be smaller than a reversible alternative's work for the same
I/O budget. The strict inequality follows from `penalty > 0` and the
score-positive condition.

**Test pointer:**
`tests/unit/physics/test_thermodynamic_budget.py::test_landauer_proxy_irreversible_dominates_reversible`
runs 1000 random pairs (seeded, INV-HPC1-respecting) and asserts both
the non-strict bound and the strict bound under `score > 0`, including
the algebraic identity `C_irr − C_rev = penalty · score` to 1e-9.

### INV-HPC1 (universal — determinism)

The module is purely functional — no global state, no RNG, no time call.
Identical inputs ⇒ bit-identical outputs.
**Test:** `test_deterministic_under_fixed_seed` (50 entries, total cost
byte-precise across two runs from the same seed).

### INV-HPC2 (universal — finite-in / finite-out)

NaN / Inf / negative inputs raise `ValueError`.
**Tests:** `test_token_cost_finite_non_negative`,
`test_entropy_cost_finite`, `test_negative_cost_raises`.

---

## Test inventory (11 functions, all green)

| # | Test | Type |
|---|---|---|
| 1 | `test_token_cost_finite_non_negative` | universal (Hypothesis sweep, 200 examples) |
| 2 | `test_latency_cost_monotone_in_walltime` | qualitative |
| 3 | `test_entropy_cost_finite` | universal (Hypothesis sweep, 200 examples) |
| 4 | `test_landauer_proxy_irreversible_dominates_reversible` | universal — INV-LANDAUER-PROXY (1000 random pairs) |
| 5 | `test_irreversibility_zero_recovers_reversible_cost` | algebraic (exact) |
| 6 | `test_total_cost_additive_over_entries` | algebraic |
| 7 | `test_negative_cost_raises` | universal (fail-closed) |
| 8 | `test_horizon_filter_excludes_old_entries` | conditional |
| 9 | `test_deterministic_under_fixed_seed` | universal — INV-HPC1 |
| 10 | `test_bits_erased_zero_implies_zero_entropy_cost` | algebraic (Hypothesis 100 examples) |
| 11 | `test_dataclasses_are_frozen` | universal — immutability guard |

---

## Known limitations

- **Proxy units, not joules.** The cost currency is dimensionless. No
  hardware integration: no perf-counter coupling, no power-meter
  ingestion, no GPU-energy proxy.
- **Output-token weight = 4 is heuristic** — it reflects decode-dominance
  on transformer-class accelerators but is *not* calibrated to any
  vendor's energy meter. Treat the absolute cost number as ordinal.
- **Latency map is a soft saturator,** not a calibrated wall-time-to-energy
  curve. `log1p(ns / 1e6)` is monotone and zero-anchored; that's all.
- **Irreversibility scoring is exogenous** — this module accepts a
  `[0, 1]` score from the caller. The construction of that score is the
  responsibility of the action layer (e.g. `tacl/evidence_ledger.py`).
- **Operator state is *not* an input.** Per canon 6, operator-physiology
  signals must not feed this budget. Do not couple this module to any
  HRV / EEG / wearable channel.

---

## Source anchor

R. Landauer, *"Irreversibility and heat generation in the computing
process"*, IBM J. Res. Dev. 5 (1961) 183. The principle establishes
that the minimum energy dissipated by erasing one bit of classical
information is bounded below by `kT · ln(2)`.

This module is a **proxy** that tracks budget over orchestration
steps; it does **not** claim to compute physical work. The use of
`ln(2)` is the dimensionless mapping
`1 bit erased ↔ ln(2) units of proxy work`. No claim is made about
the empirical attainability of the Landauer bound on any specific
hardware platform.

---

## How to use

```python
from core.physics.thermodynamic_budget import (
    ThermodynamicBudgetConfig,
    BudgetLedger,
    aggregate_entry,
    compute_token_cost,
    compute_latency_cost,
    compute_entropy_cost,
    compute_irreversibility_cost,
    total_cost,
)

cfg = ThermodynamicBudgetConfig()  # opt-in default penalty=1.0

entry = aggregate_entry(
    action_id="submit_order_42",
    timestamp_ns=...,
    token=compute_token_cost(n_in=120, n_out=18),
    lat=compute_latency_cost(wall_ns=42_000_000, p99_ns=70_000_000),
    ent=compute_entropy_cost(bits_consumed=12.5, bits_erased=3.0),
    irr=compute_irreversibility_cost(True, 0.7, cfg),
)

ledger = BudgetLedger(entries=(entry,), horizon_ns=cfg.max_horizon_ns)
budget = total_cost(ledger)
```

The orchestrator decides what action to record; the module never
*executes* anything.
