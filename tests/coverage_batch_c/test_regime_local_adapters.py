# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Behavioral coverage for analytics.regime.src.adapters.local."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from analytics.regime.src.adapters.local import (
    FileRegimePersistence,
    InMemoryRegimePersistence,
    LocalFeatureExtractor,
    LocalRegimeClassifier,
    LocalSum,
    LocalTransitionModel,
)


def _returns(rows: int, cols: int, seed: int = 0) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    data = rng.normal(scale=0.01, size=(rows, cols))
    return pd.DataFrame(
        data,
        columns=[f"asset_{i}" for i in range(cols)],
        index=pd.RangeIndex(rows),
    )


# --------------------------------------------------------------------------
# LocalSum
# --------------------------------------------------------------------------
def test_local_sum() -> None:
    assert LocalSum().sum(2, 3) == 5
    assert LocalSum().sum(-4, 4) == 0


# --------------------------------------------------------------------------
# LocalRegimeClassifier
# --------------------------------------------------------------------------
def test_classifier_fit_predict_full_pipeline() -> None:
    returns = _returns(60, 3, seed=1)
    clf = LocalRegimeClassifier(random_state=7)
    clf.fit(returns, n_regimes=3)

    assert clf._fitted is True
    assert clf._centroids is not None
    assert clf._centroids.shape == (3, 2)

    labels = clf.predict(returns)
    assert len(labels) == len(returns)
    assert set(labels).issubset({0, 1, 2})

    proba = clf.predict_proba(returns)
    assert list(proba.columns) == ["regime_0", "regime_1", "regime_2"]
    # softmax rows sum to 1
    np.testing.assert_allclose(
        np.asarray(proba.sum(axis=1).to_numpy(), dtype=float), 1.0, rtol=1e-6
    )

    stats = clf.get_regime_statistics()
    assert set(stats.keys()) == {0, 1, 2}
    total = sum(s["count"] for s in stats.values())
    assert total == len(returns)


def test_classifier_insufficient_data_fit() -> None:
    # rows < n_regimes triggers the zero-centroid early return.
    returns = _returns(2, 2, seed=2)
    clf = LocalRegimeClassifier()
    clf.fit(returns, n_regimes=5)
    assert clf._fitted is True
    assert clf._centroids is not None
    assert np.all(clf._centroids == 0.0)


def test_classifier_single_row_feature_window() -> None:
    # 1 row forces the window<2 -> window=len(returns) branch in
    # _extract_features, then the insufficient-data early return.
    returns = _returns(1, 2, seed=99)
    clf = LocalRegimeClassifier()
    clf.fit(returns, n_regimes=2)
    assert clf._fitted is True
    assert clf._centroids is not None
    assert np.all(clf._centroids == 0.0)


def test_classifier_predict_before_fit_returns_zeros() -> None:
    returns = _returns(10, 2, seed=3)
    clf = LocalRegimeClassifier()
    labels = clf.predict(returns)
    assert labels == [0] * len(returns)


def test_classifier_predict_proba_before_fit_is_uniform() -> None:
    returns = _returns(6, 2, seed=4)
    clf = LocalRegimeClassifier()
    proba = clf.predict_proba(returns)
    assert proba.shape == (6, 3)
    np.testing.assert_allclose(proba.values, 1.0 / 3.0)


def test_classifier_empty_regime_statistics() -> None:
    # Identical rows collapse every point into one cluster -> the other
    # clusters are empty, exercising the count==0 stats branch.
    returns = pd.DataFrame(
        np.full((12, 2), 0.005),
        columns=["a", "b"],
        index=pd.RangeIndex(12),
    )
    clf = LocalRegimeClassifier(random_state=0)
    clf.fit(returns, n_regimes=3)
    stats = clf.get_regime_statistics()
    empty = [k for k, v in stats.items() if v["count"] == 0]
    assert empty, "expected at least one empty regime"
    for k in empty:
        assert stats[k] == {"mean": 0.0, "volatility": 0.0, "count": 0}
    populated = [k for k, v in stats.items() if v["count"] > 0]
    assert populated
    assert "duration_mean" in stats[populated[0]]


