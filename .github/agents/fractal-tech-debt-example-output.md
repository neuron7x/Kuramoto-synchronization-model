# Fractal Tech Debt Engine v2.0 - Example Output

This document shows example outputs from the Fractal Tech Debt Engine v2.0 agent for different scenarios.

## Example 1: TECH_DEBT_REPORT Format

### Scenario: Trading Strategy with Complexity Issues

**Input:** PR adding a new momentum trading strategy with complex nested logic.

**Output:**

```
TECH_DEBT_REPORT:

* Scope: PR / Module: core/strategies / File: momentum_v2.py

* Summary:
  New momentum trading strategy introduced with signal calculation logic.
  Contains complexity and observability debt in core trading path.
  Changes affect risk calculation domain.

* Findings:

  * [L4][COMPLEXITY_DEBT][HIGH]: Function `calculate_momentum_signal()` має цикломатичну складність 18 (ліміт: 10)
    - Глибоко вкладена логіка з 4 рівнями if-else
    - Змішування розрахунку сигналу з risk-checks
    - Наслідки: Складність тестування, ризик помилок у торговій логіці, утруднене дебагінг

  * [L4][OBSERVABILITY_DEBT][HIGH]: Відсутність логування в критичних точках розрахунку сигналу
    - Немає логів для входу/виходу з функції
    - Немає логування проміжних результатів розрахунку
    - Немає метрик для latency та error-rates
    - Наслідки: Неможливо діагностувати проблеми в продакшн, відсутність спостережуваності

  * [L3][DESIGN_DEBT][MEDIUM]: Клас `MomentumStrategy` порушує Single Responsibility
    - Змішує логіку розрахунку сигналу, risk management та execution
    - Розмір класу: 450 рядків (рекомендовано: <200)
    - Наслідки: Складність підтримки, тестування та переконфігурації

  * [L2][TESTING_DEBT][HIGH]: Недостатнє покриття тестами фінансових інваріантів
    - Відсутні тести для граничних кейсів (нульові ціни, розриви даних)
    - Немає property-based тестів для інваріантів PnL
    - Немає тестів для backtest-results stability
    - Наслідки: Ризик регресій у фінансових результатах

* SuggestedChanges:

  * Change 1:

    * Target: L4 / core/strategies/momentum_v2.py / lines 45-98

    * Rationale:
      Зменшити цикломатичну складність через екстракцію sub-функцій.
      Захищає інваріант: читабельність та тестованість торгової логіки.

    * Patch:
```python
# BEFORE (complexity: 18)
def calculate_momentum_signal(self, prices: pd.DataFrame, volume: pd.DataFrame) -> float:
    if len(prices) < self.lookback_period:
        if self.strict_mode:
            raise ValueError("Insufficient data")
        else:
            return 0.0

    momentum = prices.pct_change(self.lookback_period)

    if self.use_volume_filter:
        if volume.mean() < self.volume_threshold:
            if self.volume_mode == "strict":
                return 0.0
            else:
                momentum *= 0.5

    if self.risk_adjust:
        volatility = prices.std()
        if volatility > self.max_volatility:
            if self.risk_mode == "skip":
                return 0.0
            else:
                momentum /= volatility

    signal = np.tanh(momentum * self.signal_strength)

    if abs(signal) < self.min_signal_threshold:
        return 0.0

    return signal

# AFTER (complexity: 5)
def calculate_momentum_signal(self, prices: pd.DataFrame, volume: pd.DataFrame) -> float:
    """Calculate momentum signal with volume and risk adjustments."""
    # Extract sub-functions for clarity
    if not self._validate_data(prices):
        return 0.0

    momentum = self._calculate_base_momentum(prices)
    momentum = self._apply_volume_filter(momentum, volume)
    momentum = self._apply_risk_adjustment(momentum, prices)
    signal = self._normalize_signal(momentum)

    return signal if abs(signal) >= self.min_signal_threshold else 0.0

def _validate_data(self, prices: pd.DataFrame) -> bool:
    """Validate input data meets minimum requirements."""
    if len(prices) < self.lookback_period:
        if self.strict_mode:
            raise ValueError(f"Insufficient data: {len(prices)} < {self.lookback_period}")
        return False
    return True

def _calculate_base_momentum(self, prices: pd.DataFrame) -> float:
    """Calculate base momentum from price changes."""
    return prices.pct_change(self.lookback_period).iloc[-1]

