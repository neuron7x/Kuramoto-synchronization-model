# Cognitive Dynamics Laboratory

Status: `research_contract`
Claim tier: `simulation-only`
Artifact role: `bounded protocol + replayable deterministic runner`

This directory integrates a cognitive-dynamical laboratory surface for convergence/divergence auditing, excitation/inhibition balance estimation, reality-weight assignment, energy-cost accounting, perturbation testing, falsification, and weight-patch planning.

This is not an AGI claim, brain-equivalence claim, production-readiness claim, or external validation claim. It is a deterministic research scaffold that converts cognitive theory into measurable simulation variables, failure surfaces, and replayable artifacts.

## Contract spine

```text
DEFINE -> MODEL -> MEASURE -> SIMULATE -> PERTURB -> DETECT_HOLES -> REWEIGHT -> FALSIFY -> CALIBRATE -> PATCH
```

## Files

| File | Purpose |
| --- | --- |
| `DEFINITIONS.md` | Operational definitions with signal, failure mode, measurement, and patch implication. |
| `MODEL_SPEC.md` | Minimal state/environment/prediction/E-I/energy/realism model. |
| `METRICS_SPEC.json` | Machine-readable metric formulas, thresholds, and failure triggers. |
| `SIMULATION_PROTOCOL.md` | Replay protocol and pass/fail conditions. |
| `EXPERIMENT_MATRIX.json` | Seven perturbation scenarios for baseline, noise, delay, scarce data, regime shift, adversarial perturbation, and resource constraint. |
| `WEIGHT_PATCHES.json` | Parameter patches with reason, risk, and verification test. |
| `FALSIFICATION_REPORT.json` | Assumption attacks, blocked claims, confidence ceiling, and minimum viable experiments. |
| `NEXT_ITERATION_PLAN.md` | Single next patch: event-triggered sparse update scheduler. |

## Replay command

```bash
python scripts/cognitive_dynamics_lab/simulation_runner.py --out artifacts/cognitive_dynamics_lab
```

Expected outputs:

```text
artifacts/cognitive_dynamics_lab/summary.json
artifacts/cognitive_dynamics_lab/metrics_table.csv
artifacts/cognitive_dynamics_lab/runs/*.json
```

## Claim boundary

Confidence may not exceed:

```text
0.60 = simulation exists with perturbation cases, but stability thresholds are not consistently passed
0.75 = perturbation tests exist with stable metrics
0.85 = repeated runs show robust behavior
0.95 = external real-world data validates dynamic predictions
```

Current integration level: `0.60`. Anything higher without repeated replay artifacts would be ordinary human overclaiming, wearing a lab badge it found in a drawer.
