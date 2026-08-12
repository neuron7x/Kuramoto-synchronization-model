# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Utility helpers for preparing telemetry dataframes."""

from __future__ import annotations

import pandas as pd

from .sensory_calibrator import SensoryCalibrator, SensoryCalibrationConfig


def prepare_timeseries(
    data: pd.DataFrame,
    *,
    target_col: str,
    calibrator: SensoryCalibrator | None = None,
) -> pd.DataFrame:
    """Scale non-target columns to ``[0, 1]`` while keeping the target intact."""

    if target_col not in data.columns:
        raise ValueError(f"Target column '{target_col}' missing from dataframe")

    feature_columns = [col for col in data.columns if col != target_col]
    features = data[feature_columns]
    if calibrator is None:
        calibrator = SensoryCalibrator(
            feature_columns, config=SensoryCalibrationConfig()
        )

    scaled = calibrator.normalize(features)
    scaled[target_col] = data[target_col].to_numpy()
    return scaled


__all__ = ["prepare_timeseries", "SensoryCalibrator", "SensoryCalibrationConfig"]
