# Cross-Asset Kuramoto · Lock Audit (Phase 1 of shadow validation)

**Performed UTC:** 2026-04-22.
**Audit outcome: PASS.** All checks LA1–LA8 green. Proceed to Phase 2.

## LA1 · PARAMETER_LOCK.json hash

```
sha256 = 1afd9058f7b5e1512d0a58c7b760da4e75389602d0155b0d83f1a84e567e5132
```

This is the hash printed by the demo-ready runner at commit `7beea0d`
(see demo script's terminal JSON `parameter_lock_sha256`). Identical.

## LA2 · INPUT_CONTRACT.md hash

```
sha256 = 9c6760860ec99de71c0ee92dca57213673ba4e1cd6a284cdd8efbadad0000c78
```

File byte-identical to the commit that locked the demo-ready artefacts.

## LA3 · Universe unchanged

| role | expected | current |
|---|---|---|
| regime universe | `BTC, ETH, SPY, QQQ, GLD, TLT, DXY, VIX` | same |
| strategy universe | `BTC, ETH, SPY, TLT, GLD` | same |

Both enforced by `INV-CAK2` (`tests/core/cross_asset_kuramoto/test_invariants.py::test_cak2_*`).

## LA4 · Cost model unchanged

`cost_bps = 10`, applied as `turnover * cost_bps / 10_000`, round-trip bps
on `|Δw|` turnover per bar. Locked in `PARAMETER_LOCK.json` and enforced
by `INV-CAK5`. Unchanged.

## LA5 · Execution lag unchanged

`execution_lag_bars = 1`. Regime shifted by 1 bar in `simulate_rp_strategy`.
No 0-lag mode used in shadow artefacts. Unchanged.

## LA6 · Demo --verify-only exit 0

```
$ python scripts/demo_cross_asset_kuramoto.py --verify-only
…
36 passed, 1 xfailed in ~3.2s
exit = 0
```

The xfail is `test_r_has_no_future_leak` — Hilbert non-causality,
documented under OBS-1 in `INTEGRATION_NOTES.md` and preserved per §R4.

## LA7 · Invariant suite still passes

Static checks: `mypy --strict`, `ruff check`, `black --check` all clean
on `core/cross_asset_kuramoto/`. Invariants INV-CAK1..8 all PASS in
`tests/core/cross_asset_kuramoto/`.

## LA8 · Known caveats preserved verbatim

| caveat | where | status |
|---|---|---|
| OBS-1: `scipy.signal.hilbert` non-causal | `INTEGRATION_NOTES.md#OBS-1` | preserved, unchanged |
| DP3: demo-snapshot 10–12 days stale | `PIPELINE_AUDIT.md#DP3` | preserved, unchanged |
| DP5: `ffill(limit=3)` material (ΔSharpe = 0.22) | `PIPELINE_AUDIT.md#DP5` | preserved, unchanged |
| fold 3 (2022) posts −1.15 Sharpe | `WALKFORWARD_VERIFICATION.md` | preserved, unchanged |

## Source-of-truth table (read-only inputs for shadow validation)

| artefact | sha256 | consumers |
|---|---|---|
| `results/cross_asset_kuramoto/PARAMETER_LOCK.json` | `1afd9058…` | runner, evaluator |
| `results/cross_asset_kuramoto/INPUT_CONTRACT.md` | `9c676086…` | runner |
| `results/cross_asset_kuramoto/demo/equity_curve.csv` | `4dc9533e…` | envelope builder |
| `core/cross_asset_kuramoto/signal.py` | `7b9bb360…` | runner (import) |
| `core/cross_asset_kuramoto/engine.py` | `2f1dc1c9…` | runner (import) |
| `~/spikes/cross_asset_sync_regime/paper_state/equity.csv` | recomputed each run | evaluator |
| `~/spikes/cross_asset_sync_regime/paper_state/signal_log.jsonl` | recomputed each run | evaluator |

No STOP triggered by §17.S1–S8 during Phase 1.
