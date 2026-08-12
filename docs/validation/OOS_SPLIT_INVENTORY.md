# OOS / Train-Test Split Inventory (Task 16)

Maps every train/test, walk-forward, and calibration split on a claim-bearing
path and the leakage-protection mechanism each one carries. The conclusion is a
**preserved negative result**: after #1288, no claim-bearing OOS path was found
without leakage protection. A candidate (`cross_asset_kuramoto/signal.py`) was
inspected and **cleared** — it fits global quantile thresholds on the train
fraction (an aggregate, not a boundary-sensitive predictor), so no embargo is
required.

No scientific or predictive claim. This is a structural inventory plus a
**regression guard**: the checker
[`tools/validation/check_oos_split_inventory.py`](../../tools/validation/check_oos_split_inventory.py)
fails closed if a path declared protected loses its protection marker.

| Path | Split kind | Protection | Marker |
|------|-----------|-----------|--------|
| `core/kuramoto/oos_validation.py` | temporal + walk-forward | embargo invariant (#1288) | `embargo` |
| `backtest/time_splits.py` | purged walk-forward k-fold | `embargo_pct` + `_purge_overlaps` | `embargo` |
| `backtest/engine.py` | walk-forward backtest | anti-look-ahead signal lag | `look-ahead` / `enforce_signal_lag` |
| `research/microstructure/cv.py` | cross-validation | embargo | `embargo` |
| `core/cross_asset_kuramoto/signal.py` | global-quantile calibration | structurally safe (global aggregate, no boundary predictor) | — |

## Machine-readable inventory (validated)

<!-- OOS-SPLIT-DATA -->
```json
{
  "schema_version": 1,
  "splits": [
    {"path": "core/kuramoto/oos_validation.py", "protection": "EMBARGO", "marker": "embargo"},
    {"path": "backtest/time_splits.py", "protection": "EMBARGO", "marker": "embargo"},
    {"path": "backtest/engine.py", "protection": "LOOKAHEAD_LAG", "marker": "look-ahead"},
    {"path": "research/microstructure/cv.py", "protection": "EMBARGO", "marker": "embargo"},
    {"path": "core/cross_asset_kuramoto/signal.py", "protection": "GLOBAL_AGGREGATE_NO_BOUNDARY_LEAK", "marker": null}
  ]
}
```
