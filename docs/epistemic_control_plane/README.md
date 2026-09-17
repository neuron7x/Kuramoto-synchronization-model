# ECP-AS v0.1 — Epistemic Control Plane for Autonomous Science

ECP-AS is a domain-independent runtime gate extracted from GeoSync governance mechanisms.
It separates **research generation** from **epistemic authorization**.

Core invariant:

> Agents may generate, test, and attack hypotheses. They may not strengthen a claim's epistemic status unless the admission controller authorizes the transition.

## Iteration 1 vertical slice

Implemented:
- evidence-carrying claim model;
- explicit adjacent state machine;
- promotion contracts;
- fail-closed admission controller;
- P/C/A/I oracle independence plus lineage-overlap rejection;
- immutable negative-evidence objects;
- deterministic promotion certificates;
- authoritative hash-chained event ledger with tamper detection;
- state reconstruction from ledger rather than agent-supplied maturity;
- explicit degradation into falsified/stale/OOD/conflicted terminal states;
- append-only negative-evidence resolution events;
- typed acyclic dependency graph with dependency-scoped invalidation sets;
- deterministic structured claim-contract compiler;
- falsifier-first experiment ranking;
- GeoSync legacy maturity adapter;
- executable tests.

## Iteration 2 controlled benchmark

Iteration 002 adds a controlled adversarial promotion benchmark, behavior-class baselines,
mechanism ablations, repository-grounded negative-evidence probes, and a 128-state replication
gate truth table. On the declared 35-case suite, full ECP-AS produced 0/23 unsafe promotions and
0/12 false blocks. This is **not** yet external real-workload validation. See
`docs/epistemic_control_plane/BENCHMARK_PROTOCOL.md` and
`artifacts/epistemic_control_plane/iteration_002/ITERATION_002_REPORT.md`.

Not yet claimed:
- complete semantic claim compiler;
- graph-scale invalidation propagation;
- cryptographic append-only ledger;
- LLM-independent semantic equivalence proofs;
- cross-domain empirical validation;
- demonstrated reduction in unsafe-promotion rate on external natural workloads.

Those are future proof obligations, not completed features.
## Iteration 003 — external adjudication replay

See `HISTORICAL_ADJUDICATION_PROTOCOL.md` and `artifacts/epistemic_control_plane/iteration_003/`. This iteration separates external action agreement from internal typed-transition conformance and tests publisher/replication events without treating every retraction as proposition falsification.

## Iteration 004 — lineage-aware evaluator stress

See `SOUNDNESS_CONTROL_STRESS_PROTOCOL.md` and `artifacts/epistemic_control_plane/iteration_004/`. External SoundnessBench labels are used only for scoring; evaluator errors are synthetic stress models. The iteration adds pairwise-lineage quorum authorization and explicitly records hidden common cause as a residual failure mode.

## Iteration 005 — distributionally robust quorum certification

See `DISTRIBUTIONALLY_ROBUST_QUORUM_PROTOCOL.md` and `artifacts/epistemic_control_plane/iteration_005/`. Published SoundnessBench FP/FN marginals are used to compute exact worst-case quorum risk over every compatible joint error distribution. Marginal benchmark quality alone is not treated as evidence of evaluator independence.
