"""Offline/online feature parity coordination helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from typing import Iterable, Sequence

import pandas as pd
from pandas.api import types as pd_types

from core.data.feature_store import IntegrityReport, OnlineFeatureStore


class FeatureParityError(RuntimeError):
    """Base error for offline/online parity coordination."""


class FeatureUpdateBlocked(FeatureParityError):
    """Raised when feature updates violate configured guardrails."""


class FeatureTimeSkewError(FeatureParityError):
    """Raised when clock skew between offline and online payloads is excessive."""


@dataclass(frozen=True)
class FeatureParitySpec:
    """Configuration describing parity expectations for a feature view."""

    feature_view: str
    entity_columns: tuple[str, ...] = ("entity_id",)
    timestamp_column: str = "ts"
    timestamp_granularity: str | pd.Timedelta | None = None
    numeric_tolerance: float | None = 0.0
    max_clock_skew: pd.Timedelta | None = pd.Timedelta(0)
    allow_schema_evolution: bool = False
    value_columns: tuple[str, ...] | None = None


@dataclass(frozen=True)
class FeatureParityReport:
    """Parity outcome with integrity metadata and drift diagnostics."""

    feature_view: str
    integrity: IntegrityReport
    inserted_rows: int
    updated_rows: int
    dropped_rows: int
    max_value_drift: float | None
    clock_skew: pd.Timedelta | None
    clock_skew_abs: pd.Timedelta | None
    columns_added: tuple[str, ...]
    columns_removed: tuple[str, ...]


class FeatureParityCoordinator:
    """Coordinate offline payloads with online materialisations."""

    def __init__(self, store: OnlineFeatureStore) -> None:
        self._store = store

    def synchronize(
        self,
        spec: FeatureParitySpec,
        frame: pd.DataFrame,
        *,
        mode: str = "append",
    ) -> FeatureParityReport:
        """Validate parity expectations and update the online store."""

        if mode not in {"append", "overwrite"}:
            raise ValueError("mode must be either 'append' or 'overwrite'")

        offline_frame = self._prepare_frame(frame, spec)
        online_existing = self._prepare_frame(
            self._store.load(spec.feature_view), spec, require_columns=False
        )

        keys = list(spec.entity_columns) + [spec.timestamp_column]
        columns_added, columns_removed = self._diff_columns(
            offline_frame, online_existing, keys
        )

        if (
            not spec.allow_schema_evolution
            and not online_existing.empty
            and (columns_added or columns_removed)
        ):
            raise FeatureUpdateBlocked(
                "Schema change detected. Enable allow_schema_evolution to proceed."
            )

        clock_skew = self._compute_clock_skew(offline_frame, online_existing, spec)
        clock_skew_abs: pd.Timedelta | None = None
        if clock_skew is not None:
            clock_skew_abs = abs(clock_skew)
            if spec.max_clock_skew is not None and clock_skew_abs > spec.max_clock_skew:
                raise FeatureTimeSkewError(
                    "Clock skew exceeds configured tolerance for feature view "
                    f"{spec.feature_view!r}: {clock_skew_abs} > {spec.max_clock_skew}"
                )

        inserted_keys, removed_keys = self._diff_keys(
            offline_frame, online_existing, keys
        )

        value_columns = self._resolve_value_columns(
            offline_frame, online_existing, keys, spec
        )

        max_value_drift, updated_keys = self._compute_value_drift(
            offline_frame, online_existing, keys, value_columns, spec
        )

        if mode == "append" and updated_keys:
            raise FeatureUpdateBlocked(
                "Append mode cannot modify existing feature rows; use overwrite instead."
            )

        if (
            spec.numeric_tolerance is not None
            and max_value_drift is not None
            and max_value_drift > spec.numeric_tolerance
        ):
            raise FeatureUpdateBlocked(
                "Observed feature drift exceeds configured tolerance: "
                f"{max_value_drift} > {spec.numeric_tolerance}"
            )

        if mode == "append":
            write_frame = self._filter_to_keys(offline_frame, inserted_keys, keys)
            dropped_rows = 0
        else:
            write_frame = offline_frame
            dropped_rows = len(removed_keys)

        inserted_rows = write_frame.shape[0]
        updated_rows = len(updated_keys)

        integrity = self._store.sync(
            spec.feature_view, write_frame, mode=mode, validate=True
        )

        return FeatureParityReport(
            feature_view=spec.feature_view,
            integrity=integrity,
            inserted_rows=inserted_rows,
            updated_rows=updated_rows,
            dropped_rows=dropped_rows,
            max_value_drift=max_value_drift,
            clock_skew=clock_skew,
            clock_skew_abs=clock_skew_abs,
            columns_added=columns_added,
            columns_removed=columns_removed,
        )

    def _prepare_frame(
        self,
        frame: pd.DataFrame,
        spec: FeatureParitySpec,
        *,
        require_columns: bool = True,
    ) -> pd.DataFrame:
        expected_columns = set(spec.entity_columns) | {spec.timestamp_column}
        missing = expected_columns - set(frame.columns)
        if missing:
            if frame.empty and not require_columns:
                return frame.copy()
            missing_str = ", ".join(sorted(missing))
            raise KeyError(
                f"Frame for feature view {spec.feature_view!r} is missing required "
                f"columns: {missing_str}"
            )

        prepared = frame.copy(deep=True)
        prepared[spec.timestamp_column] = pd.to_datetime(
            prepared[spec.timestamp_column], utc=True
        ).dt.tz_convert(UTC)

        if spec.timestamp_granularity is not None:
            prepared[spec.timestamp_column] = prepared[spec.timestamp_column].dt.floor(
                spec.timestamp_granularity
            )

        key_columns = list(spec.entity_columns) + [spec.timestamp_column]
        ordered = prepared.sort_values(by=key_columns, kind="mergesort")
        deduped = ordered.drop_duplicates(key_columns, keep="last")
        return deduped.reset_index(drop=True)

    def _diff_columns(
        self,
        offline_frame: pd.DataFrame,
        online_frame: pd.DataFrame,
        keys: Sequence[str],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        key_set = set(keys)
        offline_columns = set(offline_frame.columns) - key_set
        online_columns = set(online_frame.columns) - key_set
        added = tuple(sorted(offline_columns - online_columns))
        removed = tuple(sorted(online_columns - offline_columns))
        return added, removed

    def _compute_clock_skew(
        self,
        offline_frame: pd.DataFrame,
        online_frame: pd.DataFrame,
        spec: FeatureParitySpec,
    ) -> pd.Timedelta | None:
        if offline_frame.empty or online_frame.empty:
            return None

        offline_ts = offline_frame[spec.timestamp_column].max()
        online_ts = online_frame[spec.timestamp_column].max()
        if pd.isna(offline_ts) or pd.isna(online_ts):
            return None
        return pd.Timedelta(offline_ts - online_ts)

    def _diff_keys(
        self,
        offline_frame: pd.DataFrame,
        online_frame: pd.DataFrame,
        keys: Sequence[str],
    ) -> tuple[set[tuple[object, ...]], set[tuple[object, ...]]]:
        offline_keys = set(self._iter_key_tuples(offline_frame, keys))
        online_keys = set(self._iter_key_tuples(online_frame, keys))
        inserted = offline_keys - online_keys
        removed = online_keys - offline_keys
        return inserted, removed

    def _resolve_value_columns(
        self,
        offline_frame: pd.DataFrame,
        online_frame: pd.DataFrame,
        keys: Sequence[str],
        spec: FeatureParitySpec,
    ) -> tuple[str, ...]:
        if spec.value_columns is not None:
            candidates = tuple(spec.value_columns)
        else:
            candidates = tuple(
                column for column in offline_frame.columns if column not in keys
            )
        online_columns = set(online_frame.columns)
        resolved = tuple(
            column
            for column in candidates
            if column in offline_frame.columns and column in online_columns
        )
        return resolved

    def _compute_value_drift(
        self,
        offline_frame: pd.DataFrame,
        online_frame: pd.DataFrame,
        keys: Sequence[str],
        value_columns: Sequence[str],
        spec: FeatureParitySpec,
    ) -> tuple[float | None, set[tuple[object, ...]]]:
        if not value_columns or offline_frame.empty or online_frame.empty:
            return None, set()

        merged = offline_frame.merge(
            online_frame,
            on=list(keys),
            how="inner",
            suffixes=("_offline", "_online"),
        )
        if merged.empty:
            return None, set()

        tolerance = (
            float("inf") if spec.numeric_tolerance is None else spec.numeric_tolerance
        )

        max_drift: float | None = None
        updated: set[tuple[object, ...]] = set()

        for column in value_columns:
            offline_col = f"{column}_offline"
            online_col = f"{column}_online"
            if offline_col not in merged.columns or online_col not in merged.columns:
                continue

            offline_series = merged[offline_col]
            online_series = merged[online_col]

            if pd_types.is_numeric_dtype(offline_series) and pd_types.is_numeric_dtype(
                online_series
            ):
                diff_series = (offline_series - online_series).abs().fillna(0)
                candidate = diff_series.max(skipna=True)
                if candidate is not None and not pd.isna(candidate):
                    diff_value = float(candidate)
                    if max_drift is None:
                        max_drift = diff_value
                    else:
                        max_drift = max(max_drift, diff_value)
                exceed_mask = diff_series > tolerance
            else:
                left = offline_series.astype("string").fillna("<NA>")
                right = online_series.astype("string").fillna("<NA>")
                mismatch = left != right
                if mismatch.any():
                    if max_drift is None:
                        max_drift = 1.0
                    else:
                        max_drift = max(max_drift, 1.0)
                exceed_mask = mismatch

            if exceed_mask.any():
                updated.update(
                    merged.loc[exceed_mask, list(keys)].itertuples(
                        index=False, name=None
                    )
                )

        return max_drift, updated

    def _filter_to_keys(
        self,
        frame: pd.DataFrame,
        keys_to_keep: Iterable[tuple[object, ...]],
        keys: Sequence[str],
    ) -> pd.DataFrame:
        if not keys_to_keep:
            return frame.iloc[0:0]
        key_set = set(keys_to_keep)
        mask = frame[list(keys)].apply(tuple, axis=1).isin(key_set)
        return frame.loc[mask].reset_index(drop=True)

    def _iter_key_tuples(
        self, frame: pd.DataFrame, keys: Sequence[str]
    ) -> Iterable[tuple[object, ...]]:
        if frame.empty:
            return []
        return frame[list(keys)].itertuples(index=False, name=None)


__all__ = [
    "FeatureParityCoordinator",
    "FeatureParityError",
    "FeatureParityReport",
    "FeatureParitySpec",
    "FeatureTimeSkewError",
    "FeatureUpdateBlocked",
]
