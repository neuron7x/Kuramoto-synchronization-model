"""VLPO-inspired denoising pipeline for telemetry data."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .correlation import forget_low_correlation
from .entropy import downscale_low_entropy
from ..data.sensory_calibrator import SensoryCalibrator, SensoryCalibrationConfig


@dataclass(slots=True)
class FilterStats:
    """Summary statistics captured during filtering."""

    entropy_before: float
    entropy_after: float
    correlation_before: float
    correlation_after: float


class VLPOCoreFilter:
    """Sleep-inspired denoising for controller metrics.

    The filter implements four stages:

    1. **Glymphatic clearance** – drop duplicate feature rows while preserving
       ordering.
    2. **SHY downscaling** – attenuate low-entropy signals.
    3. **REM forgetting** – zero-out features with weak correlation to the
       target signal.
    4. **Stitching** – rebuild a dataframe with the original index to keep
       synchronisation with upstream collectors intact.
    """

    def __init__(
        self,
        *,
        entropy_threshold: float = 2.5,
        correlation_threshold: float = 0.3,
        scale_factor: float = 0.5,
        calibration_mode: str = "ema_minmax",
        calibration_window: int = 256,
        calibration_alpha: float = 0.2,
        quantile_low: float = 0.05,
        quantile_high: float = 0.95,
    ) -> None:
        self.entropy_threshold = entropy_threshold
        self.correlation_threshold = correlation_threshold
        self.scale_factor = scale_factor
        self.last_stats: dict[str, FilterStats] = {}
        self._calibration_config = SensoryCalibrationConfig(
            mode=calibration_mode,
            calibration_window=calibration_window,
            ema_alpha=calibration_alpha,
            quantile_low=quantile_low,
            quantile_high=quantile_high,
        )
        self._calibrator: SensoryCalibrator | None = None

    def _ensure_calibrator(self, feature_columns: list[str]) -> None:
        if not feature_columns:
            return
        if self._calibrator is None or self._calibrator.channels != tuple(
            feature_columns
        ):
            self._calibrator = SensoryCalibrator(
                feature_columns, config=self._calibration_config
            )

    @staticmethod
    def _glymphatic_clearance(data: pd.DataFrame) -> pd.DataFrame:
        if data.empty:
            return data.copy()
        # ``keep='first'`` preserves order and keeps index for later reindexing.
        deduplicated = data.loc[~data.duplicated(subset=data.columns, keep="first")]
        return deduplicated

    def _vlpo_switch(self, signal: np.ndarray, target: np.ndarray) -> np.ndarray:
        downscaled = downscale_low_entropy(
            signal,
            threshold=self.entropy_threshold,
            scale_factor=self.scale_factor,
        )
        filtered = forget_low_correlation(
            downscaled,
            target,
            threshold=self.correlation_threshold,
        )
        return filtered

    def filter(self, data: pd.DataFrame, *, target_col: str = "target") -> pd.DataFrame:
        if target_col not in data.columns:
            raise ValueError(f"Target column '{target_col}' missing from dataframe")
        if data.empty:
            return data.copy()

        cleaned = self._glymphatic_clearance(data)
        features = cleaned.drop(columns=[target_col])
        if not features.empty:
            self._ensure_calibrator(list(features.columns))
            if self._calibrator is not None:
                features = self._calibrator.normalize(features)
        cleaned_target = cleaned[target_col].to_numpy(dtype=float)

        filtered_columns: dict[str, np.ndarray] = {}
        stats: dict[str, FilterStats] = {}

        for column in features.columns:
            signal = cleaned[column].to_numpy(dtype=float)
            filtered_signal = self._vlpo_switch(signal, cleaned_target)

            entropy_before = float(np.nan_to_num(self._entropy(signal)))
            entropy_after = float(np.nan_to_num(self._entropy(filtered_signal)))
            corr_before = float(
                np.nan_to_num(self._correlation(signal, cleaned_target))
            )
            corr_after = float(
                np.nan_to_num(self._correlation(filtered_signal, cleaned_target))
            )

            filtered_columns[column] = filtered_signal
            stats[column] = FilterStats(
                entropy_before=entropy_before,
                entropy_after=entropy_after,
                correlation_before=corr_before,
                correlation_after=corr_after,
            )

        filtered_df = pd.DataFrame(filtered_columns, index=cleaned.index)
        filtered_df[target_col] = cleaned_target

        # Re-align with the original index so the caller retains one-to-one
        # mapping with the telemetry feed. Missing rows (due to deduplication)
        # are forward-filled to avoid shrinking the dataset.
        reindexed = filtered_df.reindex(data.index)
        reindexed[target_col] = data[target_col].to_numpy(dtype=float)
        reindexed = reindexed.ffill().bfill()

        self.last_stats = stats
        return reindexed

    @staticmethod
    def _entropy(values: np.ndarray) -> float:
        from .entropy import compute_shannon_entropy

        return compute_shannon_entropy(values)

    @staticmethod
    def _correlation(values: np.ndarray, target: np.ndarray) -> float:
        from .correlation import compute_pearson_correlation

        return compute_pearson_correlation(values, target)


__all__ = ["VLPOCoreFilter", "FilterStats"]
