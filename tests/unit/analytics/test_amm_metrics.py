# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import analytics.amm_metrics as amm_metrics


class MetricFake:
    def __init__(self):
        self.labels_calls = []
        self.set_calls = []
        self.inc_calls = []
        self.observe_calls = []

    def labels(self, *args):
        self.labels_calls.append(args)
        return self

    def set(self, value):
        self.set_calls.append(value)
        return value

    def inc(self, amount=1):
        self.inc_calls.append(amount)

    def observe(self, value):
        self.observe_calls.append(value)


def test_publish_metrics_records_values(monkeypatch):
    pulse = MetricFake()
    precision = MetricFake()
    gain = MetricFake()
    theta_metric = MetricFake()
    burst = MetricFake()

    monkeypatch.setattr(amm_metrics, "_g_pulse", pulse)
    monkeypatch.setattr(amm_metrics, "_g_prec", precision)
    monkeypatch.setattr(amm_metrics, "_g_gain", gain)
    monkeypatch.setattr(amm_metrics, "_g_theta", theta_metric)
    monkeypatch.setattr(amm_metrics, "_c_burst", burst)

    out = {"amm_pulse": 7.5, "amm_precision": 0.42}
    symbol = "BTC-USD"
    tf = "1h"
    k = 1.2
    theta = 0.9

    amm_metrics.publish_metrics(symbol, tf, out, k, theta)
    amm_metrics.publish_metrics(symbol, tf, out, k, theta, q_hi=7.5)

    assert pulse.labels_calls == [(symbol, tf), (symbol, tf)]
    assert pulse.set_calls == [out["amm_pulse"], out["amm_pulse"]]

    assert precision.labels_calls == [(symbol, tf), (symbol, tf)]
    assert precision.set_calls == [out["amm_precision"], out["amm_precision"]]

    assert gain.labels_calls == [(symbol, tf), (symbol, tf)]
    assert gain.set_calls == [k, k]

    assert theta_metric.labels_calls == [(symbol, tf), (symbol, tf)]
    assert theta_metric.set_calls == [theta, theta]

    assert burst.labels_calls == [(symbol, tf)]
    assert burst.inc_calls == [1]


def test_timed_update_observes_duration(monkeypatch):
    histogram = MetricFake()
    monkeypatch.setattr(amm_metrics, "_h_update", histogram)

    times = iter([100.0, 101.5])
    monkeypatch.setattr(amm_metrics.time, "perf_counter", lambda: next(times))

    symbol = "ETH-USD"
    tf = "5m"

    with amm_metrics.timed_update(symbol, tf):
        pass

    assert histogram.labels_calls == [(symbol, tf)]
    assert len(histogram.observe_calls) == 1
    assert histogram.observe_calls[0] > 0
