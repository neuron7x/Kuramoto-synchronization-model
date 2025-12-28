from __future__ import annotations

import pytest

from analytics.execution_quality import CancelReplaceSample, cancel_replace_latency


def test_cancel_replace_latency_returns_seconds() -> None:
    samples = [
        CancelReplaceSample(cancel_ts=10.0, replace_ts=10.25),
        CancelReplaceSample(cancel_ts=20.0, replace_ts=20.55),
    ]

    stats = cancel_replace_latency(samples)

    assert stats["count"] == pytest.approx(2.0)
    assert stats["mean"] == pytest.approx((0.25 + 0.55) / 2)
