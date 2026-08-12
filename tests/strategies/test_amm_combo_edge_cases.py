# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from collections import deque
from typing import Callable

import pytest

from backtest.strategies.amm_combo import AMMComboStrategy, AMMStrategyConfig


class DummyAMM:
    def __init__(
        self,
        _cfg: AMMStrategyConfig,
        *,
        outputs: deque[dict],
        use_internal_entropy: bool,
    ) -> None:
        self.outputs = outputs
        self.use_internal_entropy = use_internal_entropy
        self.calls: list[tuple[float, float, float, float | None]] = []

    def update(self, x_t: float, R_t: float, kappa_t: float, H_t: float | None = None) -> dict:
        self.calls.append((x_t, R_t, kappa_t, H_t))
        if self.outputs:
            return self.outputs.popleft()
        return {
            "amm_pulse": 0.0,
            "amm_precision": 1.0,
            "amm_valence": 0.0,
            "pe": 0.0,
        }


@pytest.fixture()
def dummy_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[deque[dict]], tuple[AMMComboStrategy, DummyAMM]]:
    created: dict[str, DummyAMM] = {}

    def factory(cfg: AMMStrategyConfig, use_internal_entropy: bool = True) -> DummyAMM:
        outputs = created.pop("outputs")
        amm = DummyAMM(cfg, outputs=outputs, use_internal_entropy=use_internal_entropy)
        created.setdefault("instances", []).append(amm)
        return amm

    def creator(
        outputs: deque[dict], *, config: AMMStrategyConfig | None = None
    ) -> tuple[AMMComboStrategy, DummyAMM]:
        created["outputs"] = outputs
        strategy = AMMComboStrategy(config or AMMStrategyConfig())
        amm = created["instances"].pop()
        return strategy, amm

    monkeypatch.setattr(
        "backtest.strategies.amm_combo.AdaptiveMarketMind",
        lambda cfg, use_internal_entropy=True: factory(
            cfg, use_internal_entropy=use_internal_entropy
        ),
    )

    return creator


def test_strategy_exit_path_uses_external_entropy(dummy_strategy) -> None:
    outputs = deque(
        [
            {
                "amm_pulse": 0.01,
                "amm_precision": 1.5,
                "amm_valence": 0.0,
                "pe": 0.0,
            }
        ]
    )
    cfg = AMMStrategyConfig()
    cfg.use_external_entropy = True
    strategy, amm = dummy_strategy(outputs, config=cfg)

    result = strategy.on_step(0.5, R_t=0.1, kappa_t=0.2, H_t=0.3)
    assert result["action"] == "EXIT_ALL"
    assert result["direction"] == 0
    assert amm.use_internal_entropy is False
    assert amm.calls[-1][3] == 0.3


def test_strategy_enters_long_when_thresholds_met(dummy_strategy) -> None:
    outputs = deque(
        [
            {
                "amm_pulse": 0.2,
                "amm_precision": 1.0,
                "amm_valence": 1.0,
                "pe": 0.01,
            },
            {
                "amm_pulse": 0.95,
                "amm_precision": 2.0,
                "amm_valence": 1.0,
                "pe": 0.02,
            },
        ]
    )
    strategy, _ = dummy_strategy(outputs)

    warmup = strategy.on_step(0.2, R_t=0.2, kappa_t=0.1)
    assert warmup["action"] == "EXIT_ALL"

    result = strategy.on_step(0.4, R_t=strategy.cfg.R_min + 0.1, kappa_t=0.3)
    assert result["action"] == "ENTER_LONG"
    assert result["direction"] == 1
    assert result["size"] >= 0.0


def test_strategy_enters_short_on_negative_valence(dummy_strategy) -> None:
    outputs = deque(
        [
            {
                "amm_pulse": 0.3,
                "amm_precision": 1.0,
                "amm_valence": 1.0,
                "pe": 0.01,
            },
            {
                "amm_pulse": 0.9,
                "amm_precision": 1.5,
                "amm_valence": -1.0,
                "pe": 0.05,
            },
        ]
    )
    strategy, _ = dummy_strategy(outputs)
    strategy.on_step(0.1, R_t=0.3, kappa_t=0.2)
    outcome = strategy.on_step(0.6, R_t=strategy.cfg.R_min + 0.2, kappa_t=0.4)

    assert outcome["action"] == "ENTER_SHORT"
    assert outcome["direction"] == -1
    assert outcome["size"] <= 0.0