def _apply_volume_filter(self, momentum: float, volume: pd.DataFrame) -> float:
    """Apply volume-based filtering to momentum signal."""
    if not self.use_volume_filter:
        return momentum

    avg_volume = volume.mean()
    if avg_volume < self.volume_threshold:
        return 0.0 if self.volume_mode == "strict" else momentum * 0.5

    return momentum

def _apply_risk_adjustment(self, momentum: float, prices: pd.DataFrame) -> float:
    """Apply risk-based adjustments to momentum signal."""
    if not self.risk_adjust:
        return momentum

    volatility = prices.std()
    if volatility > self.max_volatility:
        return 0.0 if self.risk_mode == "skip" else momentum / volatility

    return momentum

def _normalize_signal(self, momentum: float) -> float:
    """Normalize momentum to signal range [-1, 1]."""
    return np.tanh(momentum * self.signal_strength)
```

  * Change 2:

    * Target: L4 / core/strategies/momentum_v2.py / lines 45-150

    * Rationale:
      Додати структуроване логування для спостережуваності торгової логіки.
      Захищає інваріант: можливість діагностики та моніторингу в продакшн.

    * Patch:
```python
import logging
from observability.metrics import trading_metrics

logger = logging.getLogger(__name__)

def calculate_momentum_signal(self, prices: pd.DataFrame, volume: pd.DataFrame) -> float:
    """Calculate momentum signal with observability."""
    with trading_metrics.timer("momentum_signal_calculation"):
        logger.debug(
            "Calculating momentum signal",
            extra={
                "prices_len": len(prices),
                "lookback_period": self.lookback_period,
                "strict_mode": self.strict_mode,
            }
        )

        if not self._validate_data(prices):
            logger.warning("Data validation failed", extra={"prices_len": len(prices)})
            trading_metrics.increment("momentum_signal_validation_failed")
            return 0.0

        momentum = self._calculate_base_momentum(prices)
        logger.debug(f"Base momentum calculated: {momentum:.6f}")

        momentum = self._apply_volume_filter(momentum, volume)
        logger.debug(f"Volume-filtered momentum: {momentum:.6f}")

        momentum = self._apply_risk_adjustment(momentum, prices)
        logger.debug(f"Risk-adjusted momentum: {momentum:.6f}")

        signal = self._normalize_signal(momentum)

        logger.info(
            "Momentum signal generated",
            extra={
                "signal": signal,
                "base_momentum": momentum,
                "signal_strength": self.signal_strength,
            }
        )

        trading_metrics.histogram("momentum_signal_value", signal)

        return signal if abs(signal) >= self.min_signal_threshold else 0.0
```

  * Change 3:

    * Target: L3 / core/strategies/momentum_v2.py / full class

    * Rationale:
      Розділити клас на окремі компоненти (signal, risk, execution).
      Захищає інваріант: модульність та тестованість.
      Note: Це STANDARD-режимний рефакторинг. Для AGGRESSIVE режиму можна
      повністю реструктурувати на окремі модулі.

    * Patch:
```python
# Рекомендація: поступове розділення відповідальності
# Phase 1: Extract signal calculation to separate class
# Phase 2: Extract risk management to separate class
# Phase 3: Keep only orchestration in main strategy class

# План для follow-up PR
```

* Tests:

  * Required:
    - Unit тести для кожної з нових приватних методів (_validate_data, _calculate_base_momentum, etc.)
    - Property-based тести для інваріантів: signal range [-1, 1], monotonicity
    - Integration тести з mock market data для перевірки end-to-end логіки
    - Backtest stability тести: порівняння результатів до/після рефакторингу
    - Edge case тести: порожні дані, NaN values, extreme volatility

  * Existing:
    - tests/core/strategies/test_momentum.py (базові тести існують)
    - Потрібно розширити покриття з 65% до мінімум 90% для торгової логіки

* RiskAssessment:

  * RiskLevel: Medium

  * Notes:
    - Рефакторинг торгової логіки завжди несе ризик зміни поведінки
    - ОБОВ'ЯЗКОВО: порівняти backtest results до/після змін
    - ОБОВ'ЯЗКОВО: запустити forward-test на staging перед продакшн
    - Перевірити рев'юерам:
      * Чи збереглася логіка розрахунку momentum
      * Чи не змінилися граничні кейси (edge cases)
      * Чи логування не впливає на latency (критично для HFT)
    - Можливість rollback: висока (чисті зміни без міграцій)

* DecisionHint:

  * Рекомендація: **merge + follow-up**

  * Обґрунтування:
    - Change 1 (complexity reduction) можна мерджити після валідації тестами
    - Change 2 (observability) можна мерджити після перевірки performance overhead
    - Change 3 (class split) потребує окремого PR з детальним планом

  * Наступні кроки:
    1. Імплементувати Change 1 + Change 2 в поточному PR
    2. Додати тести (Required section)
    3. Запустити backtest comparison
    4. Створити follow-up issue для Change 3
    5. Після мерджу моніторити metrics в продакшн 7 днів

* OPTIONAL_IMPROVEMENTS:

  * Type hints для всіх методів (підвищить type safety)
  * Додати @dataclass для конфігурації стратегії
  * Розглянути використання numba/cython для оптимізації розрахунків
  * Додати documentation strings у numpy docstring format
```

