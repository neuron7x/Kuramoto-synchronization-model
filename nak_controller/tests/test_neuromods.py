from __future__ import annotations

import pytest

from nak_controller.control.neuromods import (
    apply_arousal_attention_hooks,
)


@pytest.mark.parametrize(
    "na, ach",
    [(0.2, 0.3), (0.5, 0.5), (0.9, 0.8)],
)
def test_apply_arousal_attention_hooks_bounds(na: float, ach: float) -> None:
    result = apply_arousal_attention_hooks(
        rate=0.6,
        activity_mult=1.0,
        noradrenaline_level=na,
        acetylcholine_level=ach,
        r_min=0.1,
        r_max=1.0,
        na_scale=0.4,
    )
    assert 0.1 <= result.risk_rate <= 1.0
    assert 0.1 <= result.activity_multiplier <= 2.0


def test_apply_arousal_attention_hooks_directionality() -> None:
    low = apply_arousal_attention_hooks(
        rate=0.5,
        activity_mult=1.0,
        noradrenaline_level=0.2,
        acetylcholine_level=0.2,
        r_min=0.1,
        r_max=1.0,
        na_scale=0.4,
    )
    high = apply_arousal_attention_hooks(
        rate=0.5,
        activity_mult=1.0,
        noradrenaline_level=0.8,
        acetylcholine_level=0.8,
        r_min=0.1,
        r_max=1.0,
        na_scale=0.4,
    )
    assert high.risk_rate > low.risk_rate
    assert high.activity_multiplier > low.activity_multiplier
