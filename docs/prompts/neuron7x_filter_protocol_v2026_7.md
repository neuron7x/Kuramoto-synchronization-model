# Neuron7X Filter Protocol v2026.7

## Purpose

Define the governance filter layer for Neuron7X/FVPS outputs.

Filtering converts raw generated signals into an admissible artifact set by removing unsupported, stale, duplicated, ambiguous, non-computable, or boundary-violating content before claim-state promotion.

This protocol is governance-only. It does not change runtime, physics, market, trading, forecasting, or model behavior.

## Transformation

```text
RAW_SIGNAL_SET
→ NORMALIZE
→ CLASSIFY_SIGNAL
→ REMOVE_INVALID
→ DEDUPLICATE
→ BOUNDARY_CHECK
→ RETAIN_MINIMAL_EVIDENCE
→ EMIT_FILTERED_ARTIFACT
```

## Signal Classes

```text
KEEP
  Mechanism-bound, evidence-linked, actionable, scoped, non-duplicated.

COMPRESS
  Useful but verbose, redundant, or excessively formatted.

QUARANTINE
  Plausible but missing proof, source, command, artifact, or CI link.

DROP
  Invalid, unsupported, stale, contradictory, decorative, or outside boundary.
```

## Filter Dimensions

```text
semantic_noise
claim_overreach
missing_evidence
stale_context
duplicate_artifact
undefined_metric
non_computable_claim
boundary_violation
format_padding
low_value_output
```

## Acceptance Rules

A signal may pass only when it has at least one of:

```text
mechanism
source reference
test reference
command reference
artifact reference
same-SHA CI proof
explicit boundary label
explicit rollback path
```

A signal must be removed when it:

```text
promotes speculation as verified
uses metaphor as mechanism
claims runtime behavior from governance docs
claims physics validation from descriptors
claims trading readiness without evidence
repeats an existing artifact without new value
uses vague value language without measurable function
```

## Filtering Score

```text
F = 0.18R + 0.16E + 0.14M + 0.12B + 0.12D + 0.10C + 0.10V + 0.08A
```

Where:

```text
R = relevance
E = evidence linkage
M = mechanism clarity
B = boundary compliance
D = duplication penalty inverse
C = computability
V = measurable value
A = actionability
```

## Thresholds

```text
F < 0.35       DROP
0.35–0.55      QUARANTINE
0.55–0.75      COMPRESS
>= 0.75        KEEP
```

## Output Contract

```text
[FILTERED_SIGNAL]
<retained content>

[REMOVED_SIGNAL]
<reasoned removals>

[QUARANTINED_SIGNAL]
<content requiring proof before promotion>

[BOUNDARY]
<allowed and blocked claims>

[NEXT_ACTION]
<single artifact or command>
```

## Final Law

Filtering is not censorship. Filtering is epistemic hygiene.

If the signal cannot improve decision quality, execution, reproducibility, claim clarity, or value extraction, it is systemic waste.
