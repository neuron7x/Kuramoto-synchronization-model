# Cross-Asset Kuramoto · DRO-ARA dependency (Phase 1, §5)

**Verdict: `INDEPENDENT_OF_DRO_ARA`.**
**Scope:** the spike source files and the integrated `core/cross_asset_kuramoto/` module at commit-to-be.

## Evidence (falsifiable)

Direct grep of the three load-bearing spike source files returns zero
matches for DRO-ARA tokens:

```
grep -n -E "dro_ara|DRO-ARA|derive_gamma|stationarity|regime_classifier|INV-DRO" \
    ~/spikes/cross_asset_sync_regime/{sync_regime,backtest_v2,walk_forward}.py
$  (empty output, exit 0)
```

No path inside the spike or the integrated module reads, imports, or
derives a value from the DRO-ARA engine (`core/dro_ara/engine.py`).

## What the spike uses for regime state *instead*

The regime state (`low_sync | mid_sync | high_sync`) is produced by
`sync_regime.py::classify_regimes` from the **rolling Kuramoto order
parameter `R(t)`** and a pair of quantile thresholds `q33, q66`
calibrated on the first 70 % of the regime-universe sample
(§PARAMETER_LOCK.regime_threshold_train_frac = 0.70). This is a
self-contained Kuramoto-derived classification and makes no call into
DRO-ARA's γ / ADF-based stationarity vocabulary.

## Implication for integration

- No DRO-ARA commit needs to be pinned.
- No `INV-DRO*` invariant applies to `core/cross_asset_kuramoto/`.
- `INV-K1` (`0 ≤ R(t) ≤ 1`) *does* apply and is carried into
  `invariants.py` via `INV-CAK3`.
- Integration does **not** block on the DRO-ARA patch PR track.

Per §RDA3, the dependency status is unambiguous; no STOP triggered.
