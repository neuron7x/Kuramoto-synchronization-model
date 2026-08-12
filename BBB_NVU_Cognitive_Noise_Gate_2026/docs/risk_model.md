# Risk Model

## Domain indices

- `BSI` — Barrier Stress Index from barrier stress proxies such as TEER delta, permeability coefficient, DCE-MRI Ktrans, CSF/serum albumin quotient, or BBB-related biomarkers.
- `NRI` — Neuroinflammation Risk Index from inflammatory proxies such as CRP, cytokines, leukocyte markers, fever/infection flags, or experimental microglial markers.
- `VML` — Vascular-Metabolic Load from blood-pressure load, glucose variability, SpO2, sleep duration, fragmentation, or HRV trend.
- `GRS` — Glymphatic Recovery Score from sleep continuity, slow-wave sleep proxy, sleep HRV dynamics, imaging protocols, or CSF research protocols. Lower values are worse.
- `CNI` — Cognitive Noise Index from reaction-time delta, sustained attention, working memory, subjective fatigue, or sensory load.

## Composite state priority

1. Safety rule.
2. Data validity rule.
3. Evidence-grade rule.
4. Domain-specific risk rule.
5. Control-action rule.
6. Reporting rule.

## Confidence

`confidence = data_completeness × signal_quality × provenance_score × evidence_weight`.

Confidence is technical trust in a specific inference transaction. It is not disease probability.
