# DATA INVENTORY (draft)

This inventory captures the datasets shipped under `data/` and the embedded fixtures referenced by tests. Row counts and sizes are approximate and derived from the current repository state.

| dataset_id | path | rows | schema (name:dtype) | size | intended_use | referenced_by |
| --- | --- | --- | --- | --- | --- | --- |
| `sample-timeseries-v1` | `data/sample.csv` | 500 | ts:int, price:float, volume:int | ~13.8 KB | backtest | `scripts/smoke_e2e.py`, `scripts/validate_sample_data.py`, `tests/data/test_quality_gate.py`, docs quickstarts |
| `sample-ohlc-v1` | `data/sample_ohlc.csv` | 300 | ts:int, open:float, high:float, low:float, close:float, volume:int | ~13 KB | backtest | `tests/data/test_quality_gate.py`, docs/data guides |
| `sample-crypto-ohlcv-v1` | `data/sample_crypto_ohlcv.csv` | 504 | timestamp:str, symbol:str, open:float, high:float, low:float, close:float, volume:float | ~38 KB | backtest | `scripts/validate_ohlcv_data.py`, neuro serotonin property tests |
| `sample-stocks-daily-v1` | `data/sample_stocks_daily.csv` | 60 | timestamp:str, symbol:str, open:float, high:float, low:float, close:float, volume:float | ~4.6 KB | backtest | portfolio demos (docs/data) |
| `indicator-macd-baseline-v1` | `data/golden/indicator_macd_baseline.csv` | 5 | ts:str, close:float, ema_12:float, ema_26:float, macd:float, signal:float, histogram:float | ~0.4 KB | certification | `tests/unit/data/test_golden_datasets.py`, indicator regression docs |

## Embedded fixtures

- `tests/fixtures/recordings/*.metadata.json`: synthetic market recordings used by replay/regression suites.
- `tests/unit/data/test_data_path_guard.py` and related fixtures guard against accidental writes outside `data/`.

## Assumptions & constraints

- Timestamps are monotonic within each dataset (no backward steps).
- OHLCV datasets enforce `low <= open/close <= high` and non-negative volume.
- No nulls or empty fields are permitted in the governed datasets.
- Golden baselines must remain unchanged unless schema_version is bumped.
