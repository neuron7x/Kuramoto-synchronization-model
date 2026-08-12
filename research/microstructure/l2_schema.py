"""Canonical L2 schema for Binance depth@100ms stream.

Each row is one depth snapshot at time `ts_event` (exchange event time,
milliseconds since epoch) for `symbol`. Levels are stored as flat columns
`bid_px_k` / `bid_sz_k` / `ask_px_k` / `ask_sz_k` for k ∈ [1, N_LEVELS].
Level 1 is the top-of-book.

INV-HPC1: deterministic schema — every writer produces the exact same
column order & dtypes, so parquet shards concatenate bit-identical.
"""

from __future__ import annotations

from typing import Final

import pyarrow as pa

N_LEVELS: Final[int] = 5


def level_columns(n_levels: int = N_LEVELS) -> list[str]:
    cols: list[str] = []
    for k in range(1, n_levels + 1):
        cols.extend([f"bid_px_{k}", f"bid_sz_{k}", f"ask_px_{k}", f"ask_sz_{k}"])
    return cols


def l2_schema(n_levels: int = N_LEVELS) -> pa.Schema:
    fields: list[pa.Field] = [
        pa.field("ts_event", pa.int64(), nullable=False),
        pa.field("ts_ingest", pa.int64(), nullable=False),
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("update_id", pa.int64(), nullable=False),
    ]
    for k in range(1, n_levels + 1):
        fields.extend(
            [
                pa.field(f"bid_px_{k}", pa.float64(), nullable=False),
                pa.field(f"bid_sz_{k}", pa.float64(), nullable=False),
                pa.field(f"ask_px_{k}", pa.float64(), nullable=False),
                pa.field(f"ask_sz_{k}", pa.float64(), nullable=False),
            ]
        )
    return pa.schema(fields)


DEFAULT_SYMBOLS: Final[tuple[str, ...]] = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "DOTUSDT",
    "POLUSDT",
)
