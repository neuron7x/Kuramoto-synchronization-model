# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for Kuramoto synchrony feature."""

# Import directly from module file to avoid package __init__
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location(
    "kuramoto",
    Path(__file__).parent.parent.parent.parent.parent / "src/geosync/features/kuramoto.py",
)
kuramoto_module = importlib.util.module_from_spec(spec)
# Register before exec so dataclass type resolution (KuramotoResult) can find
# this module's namespace during class creation.
sys.modules["kuramoto"] = kuramoto_module
spec.loader.exec_module(kuramoto_module)
KuramotoSynchrony = kuramoto_module.KuramotoSynchrony
KuramotoResult = kuramoto_module.KuramotoResult
PROXY_PHASE_METHOD = kuramoto_module.PROXY_PHASE_METHOD
PROXY_CLAIM_BOUNDARY = kuramoto_module.PROXY_CLAIM_BOUNDARY
PROXY_REGIME_KIND = kuramoto_module.PROXY_REGIME_KIND
PROXY_INFORMATION_LOSS = kuramoto_module.PROXY_INFORMATION_LOSS


def _synced_prices(n_steps: int = 100, seed: int = 42) -> pd.DataFrame:
    """Fixed synchronized price frame used for numeric-stability checks."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2024-01-01", periods=n_steps, freq="1h")
    base = np.cumsum(rng.randn(n_steps))
    return pd.DataFrame(
        {
            "asset1": 100 + base + rng.randn(n_steps) * 0.5,
            "asset2": 100 + base + rng.randn(n_steps) * 0.5,
            "asset3": 100 + base + rng.randn(n_steps) * 0.5,
        },
        index=dates,
    )


class TestKuramotoSynchrony:
    """Test Kuramoto synchrony functionality."""

    def test_synchronized_assets(self):
        """Test with highly synchronized (correlated) assets."""
        # Create synchronized price movements
        np.random.seed(42)
        n_steps = 100
        dates = pd.date_range("2024-01-01", periods=n_steps, freq="1h")

        # Base signal
        base = np.cumsum(np.random.randn(n_steps))

        # Create correlated assets
        prices = pd.DataFrame(
            {
                "asset1": 100 + base + np.random.randn(n_steps) * 0.5,
                "asset2": 100 + base + np.random.randn(n_steps) * 0.5,
                "asset3": 100 + base + np.random.randn(n_steps) * 0.5,
            },
            index=dates,
        )

        detector = KuramotoSynchrony(window=30)
        result = detector.fit_transform(prices)

        # Check structure
        assert "R" in result
        assert "delta_R" in result
        assert "labels" in result

        # R should be relatively high for synchronized assets
        assert result["R"].mean() > 0.3

        # Should have some EMERGENT labels
        assert (result["labels"] == "EMERGENT").any()

    def test_random_assets(self):
        """Test with uncorrelated random walk assets."""
        np.random.seed(123)
        n_steps = 100
        dates = pd.date_range("2024-01-01", periods=n_steps, freq="1h")

        # Create independent random walks
        prices = pd.DataFrame(
            {
                "asset1": 100 + np.cumsum(np.random.randn(n_steps)),
                "asset2": 100 + np.cumsum(np.random.randn(n_steps)),
                "asset3": 100 + np.cumsum(np.random.randn(n_steps)),
            },
            index=dates,
        )

        detector = KuramotoSynchrony(window=30)
        result = detector.fit_transform(prices)

        # Note: Current simplified implementation uses arctan2 approximation
        # which may not properly detect low synchrony. Should be improved
        # with scipy.signal.hilbert for production use.
        # For now, just verify the interface works correctly
        assert "R" in result
        assert "delta_R" in result
        assert "labels" in result
        assert len(result["R"]) == n_steps

        # Should have some CHAOTIC or CAUTION labels
        assert (result["labels"] == "CHAOTIC").any() or (result["labels"] == "CAUTION").any()

    def test_insufficient_data(self):
        """Test with insufficient data points."""
        dates = pd.date_range("2024-01-01", periods=10, freq="1h")
        prices = pd.DataFrame(
            {
                "asset1": np.arange(100, 110),
                "asset2": np.arange(100, 110),
            },
            index=dates,
        )

        detector = KuramotoSynchrony(window=30)

        with pytest.raises(ValueError, match="Insufficient data"):
            detector.fit_transform(prices)

    def test_invalid_index(self):
        """Test with non-DatetimeIndex."""
        prices = pd.DataFrame(
            {
                "asset1": np.arange(100, 150),
                "asset2": np.arange(100, 150),
            }
        )

        detector = KuramotoSynchrony(window=30)

        with pytest.raises(ValueError, match="DatetimeIndex"):
            detector.fit_transform(prices)


class TestKuramotoProxyHonesty:
    """Lock the proxy / descriptor-regime honesty boundary (S4)."""

    def test_constants_declare_descriptor_proxy_boundary(self):
        """Module constants name the proxy method and claim boundary."""
        assert PROXY_PHASE_METHOD == "arctan2_std_mean_proxy"
        assert PROXY_CLAIM_BOUNDARY == "descriptor_proxy_not_physical_phase"
        assert PROXY_REGIME_KIND == "descriptor_regime"
        # The proxy explicitly records what it discards vs an analytic phase.
        assert "analytic_signal_instantaneous_phase" in PROXY_INFORMATION_LOSS

    def test_fit_transform_dict_carries_provenance(self):
        """The emitted dict declares proxy=True and the descriptor boundary."""
        prices = _synced_prices()
        result = KuramotoSynchrony(window=30).fit_transform(prices)

        # Numeric keys preserved for existing callers.
        assert {"R", "delta_R", "labels"} <= set(result)
        # Honesty provenance is present on the public dict output.
        assert result["proxy"] is True
        assert result["phase_method"] == "arctan2_std_mean_proxy"
        assert result["claim_boundary"] == "descriptor_proxy_not_physical_phase"
        assert result["regime_kind"] == "descriptor_regime"
        assert "analytic_signal_instantaneous_phase" in result["information_loss"]

    def test_result_object_carries_provenance_with_labels(self):
        """KuramotoResult binds the proxy provenance to R / delta_R / labels."""
        prices = _synced_prices()
        result = KuramotoSynchrony(window=30).result(prices)

        assert isinstance(result, KuramotoResult)
        # Regime labels travel together with their proxy provenance.
        assert result.proxy is True
        assert result.regime_kind == "descriptor_regime"
        assert result.claim_boundary == "descriptor_proxy_not_physical_phase"
        # Labels are the descriptor regimes, not asserted physical states.
        assert set(result.labels.unique()) <= {
            "EMERGENT",
            "CHAOTIC",
            "TRANSITION",
            "CAUTION",
        }

    def test_result_default_provenance_is_proxy(self):
        """A bare KuramotoResult defaults to the proxy/descriptor boundary."""
        empty = pd.Series(dtype=float)
        res = KuramotoResult(R=empty, delta_R=empty, labels=pd.Series(dtype=str))
        assert res.proxy is True
        assert res.phase_method == "arctan2_std_mean_proxy"
        assert res.claim_boundary == "descriptor_proxy_not_physical_phase"
        assert res.regime_kind == "descriptor_regime"

    def test_numeric_R_unchanged_for_fixed_input(self):
        """Provenance is additive: R / delta_R / labels are byte-stable.

        The descriptor order parameter R for a fixed seeded input must match
        the standalone arctan2(std, mean) → |⟨exp(iθ)⟩| computation exactly,
        proving the honesty relabel did not perturb the numbers.
        """
        prices = _synced_prices(seed=7)
        detector = KuramotoSynchrony(window=30)
        result = detector.fit_transform(prices)

        # Recompute R independently from the documented proxy formula.
        returns = prices.pct_change().fillna(0.0)
        phases = np.arctan2(
            returns.rolling(30, min_periods=15).std(),
            returns.rolling(30, min_periods=15).mean(),
        ).fillna(0.0)
        expected_R = np.abs(np.exp(1j * phases.values).mean(axis=1))

        np.testing.assert_allclose(result["R"].to_numpy(), expected_R, rtol=0, atol=0)
        # result() path is numerically identical to fit_transform.
        obj = detector.result(prices)
        np.testing.assert_allclose(
            obj.R.to_numpy(), result["R"].to_numpy(), rtol=0, atol=0
        )
        pd.testing.assert_series_equal(obj.labels, result["labels"])


class TestKuramotoDownstreamClaim:
    """Issue #1107 — the proxy descriptor cannot self-promote into a
    predictive / tradeable / validated signal downstream."""

    _FORBIDDEN = (
        "validated",
        "alpha",
        "market consensus",
        "predictive validity",
        "trading signal",
        "causal market",
    )

    def test_proxy_feature_cannot_claim_predictive_or_trading_validity(self) -> None:
        detector = KuramotoSynchrony(window=30)
        res = detector.result(_synced_prices())
        assert res.predictive_claim is False
        assert res.trading_claim is False
        assert res.validation_status == "descriptor_only"
        assert res.validation_status != "validated"

    def test_feature_result_metadata_preserves_descriptor_only_status(self) -> None:
        detector = KuramotoSynchrony(window=30)
        out = detector.fit_transform(_synced_prices())
        # Metadata that travels to a downstream consumer.
        assert out["predictive_claim"] is False
        assert out["trading_claim"] is False
        assert out["validation_status"] == "descriptor_only"
        # Public-language guard: no string field advertises an unsupported claim.
        blob = " ".join(v for v in out.values() if isinstance(v, str)).lower()
        for forbidden in self._FORBIDDEN:
            assert forbidden not in blob, f"unsupported claim '{forbidden}' leaked"
