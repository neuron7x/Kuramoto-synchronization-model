# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for robustness primitives (CPCV, PBO, PSR, null audit, jitter)."""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import pytest

from research.robustness.cpcv import (
    cpcv_splits,
    estimate_pbo,
    probabilistic_sharpe_ratio,
    rolling_probabilistic_sharpe,
)
from research.robustness.null_audit import run_null_falsification_audit
from research.robustness.stability import parameter_jitter_stability


class TestCPCVSplits:
    def test_split_count_equals_binomial_coefficient(self) -> None:
        splits = list(cpcv_splits(300, n_groups=6, n_test_groups=2))
        assert len(splits) == math.comb(6, 2) == 15

    def test_train_and_test_are_disjoint(self) -> None:
        for split in cpcv_splits(100, n_groups=5, n_test_groups=2, embargo=3):
            assert np.intersect1d(split.train_index, split.test_index).size == 0

    def test_embargo_purges_adjacent_train_samples(self) -> None:
        split = next(cpcv_splits(100, n_groups=4, n_test_groups=1, embargo=5))
        test = split.test_index
        tmin, tmax = int(test.min()), int(test.max())
        for t in split.train_index:
            assert not (tmin - 5 <= t <= tmax + 5)

    def test_invalid_inputs_raise(self) -> None:
        with pytest.raises(ValueError):
            next(cpcv_splits(0, 2, 1))
        with pytest.raises(ValueError):
            next(cpcv_splits(10, 1, 1))
        with pytest.raises(ValueError):
            next(cpcv_splits(10, 3, 3))
        with pytest.raises(ValueError):
            next(cpcv_splits(10, 2, 1, embargo=-1))


class TestPBO:
    def test_overfit_family_reports_high_pbo(self) -> None:
        rng = np.random.default_rng(42)
        # pure-noise strategies: best IS rarely is best OOS → PBO should be ~0.5
        oos = rng.normal(0.0, 1.0, size=(30, 8))
        pbo = estimate_pbo(oos)
        assert 0.2 <= pbo <= 0.8

    def test_clean_family_reports_low_pbo(self) -> None:
        rng = np.random.default_rng(42)
        # one dominant strategy, small noise → best IS ≈ best OOS → low PBO
        means = np.array([5.0, 0.1, 0.2, 0.3, 0.0])
        oos = means + rng.normal(0.0, 0.1, size=(50, 5))
        assert estimate_pbo(oos) <= 0.1

    def test_degenerate_shapes_raise(self) -> None:
        with pytest.raises(ValueError):
            estimate_pbo(np.zeros(10))
        with pytest.raises(ValueError):
            estimate_pbo(np.zeros((1, 5)))
        with pytest.raises(ValueError):
            estimate_pbo(np.zeros((5, 1)))


class TestPSR:
    def test_high_sharpe_long_sample_returns_near_one(self) -> None:
        rng = np.random.default_rng(42)
        # annual 0.5 / 0.15 ≈ 3.3 Sharpe on daily — very strong
        r = rng.normal(0.002, 0.009, size=1000)
        assert probabilistic_sharpe_ratio(r) > 0.99

    def test_zero_sharpe_returns_half(self) -> None:
        # Exactly zero-mean sample (symmetric pairs) → SR == 0 → PSR == 0.5.
        half = np.linspace(-0.05, 0.05, 1000)
        r = np.concatenate([half, -half])
        psr = probabilistic_sharpe_ratio(r)
        assert 0.45 <= psr <= 0.55

    def test_short_or_nonfinite_returns_nan(self) -> None:
        assert math.isnan(probabilistic_sharpe_ratio(np.array([1.0])))
        assert math.isnan(probabilistic_sharpe_ratio(np.array([1.0, float("nan"), 2.0])))
        # zero variance
        assert math.isnan(probabilistic_sharpe_ratio(np.ones(10)))

    def test_rolling_psr_shape_and_head_nan(self) -> None:
        rng = np.random.default_rng(42)
        r = rng.normal(0.001, 0.01, size=500)
        out = rolling_probabilistic_sharpe(r, window=60)
        assert out.shape == r.shape
        assert np.all(np.isnan(out[:59]))
        assert np.all(np.isfinite(out[60:]))


class TestNullAudit:
    def test_four_families_returned(self) -> None:
        rng = np.random.default_rng(42)
        sig = rng.choice([-1.0, 0.0, 1.0], size=500)
        tgt = rng.normal(0.001, 0.01, size=500)
        out = run_null_falsification_audit(sig, tgt, n_bootstrap=50)
        assert len(out) == 4
        names = {r.family for r in out}
        assert names == {
            "permuted_target",
            "block_permuted_signal",
            "inverted_signal",
            "lag_surrogate",
        }

    def test_p_value_bounds_and_count(self) -> None:
        rng = np.random.default_rng(42)
        sig = rng.choice([-1.0, 1.0], size=200)
        tgt = rng.normal(0.0, 0.01, size=200)
        out = run_null_falsification_audit(sig, tgt, n_bootstrap=100)
        for r in out:
            assert 0.0 < r.p_value <= 1.0
            assert r.n_bootstrap == 100
            assert len(r.null_sharpes) == 100

    def test_deterministic_seed(self) -> None:
        rng = np.random.default_rng(42)
        sig = rng.choice([-1.0, 1.0], size=200)
        tgt = rng.normal(0.0, 0.01, size=200)
        a = run_null_falsification_audit(sig, tgt, n_bootstrap=30, seed=123)
        b = run_null_falsification_audit(sig, tgt, n_bootstrap=30, seed=123)
        for ra, rb in zip(a, b, strict=True):
            assert ra.p_value == rb.p_value
            assert ra.null_sharpes == rb.null_sharpes

    def test_inputs_validated(self) -> None:
        x = np.zeros(10)
        with pytest.raises(ValueError):
            run_null_falsification_audit(x, x[:5])
        with pytest.raises(ValueError):
            run_null_falsification_audit(x, x, n_bootstrap=0)
        with pytest.raises(ValueError):
            run_null_falsification_audit(x, x, lag_range=(0, 3))


class TestJitterStability:
    def test_anchor_recovered_at_zero_jitter(self) -> None:
        def evaluator(params: Mapping[str, float]) -> float:
            return 1.5

        res = parameter_jitter_stability(
            anchor_parameters={"a": 1.0, "b": 2.0},
            evaluator=evaluator,
            jitter_fractions={"a": 0.0},
            n_candidates=10,
            sharpe_tolerance=0.0,
        )
        assert res.anchor_sharpe == pytest.approx(1.5)
        assert res.fraction_within_tol == pytest.approx(1.0)

    def test_parameter_not_in_anchor_raises(self) -> None:
        def evaluator(params: Mapping[str, float]) -> float:
            return 1.0

        with pytest.raises(ValueError):
            parameter_jitter_stability(
                anchor_parameters={"a": 1.0},
                evaluator=evaluator,
                jitter_fractions={"z": 0.1},
                n_candidates=5,
                sharpe_tolerance=0.1,
            )

    def test_negative_jitter_raises(self) -> None:
        def evaluator(params: Mapping[str, float]) -> float:
            return 1.0

        with pytest.raises(ValueError):
            parameter_jitter_stability(
                anchor_parameters={"a": 1.0},
                evaluator=evaluator,
                jitter_fractions={"a": -0.1},
                n_candidates=5,
                sharpe_tolerance=0.1,
            )
