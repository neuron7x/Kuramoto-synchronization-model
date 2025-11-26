"""Robust market data normalisation pipelines for ticks and OHLCV bars.

The helpers in this module build upon the existing resampling utilities and
data models to offer an end-to-end normalisation step that can be applied
before feature engineering or model training.  The core goals are:

* **Structural unification** – irrespective of whether the source payload is
  tick level or already aggregated into OHLCV bars, the resulting frame exposes
  the canonical ``open``, ``high``, ``low``, ``close`` and ``volume`` columns.
* **Temporal alignment** – timestamps are coerced to UTC, sorted and reindexed
  onto a deterministic calendar which guarantees evenly spaced intervals.
* **Gap remediation** – missing observations are surfaced explicitly and can be
  forward filled, interpolated or left as ``NaN`` while volume defaults to
  ``0`` for newly created rows.
* **Metadata aggregation** – a compact summary describing the processed batch
  (time span, interval, counts, quality signals) is produced alongside the
  frame so downstream components can trace lineage and monitor data quality.

The implementation is intentionally pandas-centric to maximise compatibility
with the rest of the analytics toolchain while keeping the API ergonomic and
type-friendly for 2025-era Python (3.11+).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, Mapping, MutableMapping

import numpy as np
import pandas as pd

from core.data.resampling import resample_l1_to_ohlcv, resample_ticks_to_l1

NormalisationKind = Literal["tick", "ohlcv"]
FillMethod = Literal["ffill", "bfill", "interpolate", "none"]


@dataclass(frozen=True, slots=True)
class MarketNormalizationConfig:
    """Declarative configuration for ``normalize_market_data``.

    Attributes
    ----------
    kind:
        Indicates the shape of the raw payload.  ``"tick"`` inputs are
        resampled into OHLCV bars.  ``"ohlcv"`` inputs are assumed to already
        contain OHLCV columns but may require gap filling or structural fixes.
    frequency:
        Target calendar frequency (e.g. ``"1min"``).  When omitted the
        frequency is inferred from the data (via :func:`pandas.infer_freq`).
    timestamp_col:
        Column containing timestamps when the frame is not indexed by a
        ``DatetimeIndex``.
    price_col:
        Column holding the last traded price in tick feeds.  Ignored for OHLCV
        payloads.
    volume_col:
        Column holding the traded size for tick feeds.  Ignored for OHLCV
        payloads.
    fill_method:
        Strategy applied to remediation rows created during reindexing.
    metadata_fields:
        Column names carrying metadata that should be aggregated into the
        resulting :class:`MarketNormalizationMetadata`.
    deduplicate:
        Drop duplicate timestamps before any further processing.
    expect_utc:
        When ``True`` timestamps are converted to UTC.  ``False`` disables the
        conversion guard (while still sorting the index).
    allow_empty:
        Whether empty inputs are considered valid.  When ``False`` a ``ValueError``
        is raised for empty frames.
    """

    kind: NormalisationKind = "ohlcv"
    frequency: str | None = None
    timestamp_col: str = "timestamp"
    price_col: str = "price"
    volume_col: str = "volume"
    fill_method: FillMethod = "ffill"
    metadata_fields: tuple[str, ...] = ("symbol", "venue", "instrument_type")
    deduplicate: bool = True
    expect_utc: bool = True
    allow_empty: bool = False


@dataclass(frozen=True, slots=True)
class MarketNormalizationMetadata:
    """Summary describing a normalised market dataset."""

    kind: NormalisationKind
    frequency: str | None
    rows: int
    start: pd.Timestamp | None
    end: pd.Timestamp | None
    duplicates_dropped: int
    missing_intervals: int
    filled_intervals: int
    inferred_frequency: bool
    metadata: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class MarketNormalizationResult:
    """Container returned by :func:`normalize_market_data`."""

    frame: pd.DataFrame
    metadata: MarketNormalizationMetadata


def normalize_market_data(
    frame: pd.DataFrame, *, config: MarketNormalizationConfig
) -> MarketNormalizationResult:
    """Return a normalised OHLCV frame and metadata for *frame*.

    Parameters
    ----------
    frame:
        Source data.  The frame may represent ticks or OHLCV bars.  A copy is
        created as part of the normalisation process; the input is never
        mutated in-place.
    config:
        Declarative configuration controlling the behaviour of the pipeline.

    Returns
    -------
    MarketNormalizationResult
        Structured frame with canonical OHLCV columns and accompanying metadata
        describing the transformation.
    """

    if not isinstance(frame, pd.DataFrame):  # pragma: no cover - defensive guard
        raise TypeError("frame must be a pandas.DataFrame")

    if frame.empty:
        if config.allow_empty:
            metadata = MarketNormalizationMetadata(
                kind=config.kind,
                frequency=config.frequency,
                rows=0,
                start=None,
                end=None,
                duplicates_dropped=0,
                missing_intervals=0,
                filled_intervals=0,
                inferred_frequency=False,
                metadata=_extract_metadata({}, config.metadata_fields),
            )
            return MarketNormalizationResult(frame=frame.copy(), metadata=metadata)
        raise ValueError("Input frame is empty")

    prepared = _prepare_frame(frame, config)
    if config.deduplicate:
        prepared, duplicates_dropped = _drop_duplicates(prepared)
    else:
        duplicates_dropped = 0

    resolved_freq, inferred = _resolve_frequency(prepared.index, config.frequency)

    if config.kind == "tick":
        ohlcv_raw = _from_ticks(prepared, config, resolved_freq)
        if ohlcv_raw.empty:
            expected_index = pd.DatetimeIndex([], tz=prepared.index.tz)
            missing = 0
            reindexed = ohlcv_raw
        else:
            start = ohlcv_raw.index[0]
            end = ohlcv_raw.index[-1]
            expected_index = pd.date_range(
                start=start,
                end=end,
                freq=resolved_freq,
                tz=start.tz,
            )
            price_columns = [
                column
                for column in ("open", "high", "low", "close")
                if column in ohlcv_raw
            ]
            if price_columns:
                present_mask = ~ohlcv_raw[price_columns].isna().all(axis=1)
                observed = ohlcv_raw.index[present_mask]
            else:
                observed = ohlcv_raw.index
            missing = int(expected_index.difference(observed).shape[0])
            reindexed = ohlcv_raw.reindex(expected_index)
        filled = _fill_gaps(reindexed, config.fill_method)
        ohlcv = _ensure_ohlcv_columns(filled)
    else:
        reindexed, missing = _reindex(prepared, resolved_freq)
        filled = _fill_gaps(reindexed, config.fill_method)
        ohlcv = _ensure_ohlcv_columns(filled)

    metadata = MarketNormalizationMetadata(
        kind=config.kind,
        frequency=resolved_freq,
        rows=int(ohlcv.shape[0]),
        start=ohlcv.index.min() if not ohlcv.empty else None,
        end=ohlcv.index.max() if not ohlcv.empty else None,
        duplicates_dropped=duplicates_dropped,
        missing_intervals=missing,
        filled_intervals=missing if config.fill_method != "none" else 0,
        inferred_frequency=inferred,
        metadata=_extract_metadata(frame, config.metadata_fields),
    )
    return MarketNormalizationResult(frame=ohlcv, metadata=metadata)


def _prepare_frame(
    frame: pd.DataFrame, config: MarketNormalizationConfig
) -> pd.DataFrame:
    prepared = frame.copy()
    if not isinstance(prepared.index, pd.DatetimeIndex):
        if config.timestamp_col not in prepared.columns:
            raise KeyError(
                f"Frame must have a DatetimeIndex or '{config.timestamp_col}' column"
            )
        prepared[config.timestamp_col] = pd.to_datetime(
            prepared[config.timestamp_col], utc=config.expect_utc
        )
        prepared.set_index(config.timestamp_col, inplace=True)
    else:
        prepared.index = pd.to_datetime(prepared.index, utc=config.expect_utc)

    if config.expect_utc:
        prepared.index = prepared.index.tz_convert("UTC")

    prepared.sort_index(inplace=True)
    prepared.index.name = "timestamp"
    return prepared


def _drop_duplicates(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    before = frame.shape[0]
    deduplicated = frame[~frame.index.duplicated(keep="last")]
    dropped = before - deduplicated.shape[0]
    return deduplicated, dropped


def _resolve_frequency(
    index: pd.DatetimeIndex, explicit: str | None
) -> tuple[str, bool]:
    if explicit is not None:
        return explicit, False
    inferred = pd.infer_freq(index)
    if inferred is None:
        raise ValueError(
            "Unable to infer frequency from index. Provide `frequency` explicitly."
        )
    return inferred, True


def _reindex(frame: pd.DataFrame, freq: str) -> tuple[pd.DataFrame, int]:
    start = frame.index[0]
    end = frame.index[-1]
    expected_index = pd.date_range(start=start, end=end, freq=freq, tz=start.tz)
    missing = int(expected_index.difference(frame.index).shape[0])
    return frame.reindex(expected_index), missing


def _fill_gaps(frame: pd.DataFrame, method: FillMethod) -> pd.DataFrame:
    if method == "none":
        return frame

    filled = frame.copy()
    price_cols = [
        col for col in ("open", "high", "low", "close", "price") if col in filled
    ]
    volume_cols = [col for col in ("volume",) if col in filled]

    if method in {"ffill", "bfill"}:
        filled[price_cols] = getattr(filled[price_cols], method)()
    elif method == "interpolate":
        filled[price_cols] = filled[price_cols].interpolate(method="time")
    else:  # pragma: no cover - defensive branch
        raise ValueError(f"Unknown fill method: {method}")

    for column in volume_cols:
        filled[column] = filled[column].fillna(0.0)
    return filled


def _from_ticks(
    frame: pd.DataFrame, config: MarketNormalizationConfig, freq: str
) -> pd.DataFrame:
    required = {config.price_col}
    missing = required - set(frame.columns)
    if missing:
        raise KeyError(f"Tick frame is missing required columns: {sorted(missing)}")

    working = frame[[config.price_col]].rename(columns={config.price_col: "price"})
    if config.volume_col in frame.columns:
        working["size"] = frame[config.volume_col]
    else:
        working["size"] = 0.0

    l1 = resample_ticks_to_l1(
        working[["price", "size"]], freq=freq, price_col="price", size_col="size"
    )

    counts = frame.resample(freq).size()
    counts_index = pd.DatetimeIndex(counts.index)
    l1_index = pd.DatetimeIndex(l1.index)

    if counts_index.tz is None and l1_index.tz is not None:
        counts.index = counts_index.tz_localize(l1_index.tz)
    elif (
        counts_index.tz is not None
        and l1_index.tz is not None
        and counts_index.tz != l1_index.tz
    ):
        counts.index = counts_index.tz_convert(l1_index.tz)
    empty_bins = counts[counts == 0].index
    if not empty_bins.empty:
        l1.loc[empty_bins, "mid_price"] = np.nan
        l1.loc[empty_bins, "last_size"] = 0.0

    ohlcv = resample_l1_to_ohlcv(
        l1, freq=freq, price_col="mid_price", size_col="last_size"
    )

    if config.volume_col in frame.columns:
        volume = (
            frame[config.volume_col]
            .resample(freq)
            .sum(min_count=1)
            .reindex(ohlcv.index)
            .fillna(0.0)
        )
        ohlcv["volume"] = volume
    else:
        ohlcv["volume"] = 0.0

    return _ensure_ohlcv_columns(ohlcv)


def _ensure_ohlcv_columns(frame: pd.DataFrame) -> pd.DataFrame:
    expected_columns = ["open", "high", "low", "close", "volume"]
    missing_columns = [
        column for column in expected_columns if column not in frame.columns
    ]
    aligned = frame.copy()
    for column in missing_columns:
        aligned[column] = 0.0 if column == "volume" else np.nan
    aligned = aligned[expected_columns].copy()
    if "volume" in missing_columns:
        aligned["volume"] = aligned["volume"].fillna(0.0)
    aligned.index = pd.DatetimeIndex(aligned.index).tz_convert("UTC")
    return aligned


def _extract_metadata(
    source: Mapping[str, object] | pd.DataFrame, fields: Iterable[str]
) -> Mapping[str, object]:
    if isinstance(source, pd.DataFrame):
        payload: MutableMapping[str, object] = {}
        for field in fields:
            if field in source.columns:
                value = source[field].dropna()
                payload[field] = value.iloc[0] if not value.empty else None
            else:
                payload[field] = None
        return payload
    return {field: source.get(field) for field in fields}


__all__ = [
    "FillMethod",
    "MarketNormalizationConfig",
    "MarketNormalizationMetadata",
    "MarketNormalizationResult",
    "NormalisationKind",
    "normalize_market_data",
]
