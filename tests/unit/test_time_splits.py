import warnings

import numpy as np
import pandas as pd
import pytest

from backtest.time_splits import (
    PurgedKFoldTimeSeriesSplit,
    WalkForwardSplitter,
    _to_timedelta,
)


def _sample_frame():
    dates = pd.date_range("2020-01-01", periods=12, freq="MS", tz="UTC")
    frame = pd.DataFrame(
        {
            "timestamp": dates,
            "label_end": dates + pd.Timedelta(days=15),
            "value": np.arange(len(dates)),
        }
    )
    return frame


def test_walk_forward_split_respects_windows():
    frame = _sample_frame()
    splitter = WalkForwardSplitter(
        train_window="180D",
        test_window="60D",
        step="60D",
        time_col="timestamp",
        label_end_col="label_end",
        embargo_pct=0.1,
    )
    splits = list(splitter.split(frame))
    assert splits, "Expected at least one split"
    for train_idx, test_idx in splits:
        assert len(train_idx) > 0
        assert len(test_idx) > 0
        train_times = frame.loc[train_idx, "timestamp"]
        test_times = frame.loc[test_idx, "timestamp"]
        assert train_times.max() < test_times.min()
        # embargo ensures a buffer
        max_train_pos = frame.index.get_indexer_for(train_idx).max()
        min_test_pos = frame.index.get_indexer_for(test_idx).min()
        assert min_test_pos - max_train_pos >= 1


def test_purged_walk_forward_removes_overlaps():
    frame = _sample_frame()
    # Introduce overlap: extend the label end of an early observation into the future
    frame.loc[2, "label_end"] = frame.loc[5, "timestamp"]
    splitter = WalkForwardSplitter(
        train_window="180D",
        test_window="60D",
        step="60D",
        time_col="timestamp",
        label_end_col="label_end",
        embargo_pct=0.0,
    )
    for train_idx, test_idx in splitter.split(frame):
        test_end = frame.loc[test_idx, "label_end"].max()
        train_overlaps = (
            frame.loc[train_idx, "label_end"] >= frame.loc[test_idx, "timestamp"].min()
        )
        assert not train_overlaps.any()
        assert frame.loc[train_idx, "timestamp"].max() < test_end


def test_walk_forward_expanding_window():
    frame = _sample_frame()
    splitter = WalkForwardSplitter(
        train_window=None,
        test_window="60D",
        step="30D",
        time_col="timestamp",
    )
    train_lengths = []
    for train_idx, _ in splitter.split(frame):
        train_lengths.append(len(train_idx))
    assert train_lengths == sorted(train_lengths)
    assert train_lengths[0] < train_lengths[-1]


def test_purged_kfold_applies_embargo():
    frame = _sample_frame()
    splitter = PurgedKFoldTimeSeriesSplit(
        n_splits=4,
        time_col="timestamp",
        label_end_col="label_end",
        embargo_pct=0.2,
    )
    frame = frame.reset_index(drop=True)
    n = len(frame)
    embargo_count = int(np.ceil(n * 0.2))
    for train_idx, test_idx in splitter.split(frame):
        assert len(np.intersect1d(train_idx, test_idx)) == 0
        last_test = max(test_idx)
        embargo_range = range(last_test + 1, min(last_test + 1 + embargo_count, n))
        assert not any(i in train_idx for i in embargo_range)


@pytest.mark.parametrize("n_splits", [1, 0])
def test_purged_kfold_requires_at_least_two_splits(n_splits):
    with pytest.raises(ValueError):
        PurgedKFoldTimeSeriesSplit(n_splits=n_splits)


def test_purged_kfold_with_label_overlap_purges_training_frame():
    frame = _sample_frame()
    # Ensure every label spans into the future to trigger purging logic.
    frame["label_end"] = frame["timestamp"] + pd.Timedelta(days=20)
    # Create an extended label that would otherwise leak into the next fold.
    frame.loc[4, "label_end"] = frame.loc[7, "timestamp"] + pd.Timedelta(days=5)

    splitter = PurgedKFoldTimeSeriesSplit(
        n_splits=3,
        time_col="timestamp",
        label_end_col="label_end",
        embargo_pct=0.0,
    )

    for train_idx, test_idx in splitter.split(frame):
        assert len(train_idx) > 0
        assert len(test_idx) > 0
        test_start = frame.loc[test_idx, "timestamp"].min()
        test_end = frame.loc[test_idx, "label_end"].max()
        # Purging should remove any training observation whose label extends into the
        # beginning of the test fold, preventing look-ahead leakage.
        overlaps = (frame.loc[train_idx, "label_end"] >= test_start) & (
            frame.loc[train_idx, "timestamp"] <= test_end
        )
        assert not overlaps.any(), "Purging failed to remove overlapping labels"


def test_walk_forward_with_overlapping_tests_has_no_leakage():
    frame = _sample_frame()
    splitter = WalkForwardSplitter(
        train_window="180D",
        test_window="90D",
        step="30D",  # intentionally overlap successive test windows
        time_col="timestamp",
        label_end_col="label_end",
    )

    splits = list(splitter.split(frame))
    assert splits, "Expected walk-forward splits to be produced"

    for train_idx, test_idx in splits:
        assert len(train_idx) > 0
        assert len(test_idx) > 0
        train_last = frame.loc[train_idx, "timestamp"].max()
        test_start = frame.loc[test_idx, "timestamp"].min()
        assert (
            train_last < test_start
        ), "Training window must strictly precede the test window"


@pytest.mark.parametrize(
    ("unit", "expected"),
    [
        ("H", "h"),
        ("h", "h"),
        ("HR", "h"),
        ("T", "min"),
        ("t", "min"),
        ("MIN", "min"),
        ("S", "s"),
        ("L", "ms"),
        ("l", "ms"),
        ("U", "us"),
        ("u", "us"),
        ("µs", "us"),
        ("N", "ns"),
        ("n", "ns"),
    ],
)
def test_to_timedelta_normalises_frequency_aliases(unit, expected):
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        delta = _to_timedelta(5, freq=unit)
    assert delta == pd.to_timedelta(5, unit=expected)


def test_to_timedelta_rejects_ambiguous_month_alias():
    with pytest.raises(ValueError):
        _to_timedelta(1, freq="M")


@pytest.mark.parametrize(
    "value",
    [
        "12H",
        "1H30T",
        "15min",
        "2h",
        "5µs",
        "10U",
    ],
)
def test_string_timedelta_inputs_do_not_emit_future_warnings(value):
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        result = _to_timedelta(value)
    assert isinstance(result, pd.Timedelta)
