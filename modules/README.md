---
owner: docs@geosync
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# GeoSync Modules

Колекція автономних модулів, які можна використовувати окремо або разом у пайплайнах GeoSync.

## Огляд модулів

| Модуль | Призначення | Залежності |
| --- | --- | --- |
| `adaptive_risk_manager.py` (`AdaptiveRiskManager`) | Адаптивне управління ризиком: VaR/CVaR, ліміти позицій, контроль експозиції. | `numpy`, `pydantic` |
| `agent_coordinator.py` (`AgentCoordinator`) | Координація агентів, черги задач, пріоритети та залежності. | stdlib |
| `alert_manager.py` (`AlertManager`) | Централізовані алерти: критичність, канали доставки, дедуплікація. | stdlib |
| `backtest_report_generator.py` (`BacktestReportGenerator`) | Генерація звітів бектесту та метрик продуктивності. | `numpy`, `pandas` |
| `data_quality_monitor.py` (`DataQualityMonitor`) | Контроль якості даних: пропуски, аномалії, затримки. | `numpy`, `pandas` |
| `dynamic_position_sizer.py` (`DynamicPositionSizer`) | Розрахунок розміру позиції (Kelly, volatility-adjusted, adaptive). | `numpy` |
| `execution_analyzer.py` (`ExecutionAnalyzer`) | Аналіз якості виконання ордерів: slippage, latency, fill rate. | `numpy` |
| `gaba_inhibition_gate.py` (`GABAInhibitionGate`) | Нейронний гейт інгібування для ризик-адаптивних дій. | `torch` (опційно) |
| `market_regime_analyzer.py` (`MarketRegimeAnalyzer`) | Класифікація ринкового режиму та тренду. | `numpy` |
| `order_validator.py` (`OrderValidator`) | Валідація ордерів, ризикових і комплаєнс-правил. | stdlib |
| `performance_tracker.py` (`PerformanceTracker`) | Моніторинг PnL та метрик продуктивності в реальному часі. | `numpy`, `pandas` |
| `portfolio_optimizer.py` (`PortfolioOptimizer`) | Оптимізація портфеля (Markowitz, risk parity тощо). | `numpy`, `pandas` |
| `signal_strategy_registry.py` (`SignalStrategyRegistry`) | Реєстр торгових стратегій, перевірка параметрів і сумісності. | `numpy`, `pandas` |
| `strategy_scheduler.py` (`StrategyScheduler`) | Планування запуску стратегій, керування залежностями. | stdlib |
| `system_health_dashboard.py` (`SystemHealthDashboard`) | Агрегація стану системи та health-checks. | stdlib |

## Вимоги та залежності

- Python 3.10+
- Базові залежності для прикладів: `numpy`, `pydantic`
- Модулі, що потребують `pandas`: `backtest_report_generator`, `data_quality_monitor`,
  `performance_tracker`, `portfolio_optimizer`, `signal_strategy_registry`
- Модуль, що потребує `torch`: `gaba_inhibition_gate` (імпортується опційно, якщо `torch` доступний)

Встановлення мінімальних залежностей:

```bash
python -m venv .venv
source .venv/bin/activate
pip install numpy pydantic
```

Додаткові залежності (за потреби):

```bash
pip install pandas
pip install torch
```

## Standard market_state формат

Всі модулі, що працюють з ринковими даними, приймають єдиний формат
`market_state`. Нижче наведено основні ключі, типи та одиниці:

| Ключ | Тип | Одиниці | Потрібно для |
| --- | --- | --- | --- |
| `symbol` | `str` | - | `AdaptiveRiskManager` |
| `timestamp` | `datetime` | ISO 8601 | Рекомендовано для трекінгу |
| `price` | `float` | quote currency | `AdaptiveRiskManager` |
| `prices` | `np.ndarray` | price series | `MarketRegimeAnalyzer` |
| `returns` | `np.ndarray` | decimal per bar | `AdaptiveRiskManager`, `MarketRegimeAnalyzer` |
| `volatility` | `float` | std dev per bar | `AdaptiveRiskManager` |
| `return` | `float` | decimal | `GABAInhibitionGate` |
| `vix` | `float` | index points | `GABAInhibitionGate` |
| `position` | `float` | base units | `GABAInhibitionGate` |
| `rpe` | `float` | unitless | `GABAInhibitionGate` |
| `delta_t_ms` | `float` | milliseconds | `GABAInhibitionGate` |
| `market_data_latency_ms` | `float` | milliseconds | `ExecutionAnalyzer` (опційно) |

> Якщо `returns` або `volatility` не передані, деякі модулі можуть
> обчислювати їх автоматично, але для стабільної роботи краще
> надавати повний набір.

## Приклад використання (на основі `modules/demo.py`)

```python
import numpy as np
from datetime import datetime

from modules import AdaptiveRiskManager, DynamicPositionSizer, MarketRegimeAnalyzer
from modules.agent_coordinator import AgentCoordinator, AgentType, Priority

prices = 100 + np.cumsum(np.random.normal(0, 1.5, 180))
returns = np.diff(prices) / prices[:-1]
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
max_position = risk_manager.calculate_position_size(
    market_state, confidence=0.7
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
print(regime_metrics, risk_metrics, position_limit, max_position, processed_tasks)
```

Щоб запустити повний сценарій:

```bash
python -m modules.demo
```

## Мінімальні конфігураційні приклади

Нижче наведені стартові конфігурації для ключових модулів.

```python
from modules import AdaptiveRiskManager, DynamicPositionSizer, MarketRegimeAnalyzer
from modules.agent_coordinator import AgentCoordinator

risk_manager = AdaptiveRiskManager(
    base_capital=1_000_000,
    risk_tolerance=0.02,
    var_window=252,
    volatility_window=20,
)

regime_analyzer = MarketRegimeAnalyzer(
    regime_window=100,
    transition_threshold=0.7,
)

position_sizer = DynamicPositionSizer(
    base_capital=1_000_000,
    kelly_fraction=0.25,
    max_position_pct=0.1,
    min_position_pct=0.01,
    volatility_target=0.15,
)

coordinator = AgentCoordinator(
    max_concurrent_tasks=2,
    enable_conflict_resolution=True,
)
```

Опційно для GABA gate (потрібен `torch`):

```python
from modules.gaba_inhibition_gate import GateParams

params = GateParams(dt_ms=0.5, risk_min=0.6, risk_max=1.4)
```

## Validation checklist

Запустіть мінімальні перевірки після змін у модулях:

- `python -m modules.demo`
- `pytest tests/unit -m "not slow"`
- `make lint`
