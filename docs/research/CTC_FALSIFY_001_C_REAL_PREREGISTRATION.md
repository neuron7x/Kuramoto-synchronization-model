# CTC-FALSIFY-001 · C-real Pre-Registration (FROZEN, pre-data)

Sealed by `config_c_real.config_hash()` **before** any dataset is
downloaded or inspected. The in-silico arc is consolidated and
metric-hardened (L1→L2→C3→C4→C5, #748…#763); this is the only open layer.
It is **not** a universal CTC-theory verdict.

## Claim under test

> On real paired LFP+spike data, the causal CTC claim (the gamma phase
> relation carries inter-areal routing) is supported iff the
> **C5-validated full gamma cross-spectral discriminant** separates an
> **independently manipulated** routing-ON vs routing-OFF condition
> out-of-sample, above a jointly-matched confound surrogate, while the
> standard scalar estimands do not.

## Carried forward (not re-litigated)

- **Estimator is pre-committed**: the C5 full cross-spectral discriminant.
  Scalar PLV-residual / time-reversed PSI are **rejected** — C3/C4/C5
  proved them blind/estimand-limited. No estimator search post-data.
- **No toggle ground truth on real data** ⇒ the routing label MUST be an
  *independent experimental manipulation* (attention cue + behaviour, or
  opto/microstim). A self-derived label is circular (the C4 self-lie).
- **L2 fixes** all bind here: jointly rate∧power∧common-drive matched
  surrogate, P-replication suitability gate, Holm multiplicity, MDE/power,
  symmetric KILLED/SURVIVED thresholds.

## Frozen dataset selection rule (garden-of-forking-paths closed)

Inclusion: simultaneous LFP+spikes ≥2 areas; an independent routing
manipulation; open licence + content-addressable dump; trial structure
admitting the jointly-matched surrogate. The **first** source satisfying
*all*, by the fixed order `allen_visual_coding_neuropixels →
crcns_pfc_2 → crcns_v1_* → published_ctc_fries_lab_if_open`, is bound at
the C-real-data A-gate. Pinned here so selection is not post-hoc.

## Fail-closed decision (pre-registered)

`INADMISSIBLE_NO_PAIRED_DATA` (pre-data, the designed state) →
`INADMISSIBLE_NO_INDEPENDENT_ROUTING_LABEL` →
`INADMISSIBLE_DATASET_UNSUITABLE` (P does not replicate) →
`INADMISSIBLE_UNDERPOWERED` → terminal:

- **`SURVIVED_INITIAL`** iff OOS-AUC ≥ `AUC_SUPPORT_MIN` (0.70) on
  routing-ON vs OFF, above the jointly-matched surrogate, Holm-corrected.
- **`KILLED_SCOPED`** iff OOS-AUC ≤ `AUC_CHANCE_HI` (0.60) with the
  independent control present.
- AUC in the inconclusive band ⇒ no forced call; richer pre-registered
  probe required (honest non-decision).

## Pre-stated forecast (the two terminals — no third)

- **A (likelier).** Scalar estimands stay blind; the cross-spectral
  discriminant separates routing-ON/OFF → scoped methodological negative:
  *canonical CTC evidence is estimand-limited, not the phenomenon*.
  Publishable as instrument-critique; **not** a theory verdict.
- **B.** No independent label obtainable / discriminant at chance →
  *CTC-causal UNTESTABLE by this protocol*. Hard knowledge boundary, no
  verdict on the theory.

## Honesty invariant & scope

If routing survives the jointly-matched null with the independent control,
**survival is reported, not spun** — symmetric thresholds, identical
template. Tier: INFERENCE/hypothesis until real data; then scoped to that
dataset+pipeline only. `ctc_falsify_001` stays **OPEN**.

## UNKNOWN

Which concrete dataset/licence — **not checked, no data touched**.
Resolved only at the C-real-data A-gate, after this hash is sealed. No C6
exists; C-real-data proceeds only on explicit user vector.
