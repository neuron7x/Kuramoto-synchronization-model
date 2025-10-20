import sys
import types

import numpy as np
import pandas as pd
import pytest

from analytics.signals.irreversibility import IGSConfig, StreamingIGS


def test_streaming_igs_resets_on_non_monotonic_timestamp():
    cfg = IGSConfig(window=10, min_counts=3)
    engine = StreamingIGS(cfg)

    t0 = pd.Timestamp("2024-01-01T00:00:00Z")
    t1 = t0 + pd.Timedelta(minutes=1)

    assert engine.update(t0, 100.0) is None
    assert engine.update(t1, 101.0) is None
    assert engine.last_timestamp == t1

    regression_metrics = engine.update(t0, 102.0)

    assert regression_metrics is None
    assert engine.last_timestamp is None
    assert engine.last_price is None
    assert not engine.returns
    assert not engine.states
    assert np.all(engine.T == 0.0)
    assert np.all(engine.row_sums == 0.0)


def test_streaming_igs_resets_on_timezone_mismatch():
    cfg = IGSConfig(window=10, min_counts=3)
    engine = StreamingIGS(cfg)

    aware_ts = pd.Timestamp("2024-01-01T00:00:00Z")
    naive_ts = pd.Timestamp("2024-01-01T00:01:00")

    assert engine.update(aware_ts, 100.0) is None
    assert engine.update(naive_ts, 101.0) is None

    assert engine.last_timestamp is None
    assert engine.last_price is None
    assert not engine.returns
    assert not engine.states


def test_streaming_igs_updates_prometheus_gauges_inline(monkeypatch):
    from analytics.signals import irreversibility as irr

    recorded: dict[str, dict[str, float | str]] = {}

    class FakeGauge:
        def __init__(self, name: str, _doc: str, _labels: list[str]):
            self.name = name

        def labels(self, label: str):
            entry = recorded.setdefault(self.name, {})
            entry["label"] = label
            return self

        def set(self, value: float) -> None:
            recorded.setdefault(self.name, {})["value"] = value

    try:
        import prometheus_client as prom_mod  # type: ignore
    except ImportError:
        prom_mod = types.ModuleType("prometheus_client")
        monkeypatch.setitem(sys.modules, "prometheus_client", prom_mod)

    monkeypatch.setattr(prom_mod, "Gauge", FakeGauge)
    monkeypatch.setattr(irr, "prometheus_client", prom_mod, raising=False)

    cfg = irr.IGSConfig(
        window=5,
        min_counts=2,
        prometheus_enabled=True,
        prometheus_async=False,
        instrument_label="btcusd",
    )
    engine = irr.StreamingIGS(cfg)

    assert engine.metrics.enabled is True
    assert engine.metrics.async_enabled is False

    engine.metrics.emit(1.23, -0.45, 0.67, 9)

    expected = {
        "igs_epr": {"label": "btcusd", "value": pytest.approx(1.23)},
        "igs_flux_index": {"label": "btcusd", "value": pytest.approx(-0.45)},
        "igs_regime_score": {"label": "btcusd", "value": pytest.approx(0.67)},
        "igs_states_k": {"label": "btcusd", "value": pytest.approx(9.0)},
    }

    assert recorded == expected