## Example 2: GITHUB_REVIEW_COMMENTS Format

### Scenario: Quick inline comments for PR review

**Input:** Small PR with security and style issues.

**Output:**

```
GITHUB_REVIEW_COMMENTS:

* Comment 1:
  * File: core/data/fetcher.py
  * Line: 34
  * Body: |
    [SECURITY_DEBT][CRITICAL] SQL injection vulnerability

    Використання f-string для побудови SQL-запиту небезпечне.

    ```python
    # UNSAFE
    query = f"SELECT * FROM trades WHERE symbol = '{symbol}'"

    # SAFE
    query = "SELECT * FROM trades WHERE symbol = %s"
    cursor.execute(query, (symbol,))
    ```

* Comment 2:
  * File: core/risk/calculator.py
  * Line: 89
  * Body: |
    [COMPLEXITY_DEBT][MEDIUM] Висока цикломатична складність (15)

    Розглянути екстракцію логіки у окремі методи для покращення читабельності.

* Comment 3:
  * File: tests/core/test_risk.py
  * Line: 12
  * Body: |
    [TESTING_DEBT][HIGH] Відсутні тести для граничних кейсів

    Додати тести для:
    - Нульовий/негативний capital
    - Extreme leverage values
    - Empty portfolio

* Comment 4:
  * File: core/strategies/base.py
  * Line: 156
  * Body: |
    [OBSERVABILITY_DEBT][MEDIUM] Відсутнє логування перед execution

    Додати structured logging для execution decisions:
    ```python
    logger.info("Executing trade", extra={
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "signal_strength": signal
    })
    ```
```

## Example 3: PATCH_ONLY Format

### Scenario: Simple, focused fix request

**Input:** Quick fix needed for magic constant.

**Output:**

```
PATCH_ONLY:

```diff
diff --git a/core/risk/limits.py b/core/risk/limits.py
index abc123..def456 100644
--- a/core/risk/limits.py
+++ b/core/risk/limits.py
@@ -12,11 +12,16 @@ from typing import Dict

 logger = logging.getLogger(__name__)

+# Risk limits configuration
+MAX_POSITION_SIZE_RATIO = 0.1  # Maximum 10% of portfolio in single position
+MAX_LEVERAGE = 3.0  # Maximum 3x leverage allowed
+MIN_MARGIN_RATIO = 0.2  # Minimum 20% margin requirement
+
 class RiskLimits:
     def check_position_size(self, position_value: float, portfolio_value: float) -> bool:
-        # Magic constant 0.1 - should be configurable
-        if position_value / portfolio_value > 0.1:
-            logger.warning(f"Position size exceeds 10% limit")
+        ratio = position_value / portfolio_value
+        if ratio > MAX_POSITION_SIZE_RATIO:
+            logger.warning(f"Position size {ratio:.2%} exceeds limit {MAX_POSITION_SIZE_RATIO:.2%}")
             return False
         return True
```
```

## Example 4: Multi-Level Analysis

### Scenario: Comprehensive repository-level analysis

**Input:** Large PR touching multiple domains.

**Output:**

