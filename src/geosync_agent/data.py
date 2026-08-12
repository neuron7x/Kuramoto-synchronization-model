# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Data preparation utilities for GeoSync trading agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from application.system import GeoSyncSystem

from .config import AgentDataFeedConfig


@dataclass(slots=True)
class LoadedData:
    """Container bundling raw market data with engineered features."""

    market_frame: pd.DataFrame
    feature_frame: pd.DataFrame


class AgentDataLoader:
    """Load, validate, and feature-engineer datasets for RL agents."""

    def __init__(self, system: GeoSyncSystem) -> None:
        self._system = system
        self._price_column = system.feature_pipeline.config.price_col

    def load_market_data(self, config: AgentDataFeedConfig) -> pd.DataFrame:
        """Return a cleaned market frame indexed by UTC timestamps."""

        resolved = config.resolve_path()
        frame = pd.read_csv(resolved)
        if config.timestamp_field not in frame.columns:
            raise KeyError(f"Timestamp field '{config.timestamp_field}' missing from {resolved}")

        timestamp_series = pd.to_datetime(
            frame[config.timestamp_field], unit=config.timestamp_unit, utc=True
        )
        market = frame.drop(columns=[config.timestamp_field]).copy()
        market.index = timestamp_series
        market.sort_index(inplace=True)

        required: Iterable[str] = config.required_fields
        required_set = set(required)
        missing = [col for col in required if col not in market.columns]
        if missing:
            raise KeyError(f"Missing required columns: {missing}")

        numeric_market = market.apply(pd.to_numeric, errors="coerce")
        all_nan_columns = [
            col for col in numeric_market.columns if numeric_market[col].isna().all()
        ]
        if all_nan_columns:
            problematic_required = [
                col for col in all_nan_columns if col in required_set or col == config.price_field
            ]
            if problematic_required:
                raise ValueError(
                    "Required numeric columns contain no valid values: "
                    f"{sorted(problematic_required)}"
                )
            numeric_market = numeric_market.drop(columns=all_nan_columns)

        market = numeric_market.astype(float)
        market.replace([np.inf, -np.inf], np.nan, inplace=True)
        market.dropna(how="any", inplace=True)
        if market.empty:
            raise ValueError("No valid rows remain after cleaning market data")

        if self._price_column not in market.columns:
            market.rename(columns={config.price_field: self._price_column}, inplace=True)
        return market

    def build_feature_frame(self, market_frame: pd.DataFrame) -> pd.DataFrame:
        """Construct the feature frame used as state representation."""

        features = self._system.build_feature_frame(market_frame)
        if features.empty:
            raise ValueError("Feature frame is empty after engineering step")
        features = features.replace([np.inf, -np.inf], np.nan).dropna()
        return features

    def load(self, config: AgentDataFeedConfig) -> LoadedData:
        """Return market and feature frames for *config*."""

        market = self.load_market_data(config)
        feature_frame = self.build_feature_frame(market)
        feature_frame = feature_frame.dropna()
        if feature_frame.empty:
            raise ValueError("Aligned data frame is empty")
        market_frame = feature_frame[market.columns]
        return LoadedData(market_frame=market_frame, feature_frame=feature_frame)
