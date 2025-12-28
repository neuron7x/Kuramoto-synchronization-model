"""Demo сценарій для модулів TradePulse.

Запускайте: ``python -m modules.demo``
"""

from __future__ import annotations

from importlib.util import find_spec
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

    regime_analyzer = MarketRegimeAnalyzer()
    regime_metrics = regime_analyzer.classify_regime(prices, returns)

    risk_manager = AdaptiveRiskManager(base_capital=1_000_000, risk_tolerance=0.02)
    risk_metrics = risk_manager.calculate_risk_metrics(returns)
    position_limit = risk_manager.update_position_limits("BTC-USD", volatility)
    max_position = risk_manager.calculate_position_size(
        "BTC-USD", price=float(prices[-1]), volatility=volatility, confidence=0.7
    )

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

    print("\n=== GABA inhibition gate (optional) ===")
    if find_spec("torch") is None:
        print("Torch не встановлено, GABA-модуль пропущено.")
        return

    import torch

    from modules.gaba_inhibition_gate import GABAInhibitionGate

    gate = GABAInhibitionGate(device="cpu")
    market_state = {
        "vix": torch.tensor(28.0),
        "vol": torch.tensor(0.35),
        "ret": torch.tensor(0.02),
        "pos": torch.tensor(0.8),
        "rpe": torch.tensor(0.15),
        "delta_t_ms": torch.tensor(25.0),
    }
    action = torch.tensor([1.0])

    gated_action, metrics = gate(market_state, action)
    print(f"Gated action: {gated_action.item():.4f}")
    pprint(metrics.__dict__)


if __name__ == "__main__":
    main()
