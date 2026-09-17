# ECP-AS Iteration 002 — Verification Report

**Status:** `PASS_CONTROLLED_ADVERSARIAL_BENCHMARK__EXTERNAL_VALIDATION_PENDING`

## Objective

Move ECP-AS from architecture-only verification to a falsifiable promotion-policy benchmark while
keeping the claim boundary explicit.

## Engineering changes

- Added an auditable promotion benchmark API under `geosync.epistemic.benchmark`.
- Added behavioral baselines and two mechanism ablations.
- Hardened `REPLICATED` promotion so unresolved blocking negative evidence is fail-closed.
- Added 31 synthetic adversarial/control scenarios.
- Added 4 probes grounded in the repository's preserved negative-evidence registry.
- Added per-scenario decision matrix and failure-class breakdown artifacts.
- Added a 128-state exhaustive truth-table check for the replication gate.

## Results

Canonical benchmark: **35 cases** = 12 safe controls + 23 unsafe cases.

| Policy | Unsafe promotions | UnsafePromotionRate | False blocks | FalseBlockRate |
|---|---:|---:|---:|---:|
| required evidence only | 16/23 | 69.57% | 0/12 | 0% |
| self review | 15/23 | 65.22% | 0/12 | 0% |
| multi-agent vote | 13/23 | 56.52% | 3/12 | 25% |
| artifact chain, no lineage | 8/23 | 34.78% | 0/12 | 0% |
| ECP-AS without negative gate | 6/23 | 26.09% | 0/12 | 0% |
| ECP-AS without lineage gate | 8/23 | 34.78% | 0/12 | 0% |
| **ECP-AS** | **0/23** | **0%** | **0/12** | **0%** |

Against the strongest non-lineage artifact baseline in this suite, ECP-AS reduced unsafe promotion
by **34.78 percentage points**. This is a benchmark-specific exact count, not a population estimate.

The 128-state `OBSERVED -> REPLICATED` truth table passed all states.

## Mechanistic interpretation

The benchmark falsifies the proposition that positive evidence completeness, self-review, verifier
count, or artifact-chain completeness alone are sufficient under correlated-verifier and preserved
negative-evidence failure modes.

Ablation isolates two contributions:

- removing lineage gating reintroduces 8 unsafe promotions;
- removing active-negative gating reintroduces 6 unsafe promotions.

## Verification

- `39` targeted unittest methods: PASS;
- one test exhaustively evaluates `128` replication-gate states: PASS;
- `compileall` for ECP-AS + benchmark runner: PASS;
- commit-acceptor schema validation: PASS;
- commit-acceptor inline-command syntax validation: PASS;
- selected Iteration 002 diff-bound acceptors: PASS;
- global acceptor corpus remains blocked by pre-existing unrelated SHA-mismatch debt; this is not counted as an Iteration 002 PASS.
- canonical benchmark runner exit code: PASS;
- ECP-AS benchmark decisions: `35/35` equal declared labels;
- repository negative probes: `4/4` blocked from stronger promotion.

## Explicit boundary

This iteration does **not** prove reduction of scientific error on natural autonomous-research
workloads. The next proof obligation is an external/replayed workload with labels and evidence
construction not authored by the same benchmark designer.
