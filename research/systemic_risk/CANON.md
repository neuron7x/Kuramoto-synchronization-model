# Canonical Seven — Complete

The **Canonical Seven** are the seven institutional preconditions an
empirical claim in this module must survive before it is allowed to
graduate from `HYPOTHESIS` to `THEORY`, and from `THEORY` to `FACT`.
They operationalise the falsificationist contract that the module
*as a whole* exists to enforce: every claim must carry, in code,
the specific conditions for its own death.

All seven pillars are now in `main`. Every module is pure-function,
fail-closed, and free of I/O; every public dataclass is
`frozen=True, slots=True`.

| # | Pillar                            | Module                          | Status |
|---|-----------------------------------|---------------------------------|--------|
| 1 | Hypothesis Death Engine           | `death_conditions.py`           | LIVE   |
| 2 | Bayesian Evidence Ledger          | `evidence_ledger.py`            | LIVE   |
| 3 | Data Reality Firewall (8-gate)    | `data_firewall.py`              | LIVE   |
| 4 | Adversarial Baseline Ladder       | `adversarial_ladder.py`         | LIVE   |
| 5 | Leakage Sentinel                  | `leakage_sentinel.py`           | LIVE   |
| 6 | Replication Capsule               | `replication_capsule.py`        | LIVE   |
| 7 | Claim Governance FSM              | `governance_fsm.py`             | LIVE   |

## End-to-end pipeline

A single round through the canonical seven on one claim looks like
this:

```
                      ┌──────────────────┐
                      │ raw exposure     │
                      │ panel + roster   │
                      └────────┬─────────┘
                               ▼
                   ┌───────────────────────┐
                   │ G3: data_firewall     │  (8 gates)
                   │   passed_all?         │
                   └─────────┬─────────────┘
                             │ false → STOP
                             │ true ▼
                   ┌───────────────────────┐
                   │ G5: leakage_sentinel  │  (6 sentinels)
                   │   detected?           │
                   └─────────┬─────────────┘
                             │ true → INVALIDATE
                             │ false ▼
                   ┌───────────────────────┐
                   │ G4: adversarial_ladder│  (8 prosecutors)
                   │   any losing_path?    │
                   └─────────┬─────────────┘
                             │ true → DEMOTE
                             │ false ▼
                   ┌───────────────────────┐
                   │ G6: replication_capsule│  (rerun comparator)
                   │   matched?            │
                   └─────────┬─────────────┘
                             │ false → KILL
                             │ true ▼
                   ┌───────────────────────┐
                   │ G2: evidence_ledger   │  (Bayesian update)
                   │   posterior > prior?  │
                   └─────────┬─────────────┘
                             ▼
                   ┌───────────────────────┐
                   │ G1: death_conditions  │  (5 triggers + precedence)
                   │   action?             │
                   └─────────┬─────────────┘
                             ▼
                   ┌───────────────────────┐
                   │ G7: governance_fsm    │  (state machine)
                   │   apply(transition)   │
                   └─────────┬─────────────┘
                             ▼
                       new claim state
                  (incl. terminal REJECTED)
```

## Precedence

When more than one trigger fires, the death engine resolves them to
a single tier action under the strict ordering:

```
KILL > INVALIDATE > QUARANTINE > DEMOTE > STOP > NONE
```

The governance FSM then maps that action to a state transition;
`REJECTED` is **absorbing** (no resurrection).

## Foundation invariants

* **F1** — every Bayes factor is finite and ≥ 0; `inf` is rejected at
  the constructor; `0` is reserved for the replication-mismatch /
  KILL trigger.
* **F2** — the evidence ledger is append-only and chronologically
  ordered (strict `<`); reordering is impossible by construction.
* **F3** — the death-conditions registry is frozen; new triggers are
  added only via `extend(...)`, which returns a new registry and
  never mutates the existing one.
* **F4** — the leakage sentinel returns `detected=True` on every
  *positive* detection, and `LeakageReport.detected` is the
  disjunction of its component outcomes — there is no quiet-fail
  path.
* **F5** — every public dataclass in this layer is `frozen=True`
  with `slots=True`; instances cannot be mutated after construction.
* **F6** — the data firewall runs **all eight** gates regardless of
  earlier failures; the report contains a complete audit trail.
* **F7** — the replication capsule comparator's six-stage pipeline
  is fail-closed; first-failure wins for `reason`, no silent repair.
* **F8** — the governance FSM is deterministic on `(state,
  TierTransition)`; `REJECTED` is absorbing; `QUARANTINED` cannot be
  promoted out of via this FSM (external sign-off required).

## Reading order

1. [`evidence_ledger.py`](evidence_ledger.py) — formal Bayesian
   skeleton; everything downstream is an evidence producer.
2. [`death_conditions.py`](death_conditions.py) — tier-action
   arbiter; the claim either survives a round or doesn't.
3. [`leakage_sentinel.py`](leakage_sentinel.py) — most common
   producer of `INVALIDATE`-tier evidence; six independent sentinel
   checks.
4. [`data_firewall.py`](data_firewall.py) — eight-gate ingress
   contract; nothing reaches the metric layer without passing all
   eight.
5. [`adversarial_ladder.py`](adversarial_ladder.py) — paired-bootstrap
   delta-AUC against eight prosecutors; baseline-dominance trigger
   producer.
6. [`replication_capsule.py`](replication_capsule.py) — frozen
   comparator; `matched=False` drives KILL via T4 trigger.
7. [`governance_fsm.py`](governance_fsm.py) — frozen FSM with
   absorbing `REJECTED`; the claim's lifecycle terminus.

Every module ships its own test file under
`tests/research/systemic_risk/`. Property-style invariants F1–F8 are
checked there.

## Public surface

The seven pillars contribute roughly 80 symbols to
`research.systemic_risk`'s public `__all__` (see
[`__init__.py`](__init__.py)). They are imported as a single package
so callers can wire the full pipeline without touching submodules
directly:

```python
from research.systemic_risk import (
    # G3 — firewall
    run_data_firewall, FIREWALL_GATES, Provenance,
    # G5 — leakage
    run_leakage_audit,
    # G4 — ladder
    run_adversarial_ladder, LADDER_RUNGS,
    # G6 — capsule
    compare_run_outputs,
    # G2 — ledger
    EvidenceLedger, Evidence, auc_per_crisis_bayes_factor,
    # G1 — death
    DeathConditionsRegistry, default_registry, DeathState,
    # G7 — fsm
    GovernanceFSM,
)
```
