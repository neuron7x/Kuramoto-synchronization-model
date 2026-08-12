# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from geosync.core.neuro.dopamine.experimental_rpe import (
    RPEExtensionConfig,
    asymmetric_value_update,
    average_reward_vigor,
    canonical_td_error,
    compute_rpe_extension_surface,
    distributional_td_error,
    risk_adjusted_reward,
)


def test_extension_surface_preserves_canonical_td0_anchor() -> None:
    surface = compute_rpe_extension_surface(
        reward=0.25,
        value=0.40,
        next_value=0.50,
        discount_gamma=0.98,
        reward_quantiles=(-0.10, 0.0, 0.10),
    )

    expected = 0.25 + 0.98 * 0.50 - 0.40
    assert surface.canonical_delta == pytest.approx(expected)
    assert surface.risk_adjusted_delta == pytest.approx(surface.canonical_delta)


def test_distributional_td_error_is_affine_in_reward_quantiles() -> None:
    quantiles = (-0.20, -0.05, 0.0, 0.15, 0.35)
    deltas = distributional_td_error(
        quantiles,
        value=0.30,
        next_value=0.70,
        discount_gamma=0.95,
    )

    assert len(deltas) == len(quantiles)
    for left_reward, right_reward, left_delta, right_delta in zip(
        quantiles,
        quantiles[1:],
        deltas,
        deltas[1:],
    ):
        assert right_delta - left_delta == pytest.approx(right_reward - left_reward)


def test_asymmetric_value_update_keeps_raw_delta_outside_learning_rate() -> None:
    positive = asymmetric_value_update(
        0.50,
        positive_alpha=0.20,
        negative_alpha=0.05,
    )
    negative = asymmetric_value_update(
        -0.50,
        positive_alpha=0.20,
        negative_alpha=0.05,
    )

    assert positive == pytest.approx(0.10)
    assert negative == pytest.approx(-0.025)
    assert canonical_td_error(0.50, 0.0, 0.0, 1.0) == pytest.approx(0.50)


def test_risk_penalty_does_not_increase_reward() -> None:
    adjusted = risk_adjusted_reward(
        reward=0.10,
        volatility=0.20,
        drawdown=-0.30,
        volatility_penalty=0.40,
        drawdown_penalty=0.50,
    )

    assert adjusted <= 0.10
    assert adjusted == pytest.approx(0.10 - 0.40 * 0.20 - 0.50 * 0.30)


def test_configured_surface_keeps_canonical_delta_unchanged() -> None:
    cfg = RPEExtensionConfig(
        positive_alpha=0.30,
        negative_alpha=0.10,
        volatility_penalty=0.20,
        drawdown_penalty=0.30,
        vigor_gain=0.50,
        vigor_min=0.25,
        vigor_max=1.50,
    )
    surface = compute_rpe_extension_surface(
        reward=0.40,
        value=0.10,
        next_value=0.20,
        discount_gamma=0.90,
        reward_quantiles=(0.10, 0.40, 0.70),
        volatility=0.50,
        drawdown=0.25,
        average_reward=0.20,
        config=cfg,
    )

    canonical = 0.40 + 0.90 * 0.20 - 0.10
    risk_reward = 0.40 - 0.20 * 0.50 - 0.30 * 0.25
    assert surface.canonical_delta == pytest.approx(canonical)
    assert surface.risk_adjusted_delta == pytest.approx(
        risk_reward + 0.90 * 0.20 - 0.10,
    )
    assert surface.asymmetric_value_update == pytest.approx(
        cfg.positive_alpha * canonical,
    )
    assert surface.average_reward_vigor == pytest.approx(
        1.0 + 0.50 * (0.40 - 0.20),
    )


def test_canonical_td_error_rejects_nonfinite_output() -> None:
    with pytest.raises(ValueError, match="canonical_delta must be finite"):
        canonical_td_error(1.0e308, -1.0e308, 1.0e308, 1.0)


def test_risk_adjusted_reward_rejects_nonfinite_output() -> None:
    with pytest.raises(ValueError, match="risk_adjusted_reward must be finite"):
        risk_adjusted_reward(
            reward=0.0,
            volatility=1.0e200,
            drawdown=1.0e200,
            volatility_penalty=1.0e200,
            drawdown_penalty=0.0,
        )


def test_average_reward_vigor_rejects_nonfinite_preclamp() -> None:
    with pytest.raises(ValueError, match="clamp value must be finite"):
        average_reward_vigor(
            reward=1.0e200,
            average_reward=-1.0e200,
            gain=1.0e200,
            lower=0.1,
            upper=2.0,
        )