```
TECH_DEBT_REPORT:

* Scope: PR / Multiple modules (data, strategies, risk)

* Summary:
  Refactoring PR що торкається 3 доменів: data ingestion, strategy execution, risk management.
  Містить структурні покращення але також HIGH-пріоритетні проблеми безпеки та тестування.

* Findings:

  [L0: REPOSITORY]
  * [L0][DESIGN_DEBT][MEDIUM]: Порушення domain boundaries між data та strategies
    - Прямі імпорти між доменами замість через інтерфейси
    - Циклічні залежності: data → strategies → risk → data
    - Наслідки: Складність тестування ізольовано, tight coupling

  [L1: MODULE]
  * [L1][DESIGN_DEBT][MEDIUM]: Модуль data/pipeline має змішані відповідальності
    - Fetch, transform, validate, store в одному модулі
    - 8 файлів, 2500+ рядків
    - Наслідки: Складність розуміння потоків даних, утруднене розширення

  [L2: FILE]
  * [L2][SECURITY_DEBT][CRITICAL]: data/fetcher.py зберігає API keys у plain text
    - Hardcoded keys у constants
    - Немає encryption/secrets management
    - Наслідки: КРИТИЧНИЙ ризик витоку credentials

  * [L2][DATA_QUALITY_DEBT][HIGH]: Відсутня валідація схем даних
    - Немає pydantic/dataclass schemas
    - Немає перевірки типів на вході/виході
    - Наслідки: Ризик silent data corruption

  [L3: CLASS]
  * [L3][COMPLEXITY_DEBT][HIGH]: Клас DataPipeline має 15 методів, 600 рядків
    - God class anti-pattern
    - Змішує orchestration з business logic
    - Наслідки: Складність тестування та розширення

  [L4: FUNCTION]
  * [L4][PERFORMANCE_DEBT][MEDIUM]: Функція transform_ohlcv() має O(n²) складність
    - Nested loops для групування даних
    - Можна оптимізувати через pandas groupby
    - Наслідки: Latency на великих датасетах

* SuggestedChanges:
  [Due to space, showing priority order only]

  Priority 1 (CRITICAL): Fix security issue in data/fetcher.py
  Priority 2 (HIGH): Add data validation schemas
  Priority 3 (HIGH): Add tests for data transformation invariants
  Priority 4 (MEDIUM): Refactor DataPipeline class
  Priority 5 (MEDIUM): Optimize transform_ohlcv performance

* Tests: [abbreviated]

* RiskAssessment:
  * RiskLevel: High (due to CRITICAL security issue)
  * Notes: Block merge until security issue resolved

* DecisionHint: **block until fixed CRITICAL**
```

## Example 5: CONSERVATIVE Mode Output

### Scenario: Analysis of critical trading strategy

**Input:** Changes to live trading strategy with CONSERVATIVE mode.

**Output:**

```
TECH_DEBT_REPORT:

* Scope: PR / Module: strategies/live_trading / File: main_strategy.py

* Summary:
  Мінорні зміни у live trading strategy. Режим: CONSERVATIVE.
  Фокус на локальних покращеннях без структурних змін.

* Findings:

  * [L4][CODE_STYLE_DEBT][LOW]: Неконсистентне іменування змінних
    - pos_size vs position_size у різних методах
    - Наслідки: Мінімальні, але знижує читабельність

  * [L4][OBSERVABILITY_DEBT][MEDIUM]: Недостатньо логування для моніторингу
    - Відсутній лог перед execution critical paths
    - Наслідки: Утруднений debugging в продакшн

* SuggestedChanges:

  * Change 1:
    * Target: L4 / strategies/live_trading/main_strategy.py / lines 67-72
    * Rationale: Стандартизувати іменування без зміни логіки
    * Patch:
```python
# Rename for consistency (safe, no behavior change)
- pos_size = self.calculate_position()
+ position_size = self.calculate_position()
```

  * Change 2:
    * Target: L4 / strategies/live_trading/main_strategy.py / line 89
    * Rationale: Додати logging для observability
    * Patch:
```python
def execute_trade(self, signal):
+   logger.info("Executing trade", extra={"signal": signal, "timestamp": time.time()})
    # existing code...
```

* Tests:
  * Required: Regression тести для підтвердження збереження поведінки
  * Existing: tests/strategies/test_main_strategy.py (coverage: 85%)

* RiskAssessment:
  * RiskLevel: Low
  * Notes: Зміни мінімальні, поведінка не змінюється

* DecisionHint: **merge as is** (після тестів)

* OPTIONAL_IMPROVEMENTS:
  * Розгляньте більш глобальний рефакторинг у окремому PR (STANDARD/AGGRESSIVE режим)
  * Додайте structured logging framework для всіх strategies
```

---

## Notes on Output Formats

1. **TECH_DEBT_REPORT** - Use for comprehensive analysis
2. **GITHUB_REVIEW_COMMENTS** - Use for quick inline feedback
3. **PATCH_ONLY** - Use for simple, focused fixes

All outputs maintain:
- Ukrainian language for consistency with TradePulse team
- Technical accuracy and specificity
- Focus on trading/financial domain invariants
- Clear risk assessment and decision guidance
