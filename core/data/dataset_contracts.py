# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Shared dataset governance contracts for repository-managed assets.

The contracts defined here act as the single source of truth for provenance,
schema expectations, and semantic invariants that the governance tooling
enforces. Validation scripts and fingerprint utilities import this module to
avoid drifting definitions across CLI entrypoints and tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class DatasetContract:
    """Contract describing a governed dataset shipped with the repository."""

    dataset_id: str
    path: Path
    schema_version: str
    columns: Sequence[str]
    dtypes: Sequence[str]
    origin: str
    description: str
    creation_method: str
    temporal_coverage: str
    intended_use: str
    forbidden_use: str
    semantic_rules: Mapping[str, object] = field(default_factory=dict)

    @property
    def meta_path(self) -> Path:
        return self.path.with_suffix(self.path.suffix + ".meta.json")


def _dataset_path(relative: str) -> Path:
    return REPO_ROOT / relative


DATASET_CONTRACTS: List[DatasetContract] = [
    DatasetContract(
        dataset_id="sample-timeseries-v1",
        path=_dataset_path("data/sample.csv"),
        schema_version="1.0.0",
        columns=["ts", "price", "volume"],
        dtypes=["int", "float", "int"],
        origin="synthetic",
        description="Synthetic price/volume sequence for smoke tests.",
        creation_method="scripts/generate_sample_ohlcv.py (single-asset sample preset)",
        temporal_coverage="500 sequential steps",
        intended_use="backtest",
        forbidden_use="not for live trading",
        semantic_rules={
            "timestamp_column": "ts",
            "monotonic": True,
            "non_negative": ["volume"],
            "positive_fields": ["price"],
            "no_nulls": True,
        },
    ),
    DatasetContract(
        dataset_id="sample-ohlc-v1",
        path=_dataset_path("data/sample_ohlc.csv"),
        schema_version="1.0.0",
        columns=["ts", "open", "high", "low", "close", "volume"],
        dtypes=["int", "float", "float", "float", "float", "int"],
        origin="synthetic",
        description="Synthetic OHLCV bars for indicator and strategy regression coverage.",
        creation_method="scripts/generate_sample_ohlcv.py (OHLC sample preset)",
        temporal_coverage="300 sequential bars",
        intended_use="backtest",
        forbidden_use="not for live trading",
        semantic_rules={
            "timestamp_column": "ts",
            "monotonic": True,
            "non_negative": ["volume"],
            "ohlc_fields": {
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
            },
            "no_nulls": True,
        },
    ),
    DatasetContract(
        dataset_id="sample-crypto-ohlcv-v1",
        path=_dataset_path("data/sample_crypto_ohlcv.csv"),
        schema_version="1.0.0",
        columns=["timestamp", "symbol", "open", "high", "low", "close", "volume"],
        dtypes=["str", "str", "float", "float", "float", "float", "float"],
        origin="synthetic",
        description="Synthetic multi-asset crypto OHLCV data (BTC, ETH, SOL).",
        creation_method="scripts/generate_sample_ohlcv.py --symbols BTC ETH SOL --days 21 --timeframe 1h",
        temporal_coverage="504 hourly bars across 3 assets starting 2024-01-01",
        intended_use="backtest",
        forbidden_use="not for live trading",
        semantic_rules={
            "timestamp_column": "timestamp",
            "monotonic": True,
            "partition_by": ["symbol"],
            "non_negative": ["volume"],
            "ohlc_fields": {
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
            },
            "no_nulls": True,
        },
    ),
    DatasetContract(
        dataset_id="sample-stocks-daily-v1",
        path=_dataset_path("data/sample_stocks_daily.csv"),
        schema_version="1.0.0",
        columns=["timestamp", "symbol", "open", "high", "low", "close", "volume"],
        dtypes=["str", "str", "float", "float", "float", "float", "float"],
        origin="synthetic",
        description="Synthetic daily OHLCV bars for equities (AAPL, SPY).",
        creation_method="scripts/generate_sample_ohlcv.py --symbols AAPL SPY --days 60 --timeframe 1d",
        temporal_coverage="60 daily bars starting 2024-01-01",
        intended_use="backtest",
        forbidden_use="not for live trading",
        semantic_rules={
            "timestamp_column": "timestamp",
            "monotonic": True,
            "partition_by": ["symbol"],
            "non_negative": ["volume"],
            "ohlc_fields": {
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
            },
            "no_nulls": True,
        },
    ),
    DatasetContract(
        dataset_id="indicator-macd-baseline-v1",
        path=_dataset_path("data/golden/indicator_macd_baseline.csv"),
        schema_version="1.0.0",
        columns=["ts", "close", "ema_12", "ema_26", "macd", "signal", "histogram"],
        dtypes=["str", "float", "float", "float", "float", "float", "float"],
        origin="curated",
        description="Baseline MACD indicator output for regression testing.",
        creation_method="analytics/macd baseline generation (curated test fixture)",
        temporal_coverage="5 one-minute bars starting 2024-01-01T00:00Z",
        intended_use="certification",
        forbidden_use="not for live trading",
        semantic_rules={
            "timestamp_column": "ts",
            "monotonic": True,
            "non_negative": [],
            "no_nulls": True,
            "positive_fields": [],
        },
    ),
]


def iter_contracts() -> Iterable[DatasetContract]:
    return tuple(DATASET_CONTRACTS)


def contract_by_path(path: Path) -> DatasetContract | None:
    for contract in DATASET_CONTRACTS:
        if contract.path.resolve() == path.resolve():
            return contract
    return None


def contract_by_id(dataset_id: str) -> DatasetContract | None:
    for contract in DATASET_CONTRACTS:
        if contract.dataset_id == dataset_id:
            return contract
    return None


__all__ = [
    "DATASET_CONTRACTS",
    "DatasetContract",
    "contract_by_id",
    "contract_by_path",
    "iter_contracts",
]
