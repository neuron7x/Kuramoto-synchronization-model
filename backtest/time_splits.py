"""Utility classes for time-aware cross-validation with leakage control.

This module implements walk-forward validation and purged k-fold cross-validation
strategies tailored for financial time series. The implementations follow the
recommendations popularised by Marcos López de Prado in "Advances in Financial
Machine Learning" and guarantee that no information from the future leaks into
training folds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

_CANONICAL_FREQUENCY_UNITS = {
    "H": "h",
    "HR": "h",
    "HRS": "h",
    "HOUR": "h",
    "HOURS": "h",
    "T": "min",
    "MIN": "min",
    "MINS": "min",
    "MINUTE": "min",
    "MINUTES": "min",
    "S": "s",
    "SEC": "s",
    "SECS": "s",
    "SECOND": "s",
    "SECONDS": "s",
    "L": "ms",
    "MS": "ms",
    "MILLISECOND": "ms",
    "MILLISECONDS": "ms",
    "U": "us",
    "US": "us",
    "USEC": "us",
    "MICROSECOND": "us",
    "MICROSECONDS": "us",
    "N": "ns",
    "NS": "ns",
    "NSEC": "ns",
    "NANOSECOND": "ns",
    "NANOSECONDS": "ns",
}

_AMBIGUOUS_FREQUENCY_UNITS = {"M", "Y"}

_STRING_UNIT_PATTERN = re.compile(r"(?<=\d)([A-Za-zµμ]+)")


def _normalise_frequency_unit(freq: str) -> str:
    """Return a canonical unit string accepted by :func:`pandas.to_timedelta`."""

    cleaned = freq.strip()
    if not cleaned:
        raise ValueError("Frequency unit must be a non-empty string.")
    ascii_unit = cleaned.replace("μ", "u").replace("µ", "u")
    upper = ascii_unit.upper()
    if upper in _AMBIGUOUS_FREQUENCY_UNITS:
        raise ValueError(
            "Ambiguous frequency unit '{unit}' is not supported; specify an explicit "
            "duration such as 'min' or 'hour'.".format(unit=cleaned)
        )
    if upper in _CANONICAL_FREQUENCY_UNITS:
        return _CANONICAL_FREQUENCY_UNITS[upper]
    if ascii_unit.isupper():
        return ascii_unit.lower()
    return ascii_unit


def _normalise_timedelta_string(value: str) -> str:
    """Normalise deprecated unit aliases embedded within timedelta strings."""

    def _replace(match: re.Match[str]) -> str:
        unit = match.group(0)
        return _normalise_frequency_unit(unit)

    return _STRING_UNIT_PATTERN.sub(_replace, value.replace("μ", "u").replace("µ", "u"))


def _to_timedelta(
    value: Optional[pd.Timedelta | str | int | float], *, freq: Optional[str] = None
) -> Optional[pd.Timedelta]:
    """Convert ``value`` to :class:`pandas.Timedelta` when possible.

    Parameters
    ----------
    value:
        A timedelta-like representation. The value can be ``None`` (no limit),
        a :class:`pandas.Timedelta`, a string that can be parsed by
        :func:`pandas.to_timedelta`, or a numeric value which is interpreted as
        a number of periods expressed in ``freq``.
    freq:
        Optional frequency used when ``value`` is numeric.
    """

    if value is None:
        return None
    if isinstance(value, pd.Timedelta):
        return value
    if isinstance(value, str):
        normalised = _normalise_timedelta_string(value)
        return pd.to_timedelta(normalised)
    if isinstance(value, (int, float)):
        if freq is None:
            raise ValueError(
                "A frequency must be provided when using a numeric window size."
            )
        unit = _normalise_frequency_unit(freq) if isinstance(freq, str) else freq
        return pd.to_timedelta(value, unit=unit)
    raise TypeError(f"Unsupported timedelta specification: {value!r}")


@dataclass(slots=True)
class _BaseTimeSplit:
    time_col: Optional[str] = None
    label_end_col: Optional[str] = None
    embargo_pct: float = 0.0

    def _prepare_frame(self, data: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(data, pd.DataFrame):
            raise TypeError("`data` must be a pandas DataFrame.")
        frame = data.copy()
        if self.time_col is None:
            if not isinstance(frame.index, pd.DatetimeIndex):
                raise ValueError(
                    "A datetime index is required when `time_col` is not provided."
                )
            frame = frame.reset_index().rename(columns={"index": "__time__"})
            time_col = "__time__"
        else:
            if self.time_col not in frame.columns:
                raise KeyError(f"Column `{self.time_col}` not found in data frame.")
            time_col = self.time_col
        frame = frame.sort_values(time_col)
        frame.reset_index(inplace=True)
        frame.rename(columns={"index": "__orig_index__"}, inplace=True)
        frame[time_col] = pd.to_datetime(frame[time_col], utc=True, errors="coerce")
        if frame[time_col].isna().any():
            raise ValueError("All time values must be convertible to datetime.")
        self._resolved_time_col = time_col
        if self.label_end_col:
            if self.label_end_col not in frame.columns:
                raise KeyError(
                    f"Column `{self.label_end_col}` not found in data frame."
                )
            frame[self.label_end_col] = pd.to_datetime(
                frame[self.label_end_col], utc=True, errors="coerce"
            )
            if frame[self.label_end_col].isna().any():
                raise ValueError(
                    "All label end values must be convertible to datetime."
                )
        return frame

    def _purge_overlaps(
        self, frame: pd.DataFrame, train_mask: np.ndarray, test_mask: np.ndarray
    ) -> np.ndarray:
        if not self.label_end_col:
            return train_mask
        time_col = self._resolved_time_col
        test_start = frame.loc[test_mask, time_col].min()
        test_end = frame.loc[test_mask, self.label_end_col].max()
        if pd.isna(test_end):
            test_end = frame.loc[test_mask, time_col].max()
        overlap_mask = (frame[self.label_end_col] >= test_start) & (
            frame[time_col] <= test_end
        )
        return train_mask & ~overlap_mask.to_numpy()

    def _apply_embargo(
        self, frame: pd.DataFrame, train_mask: np.ndarray, test_mask: np.ndarray
    ) -> np.ndarray:
        if self.embargo_pct <= 0:
            return train_mask
        embargo_count = int(np.ceil(len(frame) * self.embargo_pct))
        if embargo_count == 0:
            return train_mask
        embargo = np.zeros_like(train_mask)
        test_positions = np.flatnonzero(test_mask)
        if test_positions.size == 0:
            return train_mask
        embargo_start = test_positions.max() + 1
        embargo_end = min(embargo_start + embargo_count, len(frame))
        embargo[embargo_start:embargo_end] = True
        return train_mask & ~embargo


class WalkForwardSplitter(_BaseTimeSplit):
    """Generate walk-forward train/test splits without leakage.

    Parameters
    ----------
    train_window:
        Size of the training window. Accepts any value recognised by
        :func:`pandas.to_timedelta` or a numeric value when paired with ``freq``.
        ``None`` means the training window grows with every split (expanding
        window).
    test_window:
        Size of the test window.
    step:
        Forward step applied after each split. By default, it equals the test
        window to produce non-overlapping test segments.
    freq:
        Optional unit used when ``train_window`` or ``test_window`` are numeric.
    embargo_pct:
        Fraction of observations blocked after the test window (embargo).
    label_end_col:
        Optional column containing the end time of a label/event, used for
        purging overlapping observations from the training set.
    """

    def __init__(
        self,
        train_window: Optional[pd.Timedelta | str | int | float],
        test_window: pd.Timedelta | str | int | float,
        *,
        step: Optional[pd.Timedelta | str | int | float] = None,
        freq: Optional[str] = None,
        time_col: Optional[str] = None,
        label_end_col: Optional[str] = None,
        embargo_pct: float = 0.0,
    ) -> None:
        super().__init__(
            time_col=time_col, label_end_col=label_end_col, embargo_pct=embargo_pct
        )
        self.train_window = _to_timedelta(train_window, freq=freq)
        self.test_window = _to_timedelta(test_window, freq=freq)
        if self.test_window is None:
            raise ValueError("`test_window` must be provided.")
        self.step = (
            _to_timedelta(step, freq=freq) if step is not None else self.test_window
        )

    def split(self, data: pd.DataFrame) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
        frame = self._prepare_frame(data)
        time_col = self._resolved_time_col
        min_time = frame[time_col].min()
        max_time = frame[time_col].max()
        test_start = (
            min_time if self.train_window is None else min_time + self.train_window
        )
        while test_start + self.test_window <= max_time:
            train_start = (
                min_time
                if self.train_window is None
                else test_start - self.train_window
            )
            train_mask = (frame[time_col] >= train_start) & (
                frame[time_col] < test_start
            )
            test_end = test_start + self.test_window
            test_mask = (frame[time_col] >= test_start) & (frame[time_col] < test_end)
            if not test_mask.any():
                test_start += self.step
                continue
            if not train_mask.any():
                test_start += self.step
                continue
            train_mask = train_mask.to_numpy()
            test_mask = test_mask.to_numpy()
            train_mask = self._purge_overlaps(frame, train_mask, test_mask)
            train_mask = self._apply_embargo(frame, train_mask, test_mask)
            train_idx = frame.loc[train_mask, "__orig_index__"].to_numpy()
            test_idx = frame.loc[test_mask, "__orig_index__"].to_numpy()
            yield train_idx, test_idx
            test_start += self.step


class PurgedKFoldTimeSeriesSplit(_BaseTimeSplit):
    """K-fold cross-validation for time series with purging and embargo."""

    def __init__(
        self,
        n_splits: int = 5,
        *,
        time_col: Optional[str] = None,
        label_end_col: Optional[str] = None,
        embargo_pct: float = 0.0,
    ) -> None:
        if n_splits < 2:
            raise ValueError("`n_splits` must be at least 2.")
        super().__init__(
            time_col=time_col, label_end_col=label_end_col, embargo_pct=embargo_pct
        )
        self.n_splits = n_splits

    def split(self, data: pd.DataFrame) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
        frame = self._prepare_frame(data)
        n_samples = len(frame)
        fold_sizes = np.full(self.n_splits, n_samples // self.n_splits, dtype=int)
        fold_sizes[: n_samples % self.n_splits] += 1
        current = 0
        for fold_size in fold_sizes:
            start, stop = current, current + fold_size
            test_mask = np.zeros(n_samples, dtype=bool)
            test_mask[start:stop] = True
            train_mask = ~test_mask
            train_mask = self._purge_overlaps(frame, train_mask, test_mask)
            train_mask = self._apply_embargo(frame, train_mask, test_mask)
            train_idx = frame.loc[train_mask, "__orig_index__"].to_numpy()
            test_idx = frame.loc[test_mask, "__orig_index__"].to_numpy()
            yield train_idx, test_idx
            current = stop

    def get_n_splits(self, *_: Sequence) -> int:
        """Return the number of splits."""

        return self.n_splits
