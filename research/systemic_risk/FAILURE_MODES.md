# FAILURE_MODES — research/systemic_risk

> A pre-enumerated catalogue of the ways the candidate signal can
> turn out to be an artefact. Each item below is *expected* to
> emerge during the eventual real-data run; documenting them in
> advance prevents post-hoc rationalisation.

## 1. False positive before non-crisis stress

The detector fires before a market-stress episode that did *not*
escalate into a Laeven-Valencia-class banking crisis. Counts as a
false positive against the labelled crisis set; weight in
`compute_classification_metrics` correctly.

## 2. Signal after crisis (post-event contamination)

The detector fires in the weeks *after* the crisis date. If the
analysis pipeline treats this as "evidence of detection", it has
silently embedded lookahead leakage. The lead-time aggregator's
strict `min_lead_days >= 1` contract refuses this contamination
by construction (see `metrics.LeadTimeConfig`).

## 3. Baseline beats candidate

A naive volatility / density baseline matches or exceeds the
candidate's AUC and lead-time. Per `BASELINES.md`: promote the
baseline narrative, not the candidate.

## 4. Parameter sensitivity

Small changes to the rolling window (e.g. 60 → 75) flip the
verdict from `HARD_PASS` to `UNDECIDED`. Mandatory disclosure as
a sensitivity sweep table; verdict reported only at the
pre-registered window.

## 5. Small-tail instability

Power-law fit at a particular crisis selects a `k_min` that
leaves `n_tail < 50`. The validation-mode wrapper
`fit_power_law_validation` fails-closed on this case; exploratory
fits must report both the n_tail and the relative SE.

## 6. Missing-data artefact

A snapshot in the temporal panel has implicit missing rows or
columns; the validator
`temporal_panel.validate_temporal_exposure_panel` enforces stable
N across the panel (no silent entry / exit). A documented
entry/exit policy is required before any analysis runs.

## 7. Exposure orientation error

`E[i, j]` is silently transposed at some point in the pipeline so
the K-matrix encodes the wrong stress-propagation direction. The
canonical orientation invariant + the 2×2 transpose regression
test `test_coupling.py::test_orientation_invariant_2x2` exist
specifically to catch this.

## 8. Lookahead leakage in CSD or score construction

Future observations bleed into the past indicator series through
e.g. centred rolling windows or full-sample normalisation. The
test `test_critical_slowing_down.py::test_no_lookahead_leakage`
mutates a future segment of the input and asserts past indicator
values are bit-identical.

## 9. Threshold overfitting

The detection threshold `θ` is chosen *after* seeing the AUC
table on the test crises. Forbidden by `PROTOCOL.md § 11`;
`θ` must be either pre-registered or derived from a strict
training-only subset.

## 10. Multiple-testing inflation

Sweeping over windows / thresholds / detector flavours and
reporting only the favourable run. Bonferroni FWER across crises
helps but does not address sweeps over hyperparameters — those
require an outer correction or, preferably, a full pre-registration.

## What this PR does NOT do

This document is a catalogue of failures *that the eventual
real-data run must explicitly probe*. None of the failures has
been observed because no real-data run has occurred. Treat the
list as the **set of disconfirming experiments** the candidate
must survive, not as a record of survived attacks.
