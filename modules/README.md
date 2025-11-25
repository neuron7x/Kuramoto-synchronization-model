# TradePulse Modules

Колекція автономних модулів, які можна використовувати окремо або разом:

- **AdaptiveRiskManager** — динамічні ліміти, VaR/CVaR та моніторинг портфеля.
- **MarketRegimeAnalyzer** — класифікація ринкового режиму на основі цін/волатильності.
- **DynamicPositionSizer** — розрахунок розміру позиції з урахуванням Kelly, волатильності та впевненості сигналу.
- **AgentCoordinator** — черга задач і базова координація між агентами/сервісами.

## Вимоги

- Python 3.10+
- Обов'язкові залежності для прикладів: `numpy`, `pydantic`
- Опціонально: `torch` (для `GABAInhibitionGate`, пропускається автоматично)

Встановлення мінімальних залежностей:

```bash
python -m venv .venv
source .venv/bin/activate
pip install numpy pydantic
```

## Швидкий старт

Запустіть демонстраційний сценарій, який проходить весь ланцюжок: оцінка режиму ринку →
розрахунок ризику → рекомендації з розміру позиції → диспетчеризація задач агентами.

```bash
python -m modules.demo
```

Вивід міститиме:

- Короткий опис режиму ринку та волатильності.
- VaR/CVaR, Sharpe, drawdown та рекомендовані ліміти для інструмента.
- Рекомендований розмір позиції (адаптивний розрахунок).
- Список оброблених задач та ключові метрики здоров'я координатора.

## Як використовувати окремі модулі

Нижче наведено мінімальний приклад для кожного основного модуля.

```python
import numpy as np
from modules import AdaptiveRiskManager, DynamicPositionSizer, MarketRegimeAnalyzer
from modules.agent_coordinator import AgentCoordinator, AgentType

prices = 100 + np.cumsum(np.random.normal(0, 1, 120))
returns = np.diff(prices) / prices[:-1]
volatility = returns.std(ddof=1)

regime_analyzer = MarketRegimeAnalyzer()
regime = regime_analyzer.classify_regime(prices, returns)

risk_manager = AdaptiveRiskManager(base_capital=1_000_000)
risk_metrics = risk_manager.calculate_risk_metrics(returns)
limit = risk_manager.update_position_limits("BTC", volatility)

sizer = DynamicPositionSizer(base_capital=1_000_000)
position = sizer.calculate_adaptive_size("BTC", prices[-1], volatility, confidence=0.7)

coordinator = AgentCoordinator()
coordinator.register_agent("risk", AgentType.RISK_MANAGER, "Risk", "Risk engine", handler=risk_manager)
```

Використовуйте ці блоки як стартову точку та розширюйте під свої потреби.
