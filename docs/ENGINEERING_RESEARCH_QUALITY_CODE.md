# Engineering Research Quality Code

Status: repository-local quality statute.  
Scope: PRs touching physics, invariants, audits, CI gates, or research claims.  
Non-claim: this is not an external certification.

## First principles

1. Evidence outranks narrative.
2. Red enforced gates block readiness.
3. The smallest sufficient diff wins.
4. A performance patch must not become a scientific certification.
5. Partial audits must remain named as partial.
6. Residual gaps must stay explicit.
7. Mutation resistance is a release property, not polish.
8. Tests must falsify named risks, not decorate a PR.
9. Baseline edits must increase verification power and must not lower floors.
10. Merge requires an explicit final verdict.

## Verdict vocabulary

- `ACCEPT`: all enforced gates green and claim scope unchanged.
- `REVISE`: direction valid, evidence incomplete.
- `BLOCK`: enforced gate red or claim surface expanded.
- `CLOSE`: patch path increases entropy beyond benefit.

## Operating protocol

1. Name the failure mode.
2. Name the invariant that must survive.
3. Apply the smallest reversible patch.
4. Prefer existing gates before adding tests.
5. Add tests only for named invariants or mutation survivors.
6. Do not lower mutation floors.
7. Preserve residual-risk metadata.
8. Keep PRs draft until required gates are green.
9. Mark ready only after independent gate agreement.
10. Merge only after `ACCEPT`.

## Application to second-order audit energy streaming

Valid claim:

> The audit-time swing-energy evaluator avoids materializing a full `T*N*N` phase-delta tensor and evaluates pairwise potential one time slice at a time with `O(N^2)` peak pairwise working memory.

Rejected claims:

- no global stability certification;
- no complete Lyapunov proof;
- no long-horizon guarantee;
- no bypass of mutation, acceptor, PR, physics, or hygiene gates.

Required PR state:

- `energy_evaluator = streamed_pairwise_potential` may be reported;
- `energy_peak_memory = O(N^2)` may be reported;
- `promotion_allowed` must remain constrained by explicit remaining gaps;
- draft remains draft until all required gates pass.
