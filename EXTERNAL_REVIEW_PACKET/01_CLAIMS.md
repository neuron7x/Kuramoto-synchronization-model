# What the System Claims (and Refuses to Claim)

> Source-of-truth: `research/systemic_risk/claims.yaml`. This file
> is a human-readable rendering. If they diverge, `claims.yaml`
> wins.

## ✓ Verified claims (executable evidence in tree)

| ID | Claim | Anchor |
|---|---|---|
| C001 | Canonical Seven provides a fail-closed falsification workflow | `canonical_seven.py` + tests |
| C002 | Verdict aggregation is the join of a totally-ordered lattice | `verdict_lattice.py` + Hypothesis property tests |
| C003 | Bayes-factor primitives derive from primary statistical theory | `bayes_rigorous.py` + Monte-Carlo |
| C004 | Data-Reality Firewall enforces 8 orthogonal ingress gates | `data_firewall.py` |
| C005 | Leakage Sentinel detects 6 canonical time-leakage failure modes | `leakage_sentinel.py` |
| C006 | Replication Capsule comparator is fail-closed in 6 stages | `replication_capsule.py` |
| C007 | Adversarial Ladder evaluates 8 prosecutors with paired-bootstrap delta-AUC | `adversarial_ladder.py` |
| C008 | Governance FSM has REJECTED as an absorbing terminal state | `governance_fsm.py` + metamorphic test |
| C009 | Protocol X-9R is a deterministic 9-gate empirical falsification machine | `protocol_x9r.py` |
| C010 | Minimal Canonical Seven encodes all 7 pillars in <800 LoC | `minimal.py` (446 LoC) |
| C011 | All 172 public symbols are mapped to invariants and tests | `public_symbol_matrix.csv` |
| C012 | Negative-control suite confirms canonical failure tiers on garbage | `tests/negative_controls/` |
| C013 | Metamorphic test layer encodes invariant relations across transforms | `tests/metamorphic/` |

## ⏸ Hypothesis / blocked claims

| ID | Claim | Why blocked |
|---|---|---|
| C014 | Real-data evaluation requires e-MID / ECB MMSR feed | licence + regulation |
| C015 | External adversarial review pending; codebase review-ready | external action |

## ✗ Claims this system **refuses** to make

* Any claim of measured AUC on **real interbank data**.
* Any claim of "validated", "proven", "production-ready", "trading
  signal", "predicts crisis", or "early-warning system".
* Any claim of replication-on-out-of-sample-crisis without a sealed
  capsule on disk and a fresh-clone rerun match.
* Any claim about emerging-market crises (data coverage is Western
  + 2023 anchors per `LIMITATIONS.md § 3`).
