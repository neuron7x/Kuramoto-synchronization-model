# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import contextlib

import pytest

torch = pytest.importorskip("torch")

from core.neuro.shocks import ShockScenario, ShockScenarioGenerator  # noqa: E402


def _baseline() -> list[list[float]]:
    return [
        [0.1, 0.05, 0.02, 0.01],
        [0.12, 0.045, 0.018, 0.015],
        [0.09, 0.06, 0.021, 0.009],
        [0.11, 0.07, 0.019, 0.012],
    ]


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
    assert scenario.predicted_drawdown <= 0.02 + 1e-3
    assert scenario.novelty_score >= 0.02

    generated = generator.generate(count=2)
    assert len(generated) == 2
    assert all(item.predicted_drawdown <= 0.02 + 1e-6 for item in generated)

    assert captured[0][0] == "chaos.shock-generator"
    assert captured[0][1]["phase"] == "training"


def test_shock_generator_generate_requires_training() -> None:
    generator = ShockScenarioGenerator(
        _baseline(),
        risk_tolerance=0.05,
        seed=3,
        device="cpu",
    )

    with pytest.raises(RuntimeError, match="train must be executed"):
        generator.generate()


def test_build_scenario_clamps_to_risk_tolerance() -> None:
    generator = ShockScenarioGenerator(
        _baseline(),
        feature_names=("latency", "liquidity", "tariff", "correlation"),
        risk_tolerance=0.05,
        seed=11,
        device="cpu",
    )

    metrics = {
        "novelty": torch.tensor([0.6], dtype=torch.float32, device=generator._device),
        "drawdown": torch.tensor([0.2], dtype=torch.float32, device=generator._device),
        "correlation": torch.tensor([0.1], dtype=torch.float32, device=generator._device),
    }
    sample = torch.tensor([0.2, 0.1, 0.05, 0.03], dtype=torch.float32, device=generator._device)

    scenario = generator._build_scenario(sample, metrics, 0)

    assert scenario.predicted_drawdown == pytest.approx(generator._risk_tolerance)
    assert scenario.values["latency"] == pytest.approx(0.2)
    assert scenario.values["liquidity"] == pytest.approx(0.1)
    assert scenario.values["tariff"] == pytest.approx(0.05)
    assert scenario.values["correlation"] == pytest.approx(0.03)


def test_generate_reuses_best_and_clamps_new_scenarios(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = ShockScenarioGenerator(
        _baseline(),
        risk_tolerance=0.05,
        seed=19,
        device="cpu",
    )

    feature_names = getattr(generator, "_feature_names")
    best = ShockScenario(
        values={name: 0.01 for name in feature_names},
        predicted_drawdown=0.01,
        novelty_score=0.4,
        correlation=0.05,
    )
    generator._best = best

    def _fake_evaluate(self, state, scenario):
        drawdown = torch.full((state.size(0),), 0.2, dtype=torch.float32, device=self._device)
        novelty = torch.full((state.size(0),), 0.5, dtype=torch.float32, device=self._device)
        correlation = torch.zeros(state.size(0), dtype=torch.float32, device=self._device)
        reward = torch.full((state.size(0),), 0.3, dtype=torch.float32, device=self._device)
        return reward, {
            "novelty": novelty,
            "drawdown": drawdown,
            "correlation": correlation,
        }

    monkeypatch.setattr(ShockScenarioGenerator, "_evaluate", _fake_evaluate)

    generated = generator.generate(count=3)

    assert generated[0] is best
    assert len(generated) == 3
    assert all(isinstance(item, ShockScenario) for item in generated)
    for scenario in generated[1:]:
        assert scenario is not best
        assert scenario.predicted_drawdown == pytest.approx(generator._risk_tolerance)
