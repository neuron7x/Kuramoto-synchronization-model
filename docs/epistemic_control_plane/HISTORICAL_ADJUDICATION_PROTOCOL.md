# ECP-AS Historical External-Adjudication Protocol — Iteration 003

## Purpose

Iteration 003 moves ECP-AS beyond purely synthetic promotion cases by replaying external scientific adjudication events from public 2026 sources.

The object under test is **not** whether ECP-AS can rediscover the scientific truth of each paper from scratch. The object is whether, once an authenticated external event arrives, the control plane changes claim status conservatively and with the correct epistemic semantics.

## Architectural distinction

ECP-AS separates two notions that are often collapsed:

1. **Authority to invalidate an evidence artifact** — e.g. a publisher retracting an article.
2. **Independent evidence sufficient to falsify a proposition** — a materially stronger condition.

Therefore a retraction does not automatically mean `FALSIFIED`.

Examples:

- invalid dataset provenance -> `STALE`;
- internal reporting/method inconsistency -> `INCONCLUSIVE`;
- independent contradictory replication -> `CONFLICTED`;
- independently established invalid validation where proper validation no longer supports the conclusion -> `FALSIFIED`;
- author-name or contribution correction -> preserve scientific state.

## External case set

The frozen manifest contains 14 public cases:

- 9 material external challenges;
- 5 benign correction/addendum controls.

Sources are official Nature-family editorial actions plus one independent scholarly replication analysis. The manifest stores source URL, title, date, a short paraphrase, and a deterministic digest. It does not archive or reproduce publisher text.

## Evidence boundary

Two labels must not be confused:

### External action label

`DEGRADE` versus `PRESERVE` is grounded in the public external event and its published reason.

### Typed transition

`STALE`, `INCONCLUSIVE`, `CONFLICTED`, and `FALSIFIED` are ECP-AS internal policy states. Their match is **transition conformance**, not external accuracy.

This distinction prevents self-validation by taxonomy. Exact state matching is internal policy conformance, not external accuracy.

## Safety invariant

`FALSIFIED` is reserved for cases where:

- a validation defect is material;
- the source explicitly says the conclusion is unsupported under proper validation; and
- the relevant technical assessment is independently grounded strongly enough for the configured policy.

Otherwise the system degrades more conservatively.

## Benchmark policies

- `retraction_equals_falsification` — naive baseline; every retraction falsifies.
- `all_editorial_actions_degrade` — over-conservative baseline; every correction/addendum/retraction degrades.
- `ecp_as_external_adjudication` — typed authority/defect/independence policy.

## Primary measures

- external action agreement;
- false degradation of benign corrections/addenda;
- missed material degradations;
- false falsification;
- typed transition conformance to the frozen ECP-AS policy.

## Current result

On the 14 frozen cases:

- ECP-AS external action agreement: 14/14;
- false degradations: 0;
- missed degradations: 0;
- false falsifications: 0;
- typed transition conformance: 14/14.

The naive retraction=falsification baseline has 7 false falsifications. The all-editorial-actions-degrade baseline falsely degrades all 5 benign controls.

## What this does not prove

Iteration 003 does not prove that ECP-AS can prospectively detect flawed science before an external adjudicator exists. It does not provide IID generalization and does not independently validate the internal state taxonomy.

## Next proof obligation

Use an externally labeled proposal/discovery benchmark or independent blinded adjudicators so that soundness/promotion labels are not authored by the ECP-AS implementation team.

Relevant 2026 external benchmark directions include SoundnessBench and TruthInsightBench, which explicitly measure scientific soundness/evidence maturity rather than mere code execution.