def test_predict_labels_without_centroids_returns_zeros() -> None:
    clf = LocalRegimeClassifier()
    feats = np.array([[0.1, 0.2], [0.3, 0.4]])
    out = clf._predict_labels(feats)
    assert out.tolist() == [0, 0]


def test_compute_mean_duration_static() -> None:
    # empty labels
    assert LocalRegimeClassifier._compute_mean_duration(np.array([], dtype=int), 0) == 0.0
    # regime absent -> no durations
    assert LocalRegimeClassifier._compute_mean_duration(np.array([1, 1, 2]), 0) == 0.0
    # interleaved runs: 0-runs of length 2 then 1
    labels = np.array([0, 0, 1, 0])
    assert LocalRegimeClassifier._compute_mean_duration(labels, 0) == 1.5


# --------------------------------------------------------------------------
# LocalFeatureExtractor
# --------------------------------------------------------------------------
def test_feature_extractor_full() -> None:
    returns = _returns(40, 3, seed=5)
    prices = (1.0 + returns).cumprod()
    ext = LocalFeatureExtractor(windows=(5, 10, 21))
    feats = ext.extract(prices, returns)

    names = ext.get_feature_names()
    assert "momentum_5" in names
    assert "volatility_5" in names
    assert "vol_ratio_5" in names  # window != max -> ratio present
    assert "vol_ratio_21" not in names  # max window -> no ratio
    assert "cross_correlation" in names  # >=2 assets

    for name in names:
        assert name in feats.columns

    imp = ext.get_feature_importance()
    assert set(imp.keys()) == set(names)
    np.testing.assert_allclose(sum(imp.values()), 1.0, rtol=1e-9)


def test_feature_extractor_momentum_only() -> None:
    # single asset avoids the cross_correlation feature.
    returns = _returns(30, 1, seed=6)
    prices = (1.0 + returns).cumprod()
    ext = LocalFeatureExtractor(
        windows=(5,), include_momentum=True, include_volatility=False
    )
    ext.extract(prices, returns)
    names = ext.get_feature_names()
    assert names == ["momentum_5"]


def test_feature_extractor_volatility_only_single_asset() -> None:
    returns = _returns(30, 1, seed=7)
    prices = (1.0 + returns).cumprod()
    ext = LocalFeatureExtractor(
        windows=(5, 10), include_momentum=False, include_volatility=True
    )
    ext.extract(prices, returns)
    names = ext.get_feature_names()
    assert "volatility_5" in names
    assert "vol_ratio_5" in names
    assert "cross_correlation" not in names  # single asset


def test_feature_extractor_window_too_large_yields_no_features() -> None:
    returns = _returns(3, 1, seed=8)
    prices = (1.0 + returns).cumprod()
    ext = LocalFeatureExtractor(windows=(5,))
    feats = ext.extract(prices, returns)
    assert ext.get_feature_names() == []
    assert ext.get_feature_importance() == {}
    assert feats.shape[1] == 0


# --------------------------------------------------------------------------
# LocalTransitionModel
# --------------------------------------------------------------------------
def test_transition_model_short_sequence_defaults() -> None:
    model = LocalTransitionModel()
    model.fit([0])  # len < 2 -> no-op
    assert model.get_transition_matrix().empty
    # matrix None -> uniform over zero regimes
    assert model.predict_next_regime(0) == {}
    # durations empty and matrix None -> default 1.0
    assert model.expected_duration(0) == 1.0


