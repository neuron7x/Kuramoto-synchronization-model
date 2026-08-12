# GeoSync five-minute proof

## Scope

This proof reduces the repository to one runnable mechanism:

```text
D -> H -> T -> F -> V
```

It does not claim market alpha, profitability, discovered market physics, biological intelligence, AGI, predictive edge, or production readiness.

## Repo scout result

The repository already exposes several evidence and falsification surfaces: `make golden-path` for synthetic data to analysis to backtest, `make evidence` for audit verdicts, mutation ratchets in `make mutation-ratchet`, and surrogate/null-model tooling under `core/kuramoto/falsification.py`. Those paths are larger than a five-minute outsider proof and include terminology that is not needed for a minimal falsifiable mechanism.

The selected mechanism is therefore intentionally smaller: a stdlib-only fixture test for lag-1 directional persistence. It uses a deterministic CSV fixture, generates a hypothesis from the training slice, tests it on the holdout slice, applies a fixed falsifier, and writes a verdict artifact.

## D -> H -> T -> F -> V map

| Stage | File / module | Meaning |
| --- | --- | --- |
| D | `geosync/proof/fixtures/market_fixture.csv` | Deterministic market-like close series. |
| H | `geosync.proof.run.generate_hypothesis` | Choose continuation or reversal from the training slice. |
| T | `geosync.proof.run.run_test` | Score holdout directional hit rate. |
| F | `THRESHOLD = 0.60` | Reject if holdout hit rate is below 0.60. |
| V | `artifacts/geosync_proof/verdict.json` | Machine-readable ACCEPT / REJECT / INCONCLUSIVE verdict. |

## Reproduce

```bash
python -m geosync.proof.run
```

Expected human line:

```text
GEOSYNC_PROOF verdict=REJECT mechanism=lag1_directional_persistence_fixture_test ...
```

Expected artifact:

```text
artifacts/geosync_proof/verdict.json
```

## Interpretation boundary

The default fixture currently rejects the generated continuation hypothesis on holdout data. That means only this: the fixture was loaded, the hypothesis was generated, the deterministic test ran, the metric missed the threshold, and the verdict follows from the falsifier. It does not say anything about real market profitability or predictive edge.
