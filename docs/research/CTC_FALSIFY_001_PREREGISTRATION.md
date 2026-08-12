# CTC-FALSIFY-001 — Pre-Registration (frozen, in-silico stage)

Falsification instrument for **Communication-through-Coherence** (Fries 2005
*TICS*; 2015 *Neuron*). This is **not** a test of the CTC theory. It is the
fail-closed machine that prevents the standard CTC analysis pipeline from
laundering confounds as evidence. Constants live only in
`research/ctc_falsify/config.py` (SSOT; `config_hash` pins them).

## Claim under test

> The standard CTC analysis pipeline (gamma-band PLV + coherence) distinguishes
> a *true phase-gated inter-population communication channel* from confound-only
> signals (common drive / rate / SNR) at the canonical effect size.

P (descriptive): inter-areal gamma coherence covaries with communication — **not
attacked**, expected to survive. C (causal-mechanistic): the gamma phase
relation *is* the carrier — the target.

## Generative ground truth (our physics edge)

Two-population Sakaguchi–Kuramoto (`generative.py`). The **only** genuine CTC
mechanism is a directed A→B phase coupling `channel_strength`. Confounds are
injected with `channel_strength == 0` by construction, so any "CTC-positive"
readout on them is a provable false positive.

- **N1 common-drive** — shared stochastic input, no channel.
- **N2 rate** — slow envelope correlated across A,B, no channel.
- **N3 SNR** — low signal-to-noise, no channel.
- **N⁺ positive control** — genuine phase-gated channel, no heavy confound.

## Decision logic (fail-closed, pre-registered)

A → B → C → D → E (see `gates.py` docstring). Verdict enum:
`INADMISSIBLE_NO_GENERATIVE_GROUNDTRUTH | INADMISSIBLE_ESTIMATOR_BLIND |
INADMISSIBLE_CIRCULAR_PIPELINE | INADMISSIBLE_UNDERPOWERED |
INADMISSIBLE_NO_REAL_DATA | KILLED_SCOPED | SURVIVED_INITIAL`.

- **B (estimator blindness):** N⁺ recovery `< NPLUS_MIN_RECOVERY` (0.90) ⇒
  `INADMISSIBLE_ESTIMATOR_BLIND` — a pipeline that cannot see a true channel may
  not license any kill (the DOPA-VALIDITY-001 lesson, transplanted).
- **E (pre-data):** no real electrophysiology dataset is bound, so the
  canon-kill is **withheld by design** ⇒ `INADMISSIBLE_NO_REAL_DATA`. The
  confound diagnostic is still computed and recorded as evidence.
- `KILLED_SCOPED` / `SURVIVED_INITIAL` are **unreachable** until L2 binds a real
  dataset. The engine never fabricates a kill, never rescues the canon.

## Reference run (in-silico, pre-data)

`verdict = INADMISSIBLE_NO_REAL_DATA` — the designed pre-data success.
N⁺ recovered (≥ 0.90); confound false-positive rates at the canonical
threshold recorded in `evidence/ctc_falsify_001_result.json`. A non-zero
confound false-positive rate is an in-silico hazard signal, **not** a kill.

## Honesty invariant

If, at L2, the CTC residual (beyond N1/N2/N3-matched surrogates on real data)
survives all nulls with N⁺ recovered, we report **survival**, not spin. The
machine is indifferent to the audience.

## L2 (not in this artifact)

Bind a real LFP+spike dataset with a pre-committed selection rule; add the
real-data residual test that can reach `KILLED_SCOPED` / `SURVIVED_INITIAL`.
Registered as research line `ctc_falsify_001` (status OPEN).

## Verification tags

- FACT: rate/waveform/SNR confounds of spike-field coherence are documented
  (Lepage 2011; Vinck 2010; Schneider/Vinck 2021). confidence=high.
- FACT: the Kuramoto generative stack and PLV/coherence estimators are
  executable here (numpy/scipy). confidence=high.
- ASSUMPTION: a suitable open dataset is obtainable at L2. confidence=medium.
- UNKNOWN: which dataset/licence — not checked, no data touched. Resolve
  before the L2 A-gate, fail-closed.
