# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for analytics.signals.irreversibility module."""

from __future__ import annotations

import pytest

from analytics.signals.irreversibility import IGSConfig


class TestIGSConfig:
    def test_defaults(self):
        cfg = IGSConfig()
        assert cfg.window == 600
        assert cfg.n_states == 7
        assert cfg.min_counts == 50
        assert cfg.eps == pytest.approx(1e-12)
        assert cfg.normalize_flux is True
        assert cfg.detrend is False
        assert cfg.quantize_mode == "zscore"
        assert cfg.perm_emb_dim == 5

    def test_custom(self):
        cfg = IGSConfig(window=100, n_states=5, detrend=True)
        assert cfg.window == 100
        assert cfg.n_states == 5
        assert cfg.detrend is True

    def test_adapt_params(self):
        cfg = IGSConfig(
            adapt_method="entropy",
            k_min=3,
            k_max=15,
            adapt_threshold=0.05,
            adapt_persist=5,
        )
        assert cfg.adapt_method == "entropy"
        assert cfg.k_min == 3
        assert cfg.k_max == 15

    def test_prometheus_defaults(self):
        cfg = IGSConfig()
        assert cfg.prometheus_enabled is False
        assert cfg.prometheus_async is True

    @pytest.mark.parametrize("mode", ["zscore", "rank"])
    def test_quantize_modes(self, mode):
        cfg = IGSConfig(quantize_mode=mode)
        assert cfg.quantize_mode == mode

    def test_regime_weights(self):
        cfg = IGSConfig(regime_weights=(2.0, 1.0, 0.5))
        assert cfg.regime_weights == (2.0, 1.0, 0.5)

    def test_signal_epr_q(self):
        cfg = IGSConfig(signal_epr_q=0.9)
        assert cfg.signal_epr_q == 0.9

    def test_max_update_ms(self):
        cfg = IGSConfig(max_update_ms=5.0)
        assert cfg.max_update_ms == 5.0

    def test_pi_method(self):
        cfg = IGSConfig(pi_method="stationary")
        assert cfg.pi_method == "stationary"

    def test_instrument_label(self):
        cfg = IGSConfig(instrument_label="BTCUSD")
        assert cfg.instrument_label == "BTCUSD"
