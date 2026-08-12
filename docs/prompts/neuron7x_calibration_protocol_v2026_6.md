# Neuron7X Calibration Protocol v2026.6

## Purpose

Define calibration rules for Neuron7X / FVPS governance artifacts.

Calibration means adjusting precision, thresholds, weights, sensitivity bands, and promotion rules so outputs cannot overstate evidence, value, or readiness.

This protocol is governance-only. It does not change runtime, physics, market, or trading behavior.

## Calibration Object

```text
raw_output_signal
→ normalized_metric_vector
→ weighted_score
→ threshold_gate
→ rank_band
→ allowed_action
```

## Metric Vector

Each metric is normalized to `[0.0, 1.0]`.

```text
S = signal capture
I = intent compression
C = constraint extraction
M = mechanism validity
E = evidence binding
F = failure-boundary exposure
N = value-node clarity
A = artifact executability
L = feedback-ledger quality
G = governance control
```

## Value Score

```text
V = 0.10S + 0.10I + 0.10C + 0.12M + 0.12E + 0.10F + 0.12N + 0.12A + 0.06L + 0.06G
```

## Rank Bands

```text
R0_NOISE             V < 0.30
R1_FORMATTED         0.30 <= V < 0.45
R2_OPERATIONAL       0.45 <= V < 0.60
R3_VERIFIABLE        0.60 <= V < 0.72
R4_AGENTIC           0.72 <= V < 0.82
R5_RESEARCH_GRADE    0.82 <= V < 0.90
R6_GOVERNANCE_GRADE  0.90 <= V < 0.96
R7_MAX_INFERENCE     V >= 0.96
```

## Promotion Guards

A rank cannot be promoted if any mandatory guard fails.

```text
R3 requires M >= 0.65 and A >= 0.65
R4 requires M >= 0.72, F >= 0.70, A >= 0.72
R5 requires M >= 0.80, E >= 0.75, F >= 0.75, A >= 0.80
R6 requires M >= 0.86, E >= 0.86, F >= 0.82, G >= 0.85
R7 requires M >= 0.92, E >= 0.92, F >= 0.90, A >= 0.92, G >= 0.90
```

If the weighted score reaches a band but a guard fails, the final rank is capped at the highest rank whose guards pass.

## Sensitivity Profiles

### Conservative

Use for release, security, physics, scientific, or safety-sensitive claims.

```text
threshold_shift = +0.04
minimum_evidence_binding = 0.86 for R6
false_promotion_tolerance = 0
```

### Balanced

Use for normal governance artifacts and engineering planning.

```text
threshold_shift = 0.00
false_promotion_tolerance = 0
```

### Exploratory

Use only for ideation or research framing.

```text
threshold_shift = -0.04
maximum_allowed_label = PLAUSIBLE
cannot promote to VERIFIED, CI_VERIFIED, or OPERATIONAL_READY
```

## Calibration Penalties

Apply penalties before thresholding.

```text
missing evidence link: -0.12
missing rollback path: -0.08
missing failure boundary: -0.10
unfalsifiable claim: cap at R2_OPERATIONAL
metaphor used as mechanism: cap at R1_FORMATTED
runtime or physics claim without executable test: cap at R2_OPERATIONAL
stale PR body: cap at R3_VERIFIABLE
same-SHA CI missing for merge claim: cap at R4_AGENTIC
```

## Claim-State Mapping

```text
FALSE             contradiction exists
UNTESTED          no executable evidence
PARTIAL           incomplete evidence chain
LOCAL_VERIFIED    local command proof exists
CI_VERIFIED       same-SHA CI proof exists
EVIDENCE_BEARING  real data + replay + baseline + falsifier + semantic validation
```

Rank bands do not replace claim states. Rank measures output quality. Claim state measures proof completeness.

## Failure Modes

```text
overcalibration: thresholds block useful partial work
undercalibration: weak evidence is promoted
metric gaming: output optimizes score instead of truth
false precision: numeric score hides subjective judgment
stale calibration: thresholds stop matching repo risk
```

## Required Output

A calibrated response must return:

```text
rank
score
profile
active_thresholds
guards_failed
penalties_applied
allowed_claim
blocked_claims
next_action
```

## Boundary

Allowed claim: this protocol defines governance calibration thresholds and sensitivity rules.

Blocked claims: empirical cognitive validation, model weight change, runtime behavior change, physical-law validation, predictive performance, market readiness, trading readiness.
