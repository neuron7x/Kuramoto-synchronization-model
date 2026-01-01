from __future__ import annotations

import logging

from ..core.sensory import SensoryFilter


def test_sensory_filter_non_finite_values(caplog) -> None:
    filt = SensoryFilter()
    obs = {"dd": float("nan"), "liq": float("inf"), "reg": 0.2, "vol": 0.1}

    with caplog.at_level(logging.WARNING):
        snapshot = filt.transform(obs)

    assert snapshot.filtered["dd"] == 0.0
    assert snapshot.filtered["liq"] == 0.0
    assert 0.0 <= snapshot.filtered["reg"] <= 1.0
    assert 0.0 <= snapshot.filtered["vol"] <= 1.0

    warnings = [record for record in caplog.records if record.levelno >= logging.WARNING]
    assert any("dd" in record.message for record in warnings)
    assert any("liq" in record.message for record in warnings)
