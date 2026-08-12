# ADVERSARIAL_LADDER — research/systemic_risk

> Don't prove Kuramoto. Build a system where Kuramoto must lose to
> everything simpler — and only if it doesn't lose, a fact is born.

The ladder is the operationalisation of
``feedback_hypothesis_destruction_machine.md``: a verdict machine
whose **default output is GUILTY**. Acquittal requires the
candidate to clear *every* engaged prosecutor on a paired-bootstrap
delta-AUC with the CI lower bound clearing
``LadderConfig.delta_floor`` (default ``0.0``).

## Eight rungs

| Rung | Name                       | Source of evidence (autonomous?) |
|------|----------------------------|----------------------------------|
| 1    | Naive baselines            | yes — `baselines.rolling_volatility_score`, `baselines.edge_density_score` |
| 2    | Null surrogates            | yes — six generators in `null_models.py` (composed via `run_null_audit`) |
| 3    | Leakage traps              | yes — `test_critical_slowing_down.test_no_lookahead_leakage`, transpose-bug 2×2, full-sample normalisation refusal |
| 4    | Data-friction audit        | **NO** — needs real e-MID / BIS / ECB ingest |
| 5    | Parameter fragility        | yes — `parameter_fragility_audit` |
| 6    | Cross-implementation       | **NO** — needs second engineer rewriting from spec |
| 7    | Replication                | **NO** — needs independent operator + clean env |
| 8    | Prospective                | **NO** — needs locked detector + next labelled crisis |

The four ``NO`` rungs structurally cannot be cleared by any
autonomous run; they live in
``LadderReport.untested_rungs`` so the gap between
``ACQUITTED_ENGAGED`` and full ``ACQUITTED`` is permanent and
visible.

## Verdict ladder

```
INSUFFICIENT_RUNGS  ← zero prosecutors engaged
       │
       ▼
GUILTY              ← any engaged prosecutor not beaten (delta_ci_low ≤ delta_floor)
       │
       ▼
ACQUITTED_ENGAGED   ← every engaged prosecutor beaten; rungs 4/6/7/8
                      typically remain untested → not full ACQUITTED
       │
       ▼
ACQUITTED           ← all 8 rungs cleared (rungs 4/6/7/8 require
                      external evidence; not emittable autonomously)
```

The system can never autonomously emit ``ACQUITTED``. That's the
point — only an external evidence chain can close the four
non-autonomous rungs.

## Reporting contract

`LadderReport` always reports:

* `verdict` — one of the four enum values above
* `outcomes` — per-prosecutor evidence, in the order supplied
* `survival_paths` — names of prosecutors the candidate beat
* `losing_paths` — names of prosecutors the candidate lost or tied
* `lowest_rung_loss` — smallest rung index at which the candidate
  was not beaten (`None` when verdict ≠ GUILTY)
* `untested_rungs` — rungs in 1..8 with zero prosecutors supplied

The headline rule from
``feedback_hypothesis_destruction_machine.md``:

> A candidate that has beaten 3 prosecutors and not been tested
> by 12 is at HYPOTHESIS, not "promising".

## Paired bootstrap

For each crisis label common to candidate and prosecutor, the
ladder records the pair `(AUC_candidate, AUC_prosecutor)`. The
delta is computed as the difference of paired means, and a
percentile bootstrap with `LadderConfig.n_bootstrap` resamples
provides the CI on the delta. The seed is recorded in
`LadderConfig.seed` and emitted in any downstream
`RunManifest`.

## Composed null audit (`run_null_audit`)

Closes the PATH B deferral declared in `null_models.py`:
the function is now a thin orchestrator that pins each supplied
null surrogate to rung 2 and runs the ladder. The six canonical
surrogates (`shuffled_time_labels`, `random_exposure_weights`,
`static_topology_baseline`, `linear_correlation_surrogate`,
`permuted_crisis_dates`, `degree_preserving_randomization`) must
be pre-computed by the caller — `run_null_audit` does not invent
them, it only renders the verdict.

## Parameter fragility (`parameter_fragility_audit`)

Sweep one `FalsificationConfig` knob over a tuple of values.
Returns per-value AUC + verdict + the AUC range. The sweep is
fragile when `auc_range >= fragility_tolerance` — the candidate's
verdict depends on the parameter choice, so reporting the
single-point AUC alone is dishonest. Sweep-eligible knobs are
the integer / float fields of `FalsificationConfig`.

## What this PR does NOT promote

C-SYSRISK-PHASE remains `HYPOTHESIS / SCORE-LEVEL INSTRUMENTATION
EXTENSION ONLY`. The ladder *organises* the available adversarial
evidence; it does not generate empirical evidence on its own.
Real-data ingest (rung 4) and the three external rungs (6/7/8)
remain the only paths to a higher tier.
