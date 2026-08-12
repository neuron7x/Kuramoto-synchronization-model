# Evidence Map — Claim → Code → Test → Falsifier

> Auto-trace from `research/systemic_risk/claims.yaml`. To verify
> mappings, run `python tools/compile_claims.py --fail-on-floating`.

## Pillar 1 — Hypothesis Death Engine

| Aspect | Path |
|---|---|
| Code | `research/systemic_risk/death_conditions.py` |
| Tests | `tests/research/systemic_risk/test_death_conditions.py` (18 tests) |
| Metamorphic | `tests/metamorphic/test_metamorphic.py::test_fsm_rejected_is_absorbing` |
| Falsifier | T4 (replication mismatch) does not drive KILL |
| CI | `pytest_research_systemic_risk` |

## Pillar 2 — Bayesian Evidence Ledger

| Aspect | Path |
|---|---|
| Code | `research/systemic_risk/evidence_ledger.py` + `bayes_rigorous.py` |
| Tests | `test_evidence_ledger.py` (19) + `test_bayes_rigorous.py` (28) |
| Metamorphic | order-invariance, BF=0 → KILL regardless of history |
| Property | Wagenmakers BIC closed form, Cramér-Rao bound (Monte-Carlo) |
| Falsifier | empirical SE on Pareto α=2.5 < 0.95 × CRLB |

## Pillar 3 — Data-Reality Firewall

| Aspect | Path |
|---|---|
| Code | `research/systemic_risk/data_firewall.py` |
| Tests | `test_data_firewall.py` (34) |
| Metamorphic | label permutation preserves structural-gate outcomes |
| Falsifier | `FIREWALL_GATES` count drifts from 8 |

## Pillar 4 — Adversarial Baseline Ladder

| Aspect | Path |
|---|---|
| Code | `research/systemic_risk/adversarial_ladder.py` + `occam_penalty.py` |
| Tests | `test_adversarial_ladder.py` (17) + `test_occam_penalty.py` (15) |
| Falsifier | candidate ACQUITTED with non-empty losing_paths |

## Pillar 5 — Leakage Sentinel

| Aspect | Path |
|---|---|
| Code | `research/systemic_risk/leakage_sentinel.py` |
| Tests | `test_leakage_sentinel.py` (19) |
| Metamorphic | disjunction-monotonic in fired components |
| Falsifier | positive sentinel produces detected=False |

## Pillar 6 — Replication Capsule

| Aspect | Path |
|---|---|
| Code | `research/systemic_risk/replication_capsule.py` |
| Tests | `test_replication_capsule.py` (17) |
| Metamorphic | same-input determinism |
| Falsifier | matched=True on divergent seed |

## Pillar 7 — Governance FSM

| Aspect | Path |
|---|---|
| Code | `research/systemic_risk/governance_fsm.py` + `governance.py` |
| Tests | `test_governance_fsm.py` (23) + `test_governance.py` (12) |
| Metamorphic | REJECTED is absorbing |
| Falsifier | input transitions out of REJECTED |

## End-to-end orchestrators

| Layer | Path | Tests |
|---|---|---|
| `canonical_seven.py` (verbose) | `test_canonical_seven.py` | 10 |
| `minimal.py` (single-file) | `test_minimal.py` | 44 |
| `quick_round.py` (ergonomic) | `test_quick_round.py` | 10 |
| `protocol_x9r.py` (X-9R machine) | `test_protocol_x9r.py` | 30 |

## Cross-cutting

| Layer | Path | Tests |
|---|---|---|
| `verdict_lattice.py` | `test_verdict_lattice.py` | 25 (12 Hypothesis property-tests) |
| `kuramoto_extensions.py` | `test_kuramoto_extensions.py` | 14 |
| `synthetic.py` + `cli.py` | `test_cli_and_synthetic.py` | 8 |
| metamorphic | `tests/metamorphic/` | 25 |
| negative controls | `tests/negative_controls/` | 17 |
