from __future__ import annotations

import contextlib

import pytest

torch = pytest.importorskip("torch")

from core.neuro.shocks import ShockScenarioGenerator


def _baseline() -> torch.Tensor:
    data = [
        [0.1, 0.05, 0.02, 0.01],
        [0.12, 0.045, 0.018, 0.015],
        [0.09, 0.06, 0.021, 0.009],
        [0.11, 0.07, 0.019, 0.012],
    ]
    return torch.tensor(data, dtype=torch.float32)


def test_shock_generator_trains_on_historic_shocks(monkeypatch):
    captured: list[tuple[str, dict[str, object]]] = []

    def fake_pipeline(stage: str, **attrs):
        captured.append((stage, attrs))
        return contextlib.nullcontext(None)

    monkeypatch.setattr("observability.tracing.pipeline_span", fake_pipeline)

    generator = ShockScenarioGenerator(
        _baseline(),
        feature_names=("latency", "liquidity", "tariff", "correlation"),
        risk_tolerance=0.02,
        seed=7,
        device="cpu",
    )

    scenario = generator.train(steps=24, batch_size=8)
    assert scenario.predicted_drawdown <= pytest.approx(0.02, abs=1e-3)
    assert scenario.novelty_score >= 0.02

    generated = generator.generate(count=2)
    assert len(generated) == 2
    assert all(item.predicted_drawdown <= 0.02 + 1e-6 for item in generated)

    assert captured[0][0] == "chaos.shock-generator"
    assert captured[0][1]["phase"] == "training"
