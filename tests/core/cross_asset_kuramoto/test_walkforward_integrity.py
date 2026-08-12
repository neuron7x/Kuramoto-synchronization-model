"""T5: walk-forward fold definitions match INPUT_CONTRACT; each OOS window
contains no bar from its own IS window."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
LOCK_PATH = REPO_ROOT / "results" / "cross_asset_kuramoto" / "PARAMETER_LOCK.json"


def _lock() -> dict:
    return json.loads(LOCK_PATH.read_text())


def test_five_splits_exist() -> None:
    lock = _lock()
    splits = lock["walk_forward_splits_expanding_window"]
    assert len(splits) == 5


def test_expanding_window_ordering() -> None:
    lock = _lock()
    splits = lock["walk_forward_splits_expanding_window"]
    prev_train_end = None
    for s in splits:
        train_start = pd.Timestamp(s["train_start"])
        train_end = pd.Timestamp(s["train_end"])
        test_start = pd.Timestamp(s["test_start"])
        test_end = pd.Timestamp(s["test_end"])
        # Basic ordering
        assert train_start < train_end
        assert (
            train_end == test_start
        ), f"split {s['split']}: train_end {train_end} != test_start {test_start}"
        assert test_start < test_end
        # Expanding-window monotonicity of train_end
        if prev_train_end is not None:
            assert train_end > prev_train_end
        prev_train_end = train_end


def test_train_starts_are_identical() -> None:
    """Expanding-window ⇒ every split shares the same train_start."""
    lock = _lock()
    splits = lock["walk_forward_splits_expanding_window"]
    starts = {s["train_start"] for s in splits}
    assert starts == {"2017-08-17"}


def test_no_is_oos_overlap() -> None:
    lock = _lock()
    splits = lock["walk_forward_splits_expanding_window"]
    for s in splits:
        train_end = pd.Timestamp(s["train_end"])
        test_start = pd.Timestamp(s["test_start"])
        assert train_end <= test_start