def test_transition_model_full() -> None:
    seq = [0, 1, 1, 2, 0, 1, 2, 2, 0, 1]
    model = LocalTransitionModel(smoothing=0.01)
    model.fit(seq)

    tm = model.get_transition_matrix()
    assert list(tm.index) == ["from_regime_0", "from_regime_1", "from_regime_2"]
    np.testing.assert_allclose(tm.values.sum(axis=1), 1.0, rtol=1e-9)

    nxt = model.predict_next_regime(0)
    assert set(nxt.keys()) == {0, 1, 2}
    np.testing.assert_allclose(sum(nxt.values()), 1.0, rtol=1e-9)

    # current_regime out of range -> uniform fallback
    fallback = model.predict_next_regime(99)
    np.testing.assert_allclose(sum(fallback.values()), 1.0, rtol=1e-9)

    # regime with recorded durations -> mean of runs
    dur = model.expected_duration(1)
    assert dur > 0


def test_transition_model_expected_duration_geometric() -> None:
    # regime 1 never appears -> no recorded durations, geometric fallback.
    model = LocalTransitionModel()
    model.fit([0, 2, 2, 0, 2, 0])
    assert model._n_regimes == 3
    dur = model.expected_duration(1)
    assert dur >= 1.0


def test_transition_model_predict_with_features_ignored() -> None:
    model = LocalTransitionModel()
    model.fit([0, 1, 0, 1])
    out = model.predict_next_regime(0, features={"x": 1.0})
    np.testing.assert_allclose(sum(out.values()), 1.0, rtol=1e-9)


# --------------------------------------------------------------------------
# InMemoryRegimePersistence
# --------------------------------------------------------------------------
def test_in_memory_persistence_roundtrip() -> None:
    store = InMemoryRegimePersistence()
    assert store.load_regime_sequence("missing") is None
    assert store.load_model_state("missing") is None

    store.save_regime_sequence("s1", ["t0", "t1"], [0, 1], {"src": "unit"})
    loaded = store.load_regime_sequence("s1")
    assert loaded == {
        "timestamps": ["t0", "t1"],
        "regimes": [0, 1],
        "metadata": {"src": "unit"},
    }

    # metadata None branch
    store.save_regime_sequence("s2", ["t0"], [0])
    loaded_s2 = store.load_regime_sequence("s2")
    assert loaded_s2 is not None
    assert loaded_s2["metadata"] == {}

    store.save_model_state("m1", {"w": [1.0, 2.0]})
    assert store.load_model_state("m1") == {"w": [1.0, 2.0]}


# --------------------------------------------------------------------------
# FileRegimePersistence
# --------------------------------------------------------------------------
def test_file_persistence_roundtrip(tmp_path: Path) -> None:
    store = FileRegimePersistence(tmp_path / "data")
    assert store.load_regime_sequence("nope") is None
    assert store.load_model_state("nope") is None

    store.save_regime_sequence("seq", ["t0", "t1"], [1, 2], {"k": "v"})
    loaded = store.load_regime_sequence("seq")
    assert loaded is not None
    assert loaded["regimes"] == [1, 2]
    assert loaded["metadata"] == {"k": "v"}

    # metadata None branch
    store.save_regime_sequence("seq2", ["t0"], [0])
    loaded2 = store.load_regime_sequence("seq2")
    assert loaded2 is not None
    assert loaded2["metadata"] == {}

    state = {
        "coef": np.array([1.0, 2.0]),
        "n": np.int64(3),
        "score": np.float64(0.5),
        "nested": {"arr": np.array([9.0])},
        "seq": (np.int64(1), 2),
        "name": "model",
    }
    store.save_model_state("model", state)
    restored = store.load_model_state("model")
    assert restored is not None
    assert restored["coef"] == [1.0, 2.0]
    assert restored["n"] == 3.0
    assert restored["score"] == 0.5
    assert restored["nested"]["arr"] == [9.0]
    assert restored["seq"] == [1.0, 2]
    assert restored["name"] == "model"


def test_file_persistence_make_serializable_plain_passthrough() -> None:
    assert FileRegimePersistence._make_serializable("literal") == "literal"
    assert FileRegimePersistence._make_serializable(7) == 7
