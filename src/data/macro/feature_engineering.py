# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Feature engineering utilities for macroeconomic time series."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

__all__ = ["MacroFeatureBuilder", "MacroFeatureConfig"]


@dataclass(slots=True)
class MacroFeatureConfig:
    """Window configuration for common macroeconomic features."""

    z_score_window: int = 60
    momentum_windows: tuple[int, ...] = (3, 6, 12)
    year_over_year_periods: int = 12


class MacroFeatureBuilder:
    """Derive engineered features from raw macroeconomic data sets."""

    def __init__(self, config: MacroFeatureConfig | None = None) -> None:
        self._config = config or MacroFeatureConfig()

    def build(self, datasets: Iterable[pd.DataFrame]) -> pd.DataFrame:
        """Combine and transform a sequence of macroeconomic data frames."""

        frames = [frame.copy() for frame in datasets if not frame.empty]
        if not frames:
            return pd.DataFrame()

        combined = pd.concat(frames, ignore_index=True, sort=False)
        combined = combined.sort_values(["indicator", "period_end"]).reset_index(
            drop=True
        )

        frames = [
            self._build_indicator_features(group)
            for _, group in combined.groupby("indicator", sort=False)
        ]
        return pd.concat(frames, ignore_index=True)

    def _build_indicator_features(self, frame: pd.DataFrame) -> pd.DataFrame:
        cfg = self._config
        frame = frame.copy()
        frame["value"] = frame["value"].astype(float)

        frame["z_score"] = self._rolling_z_score(frame["value"], cfg.z_score_window)

        for window in cfg.momentum_windows:
            label = f"momentum_{window}m"
            frame[label] = frame["value"].pct_change(window)

        frame["yoy_change"] = frame["value"].pct_change(cfg.year_over_year_periods)

        if "consensus" in frame.columns:
            frame["surprise"] = frame["value"] - frame["consensus"]

        frame["release_gap_days"] = (
            frame["release_date"] - frame["period_end"]
        ).dt.days

        meta_columns = self._extract_meta_columns(frame)
        ordered_cols = [
            "indicator",
            "period_end",
            "release_date",
            "value",
            "z_score",
            "yoy_change",
            "release_gap_days",
        ]
        ordered_cols += [col for col in frame.columns if col.startswith("momentum_")]
        if "surprise" in frame.columns:
            ordered_cols.append("surprise")
        extra_columns = [
            col
            for col in frame.columns
            if col not in ordered_cols and col not in meta_columns
        ]
        ordered_cols += sorted(extra_columns)
        ordered_cols += sorted(meta_columns - set(ordered_cols))

        return frame[ordered_cols]

    @staticmethod
    def _rolling_z_score(series: pd.Series, window: int) -> pd.Series:
        if window <= 1:
            return pd.Series(np.zeros(len(series)), index=series.index)
        mean = series.rolling(window=window, min_periods=window // 3).mean()
        std = series.rolling(window=window, min_periods=window // 3).std(ddof=0)
        z = (series - mean) / std
        return z.replace([np.inf, -np.inf], np.nan)

    @staticmethod
    def _extract_meta_columns(frame: pd.DataFrame) -> set[str]:
        return {col for col in frame.columns if col.startswith("meta_")}
