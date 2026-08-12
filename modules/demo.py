# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Demo сценарій для модулів GeoSync.

Запускайте: ``python -m modules.demo``
"""

from __future__ import annotations

from datetime import datetime
from pprint import pprint

import numpy as np

from modules import AdaptiveRiskManager, DynamicPositionSizer, MarketRegimeAnalyzer
from modules.agent_coordinator import AgentCoordinator, AgentType, Priority


def generate_sample_series(length: int = 180) -> tuple[np.ndarray, np.ndarray]:
    """Генерує синтетичний ряд цін та повернень для демонстрації."""
    rng = np.random.default_rng(seed=42)
    price_changes = rng.normal(0, 1.5, size=length)
    prices = 100 + np.cumsum(price_changes)
    returns = np.diff(prices) / prices[:-1]
    return prices, returns


def main() -> None:
    prices, returns = generate_sample_series()
    volatility = returns.std(ddof=1)
    market_state = {
        "symbol": "BTC-USD",
        "timestamp": datetime.now(),
        "price": float(prices[-1]),
        "prices": prices,
        "returns": returns,
        "volatility": float(volatility),
    }

    regime_analyzer = MarketRegimeAnalyzer()
    regime_metrics = regime_analyzer.classify_regime(market_state)

    risk_manager = AdaptiveRiskManager(base_capital=1_000_000, risk_tolerance=0.02)
    risk_metrics = risk_manager.calculate_risk_metrics(market_state)
    position_limit = risk_manager.update_position_limits(market_state)
    max_position = risk_manager.calculate_position_size(market_state, confidence=0.7)

    position_sizer = DynamicPositionSizer(base_capital=1_000_000)
    sizing_result = position_sizer.calculate_adaptive_size(
        symbol="BTC-USD",
        price=float(prices[-1]),
        volatility=volatility,
        confidence=0.7,
        win_rate=0.55,
        avg_win=0.02,
        avg_loss=0.01,
    )

    coordinator = AgentCoordinator(max_concurrent_tasks=2)
    coordinator.register_agent(
        "risk",
        AgentType.RISK_MANAGER,
        "Risk Manager",
        "Адаптивний ризик-менеджер",
        handler=risk_manager,
        capabilities={"limits", "monitoring"},
    )
    coordinator.register_agent(
        "trader",
        AgentType.TRADING,
        "Trading Agent",
        "Виконує заявки на біржі",
        handler=lambda task: {"status": "ok", "payload": task.payload},
        capabilities={"execute", "hedge"},
        dependencies={"risk"},
    )

    coordinator.submit_task(
        agent_id="risk",
        task_type="rebalance_limits",
        payload={"symbol": "BTC-USD", "volatility": volatility},
        priority=Priority.HIGH,
    )
    coordinator.submit_task(
        agent_id="trader",
        task_type="open_position",
        payload={
            "symbol": "BTC-USD",
            "size": float(sizing_result.recommended_size),
            "price": float(prices[-1]),
        },
    )

    processed_tasks = coordinator.process_tasks()

    print("\n=== Market regime ===")
    pprint(regime_metrics.__dict__)

    print("\n=== Risk metrics ===")
    pprint(risk_metrics.__dict__)

    print("\n=== Position limit ===")
    print(position_limit.model_dump())
    print(f"Max position (confidence-adjusted): {max_position:,.2f}")

    print("\n=== Sizing result ===")
    pprint(sizing_result.__dict__)

    print("\n=== Agent coordinator ===")
    print("Processed tasks:", processed_tasks)
    pprint(coordinator.get_system_health())


if __name__ == "__main__":
    main()
