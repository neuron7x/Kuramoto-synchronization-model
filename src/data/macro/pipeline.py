# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Pipeline orchestrating macroeconomic data ingestion and feature generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable, Mapping

import pandas as pd

from ..etl.stores import (
    AuditEntry,
    AuditLog,
    CatalogEntry,
    DataCatalog,
    dataframe_signature,
)
from .clients import MacroDataClient
from .feature_engineering import MacroFeatureBuilder
from .models import MacroDataSet, MacroIndicatorConfig

__all__ = ["MacroSignalPipeline", "MacroPipelineContext"]


@dataclass(slots=True)
class MacroPipelineContext:
    """Shared context objects used by the macro pipeline."""

    catalog: DataCatalog
    audit_log: AuditLog


class MacroSignalPipeline:
    """Coordinate fetching, transformation and cataloguing of macro signals."""

    def __init__(
        self,
        *,
        clients: Mapping[str, MacroDataClient],
        feature_builder: MacroFeatureBuilder | None = None,
        context: MacroPipelineContext | None = None,
    ) -> None:
        if not clients:
            raise ValueError("At least one macro data client must be provided")
        self._clients = dict(clients)
        self._feature_builder = feature_builder or MacroFeatureBuilder()
        self._context = context or MacroPipelineContext(
            catalog=DataCatalog(),
            audit_log=AuditLog(),
        )

    @property
    def catalog(self) -> DataCatalog:
        return self._context.catalog

    @property
    def audit_log(self) -> AuditLog:
        return self._context.audit_log

    def run(
        self,
        indicators: Iterable[MacroIndicatorConfig],
        *,
        start: datetime,
        end: datetime | None = None,
        extra_params: Mapping[str, Mapping[str, object]] | None = None,
        run_id: str | None = None,
    ) -> pd.DataFrame:
        """Execute the pipeline and return engineered macro features."""

        datasets: list[MacroDataSet] = []
        run_started_at = datetime.now(UTC)
        run_identifier = run_id or f"macro-{run_started_at.strftime('%Y%m%d%H%M%S')}"

        for indicator in indicators:
            client = self._clients.get(indicator.source)
            if client is None:
                raise ValueError(
                    f"No client registered for source '{indicator.source}'"
                )

            params = (extra_params or {}).get(indicator.code, {})
            frame = client.fetch_series(
                indicator.code, start=start, end=end, params=params
            )
            if indicator.consensus_indicator:
                consensus_frame = client.fetch_series(
                    indicator.consensus_indicator,
                    start=start,
                    end=end,
                    params=params,
                )
                if not consensus_frame.empty:
                    frame = frame.merge(
                        consensus_frame[["period_end", "value"]].rename(
                            columns={"value": "consensus"}
                        ),
                        on="period_end",
                        how="left",
                        suffixes=("", "_consensus"),
                    )

            frame = self._harmonise_frequency(frame, indicator)
            frame = self._apply_transformations(frame, indicator)
            if not frame.empty:
                datasets.append(MacroDataSet(indicator=indicator, frame=frame))

        feature_frames = [dataset.ensure_sorted() for dataset in datasets]
        features = self._feature_builder.build(frame for frame in feature_frames)

        if not features.empty:
            self._register_dataset(features, run_identifier, run_started_at)

        return features

    def _harmonise_frequency(
        self, frame: pd.DataFrame, indicator: MacroIndicatorConfig
    ) -> pd.DataFrame:
        if frame.empty:
            return frame

        resampled = frame.copy()

        if "period_end" not in resampled.columns:
            raise ValueError(
                f"Macro dataset for {indicator.code} missing 'period_end' column"
            )
        if "value" not in resampled.columns:
            raise ValueError(
                f"Macro dataset for {indicator.code} missing 'value' column"
            )

        if "indicator" not in resampled.columns:
            resampled["indicator"] = indicator.code
        else:
            resampled["indicator"] = resampled["indicator"].fillna(indicator.code)

        resampled["period_end"] = pd.to_datetime(resampled["period_end"], utc=True)
        freq = self._normalise_frequency(indicator.target_frequency)
        harmonised: list[pd.DataFrame] = []
        for code, group in resampled.groupby("indicator"):
            local = (
                group.sort_values("period_end")
                .set_index("period_end")
                .resample(freq)
                .last()
                .ffill()
                .reset_index()
            )
            local["indicator"] = code
            harmonised.append(local)
        resampled = (
            pd.concat(harmonised, ignore_index=True) if harmonised else resampled
        )
        has_release_date = "release_date" in resampled.columns
        if has_release_date:
            resampled["release_date"] = pd.to_datetime(
                resampled["release_date"], utc=True, errors="coerce"
            )
        else:
            resampled["release_date"] = resampled["period_end"]
        if "consensus" in resampled.columns:
            resampled["consensus"] = pd.to_numeric(
                resampled["consensus"], errors="coerce"
            )
        resampled["value"] = pd.to_numeric(resampled["value"], errors="coerce")
        lag = pd.to_timedelta(indicator.release_lag)
        availability_anchor = resampled["release_date"].fillna(resampled["period_end"])
        if "available_at" in resampled.columns:
            resampled["available_at"] = pd.to_datetime(
                resampled["available_at"], utc=True, errors="coerce"
            )
            missing_available = resampled["available_at"].isna()
            if missing_available.any():
                resampled.loc[missing_available, "available_at"] = (
                    availability_anchor[missing_available] + lag
                )
        else:
            resampled["available_at"] = availability_anchor + lag
        return resampled

    def _apply_transformations(
        self, frame: pd.DataFrame, indicator: MacroIndicatorConfig
    ) -> pd.DataFrame:
        transforms = indicator.transformations or {}
        if not transforms:
            return frame

        result = frame.copy()
        series = result["value"].astype(float)

        if "rolling_mean" in transforms:
            window = int(transforms["rolling_mean"])
            result["value_mean"] = series.rolling(window, min_periods=1).mean()

        if "diff" in transforms:
            periods = int(transforms["diff"])
            result[f"value_diff_{periods}"] = series.diff(periods)

        if "pct_change" in transforms:
            periods = int(transforms["pct_change"])
            result[f"value_pct_change_{periods}"] = series.pct_change(periods)

        return result

    def _register_dataset(
        self, features: pd.DataFrame, run_id: str, started_at: datetime
    ) -> None:
        signature = dataframe_signature(features)
        entry = CatalogEntry(
            name="macro_features",
            version=str(len(self.catalog.history("macro_features")) + 1),
            created_at=datetime.now(UTC),
            schema_signature=signature,
            row_count=len(features),
            source_run_id=run_id,
        )
        self.catalog.register(entry)
        finished_at = datetime.now(UTC)
        self.audit_log.record(
            AuditEntry(
                run_id=run_id,
                segment="macro_features",
                status="success",
                started_at=started_at,
                finished_at=finished_at,
                details={"rows": len(features)},
            )
        )

    @staticmethod
    def _normalise_frequency(target: str) -> str:
        mapping = {
            "M": "ME",
            "Q": "QE",
            "A": "YE",
        }
        return mapping.get(target, target)
