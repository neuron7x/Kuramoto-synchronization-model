# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import pandas as pd

from analytics.signals.irreversibility import IGSConfig, igs_directional_signal


def _make_features() -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=5, freq="min")
    return pd.DataFrame(
        {
            "epr": [0.1, 0.5, 0.9, 0.4, 1.2],
            "flux_index": [0.05, 0.2, -0.3, 0.01, 0.8],
        },
        index=idx,
    )


def test_directional_signal_uses_config_quantile_threshold():
    features = _make_features()
    default_cfg = IGSConfig(signal_epr_q=0.7, signal_flux_min=0.0)
    permissive_cfg = IGSConfig(signal_epr_q=0.2, signal_flux_min=0.0)

    default_signal = igs_directional_signal(features, cfg=default_cfg)
    permissive_signal = igs_directional_signal(features, cfg=permissive_cfg)

    assert default_signal.tolist() == [0, 0, -1, 0, 1]
    assert permissive_signal.tolist() == [0, 1, -1, 1, 1]


def test_directional_signal_respects_flux_threshold_from_config():
    features = _make_features()
    cfg = IGSConfig(signal_epr_q=0.2, signal_flux_min=0.3)

    signal = igs_directional_signal(features, cfg=cfg)

    assert signal.tolist() == [0, 0, 0, 0, 1]


def test_directional_signal_accepts_positional_thresholds():
    features = _make_features()

    positional_signal = igs_directional_signal(features, 0.2, 0.05)
    keyword_signal = igs_directional_signal(features, epr_q=0.2, flux_min=0.05)

    assert positional_signal.equals(keyword_signal)


def test_directional_signal_accepts_positional_config():
    features = _make_features()
    cfg = IGSConfig(signal_epr_q=0.2, signal_flux_min=0.3)

    positional_signal = igs_directional_signal(features, cfg)
    keyword_signal = igs_directional_signal(features, cfg=cfg)

    assert positional_signal.equals(keyword_signal)
