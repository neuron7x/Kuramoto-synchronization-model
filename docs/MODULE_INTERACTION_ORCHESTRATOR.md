# Module Interaction Orchestrator

## Огляд

`ModuleInteractionOrchestrator` — це централізований механізм для керування послідовністю взаємодій між модулями TradePulse. Він забезпечує правильний порядок виконання модулів на основі їх залежностей та фаз, надаючи уніфікований спосіб координації роботи всього пайплайну.

## Overview

The `ModuleInteractionOrchestrator` is a centralized mechanism for managing the sequence of interactions between TradePulse modules. It ensures correct execution order based on dependencies and phases, providing a unified way to coordinate the entire pipeline.

## Основні можливості / Key Features

### 1. Управління залежностями / Dependency Management
Автоматичне впорядкування модулів на основі їх залежностей, забезпечуючи виконання в правильній послідовності.

Automatically orders modules based on their dependencies, ensuring execution in the correct sequence.

### 2. Фазове виконання / Phase-Based Execution
Організація модулів за логічними фазами:
- `INGESTION` — завантаження даних
- `VALIDATION` — перевірка якості даних
- `FEATURE_ENGINEERING` — створення ознак
- `SIGNAL_GENERATION` — генерація сигналів
- `NEUROMODULATION` — нейромодуляційний контроль
- `RISK_ASSESSMENT` — оцінка ризиків
- `EXECUTION` — виконання торгів
- `POST_EXECUTION` — пост-обробка

### 3. Динамічне керування / Dynamic Control
Можливість динамічно вмикати/вимикати модулі без зміни конфігурації.

Ability to dynamically enable/disable modules without configuration changes.

### 4. Контекст виконання / Execution Context
Єдиний контекст для обміну даними між модулями з відстеженням помилок.

Unified context for data exchange between modules with error tracking.

## Використання / Usage

### Базовий приклад / Basic Example

```python
from core.orchestrator import (
    ModuleInteractionOrchestrator,
    ModuleDefinition,
    ModulePhase,
)

# Створення оркестратора / Create orchestrator
orchestrator = ModuleInteractionOrchestrator()

# Визначення обробника модуля / Define module handler
def ingest_data(context_data):
    """Завантажити ринкові дані / Load market data."""
    return {"raw_data": load_market_data()}

def validate_data(context_data):
    """Перевірити якість даних / Validate data quality."""
    raw_data = context_data.get("raw_data")
    # Validation logic...
    return {"validated_data": raw_data}

# Реєстрація модулів / Register modules
orchestrator.register_module(
    ModuleDefinition(
        name="data_ingestor",
        phase=ModulePhase.INGESTION,
        handler=ingest_data,
        priority=1,
    )
)

orchestrator.register_module(
    ModuleDefinition(
        name="data_validator",
        phase=ModulePhase.VALIDATION,
        handler=validate_data,
        dependencies=["data_ingestor"],
        priority=1,
    )
)

# Виконання пайплайну / Execute pipeline
context = orchestrator.execute()

# Отримання результатів / Get results
validated_data = context.get("validated_data")
```

### Складні залежності / Complex Dependencies

```python
# Модуль A є залежністю для B і C
# Module A is a dependency for both B and C
orchestrator.register_module(
    ModuleDefinition(name="A", phase=ModulePhase.INGESTION, handler=handler_a)
)

orchestrator.register_module(
    ModuleDefinition(
        name="B",
        phase=ModulePhase.FEATURE_ENGINEERING,
        handler=handler_b,
        dependencies=["A"],
    )
)

orchestrator.register_module(
    ModuleDefinition(
        name="C",
        phase=ModulePhase.FEATURE_ENGINEERING,
        handler=handler_c,
        dependencies=["A"],
    )
)

# Модуль D залежить від B і C
# Module D depends on both B and C
orchestrator.register_module(
    ModuleDefinition(
        name="D",
        phase=ModulePhase.SIGNAL_GENERATION,
        handler=handler_d,
        dependencies=["B", "C"],
    )
)
```

### Динамічне керування модулями / Dynamic Module Control

```python
# Вимкнення модуля / Disable module
orchestrator.disable_module("advanced_signal")

# Увімкнення модуля / Enable module
orchestrator.enable_module("advanced_signal")

# Видалення модуля / Remove module
orchestrator.remove_module("unused_module")

# Отримання модулів за фазою / Get modules by phase
ingestion_modules = orchestrator.list_modules_by_phase(ModulePhase.INGESTION)
```

## Інтеграція з TradePulse / Integration with TradePulse

Оркестратор інтегрується з існуючою системою TradePulse для керування повним циклом торгівлі:

The orchestrator integrates with the existing TradePulse system to manage the full trading cycle:

```python
from application.system_orchestrator import TradePulseOrchestrator, build_tradepulse_system
from core.orchestrator import ModuleInteractionOrchestrator, ModuleDefinition, ModulePhase

# Створення системи TradePulse / Create TradePulse system
system = build_tradepulse_system()
tp_orchestrator = TradePulseOrchestrator(system)

# Створення оркестратора взаємодій / Create interaction orchestrator
module_orchestrator = ModuleInteractionOrchestrator()

# Визначення модулів пайплайну / Define pipeline modules
def ingestion_module(context_data):
    source = context_data.get("data_source")
    market_data = tp_orchestrator.ingest_market_data(source)
    return {"market_data": market_data}

def feature_module(context_data):
    market_data = context_data.get("market_data")
    features = tp_orchestrator.build_features(market_data)
    return {"features": features}

def signal_module(context_data):
    source = context_data.get("data_source")
    strategy = context_data.get("strategy")
    run = tp_orchestrator.run_strategy(source, strategy)
    return {"strategy_run": run}

# Реєстрація модулів / Register modules
module_orchestrator.register_module(
    ModuleDefinition(
        name="ingestion",
        phase=ModulePhase.INGESTION,
        handler=ingestion_module,
    )
)

module_orchestrator.register_module(
    ModuleDefinition(
        name="features",
        phase=ModulePhase.FEATURE_ENGINEERING,
        handler=feature_module,
        dependencies=["ingestion"],
    )
)

module_orchestrator.register_module(
    ModuleDefinition(
        name="signals",
        phase=ModulePhase.SIGNAL_GENERATION,
        handler=signal_module,
        dependencies=["features"],
    )
)

# Виконання / Execute
initial_context = ExecutionContext()
initial_context.set("data_source", market_data_source)
initial_context.set("strategy", trading_strategy)

result = module_orchestrator.execute(initial_context)
```

## Обробка помилок / Error Handling

Оркестратор забезпечує надійну обробку помилок:

The orchestrator provides robust error handling:

```python
context = orchestrator.execute()

if context.has_error():
    print("Errors occurred:")
    for error in context.errors:
        print(f"  - {error}")
    
    # Отримати модулі, які було виконано до помилки
    # Get modules that were executed before error
    executed = context.metadata.get("modules_executed", [])
    print(f"Successfully executed: {executed}")
else:
    print("All modules executed successfully")
    # Process results...
```

## Моніторинг та діагностика / Monitoring and Diagnostics

```python
# Отримати порядок виконання / Get execution order
sequence = orchestrator.get_sequence()
print(f"Execution order: {sequence}")

# Отримати інформацію про модуль / Get module info
module_info = orchestrator.get_module_info("data_ingestor")
print(f"Module: {module_info.name}")
print(f"Phase: {module_info.phase}")
print(f"Dependencies: {module_info.dependencies}")
print(f"Enabled: {module_info.enabled}")

# Список всіх модулів / List all modules
all_modules = orchestrator.list_modules()

# Список модулів за фазою / List modules by phase
for phase in ModulePhase:
    modules = orchestrator.list_modules_by_phase(phase)
    if modules:
        print(f"{phase.value}: {', '.join(modules)}")
```

## Архітектурні рішення / Architectural Decisions

### 1. Топологічне сортування / Topological Sorting
Використовується алгоритм Кана для виявлення циклічних залежностей та впорядкування модулів.

Uses Kahn's algorithm to detect circular dependencies and order modules.

### 2. Пріоритети / Priorities
Модулі в межах однієї фази можуть мати різні пріоритети для контролю порядку виконання.

Modules within the same phase can have different priorities to control execution order.

### 3. Ізоляція стану / State Isolation
Кожен модуль отримує контекст і повертає нові дані, не змінюючи стан інших модулів.

Each module receives context and returns new data without modifying state of other modules.

### 4. Зупинка при помилках / Stop on Error
Виконання зупиняється при першій помилці, зберігаючи частково зібрані дані.

Execution stops at the first error, preserving partially collected data.

## Приклади використання / Use Cases

### 1. Торгівельний пайплайн / Trading Pipeline
Координація послідовності: завантаження → валідація → ознаки → сигнали → ризики → виконання.

Coordinate sequence: ingestion → validation → features → signals → risk → execution.

### 2. Експерименти з модулями / Module Experimentation
Швидке тестування різних комбінацій модулів та їх конфігурацій.

Quickly test different module combinations and configurations.

### 3. A/B тестування / A/B Testing
Динамічне перемикання між різними реалізаціями модулів.

Dynamically switch between different module implementations.

### 4. Поступове розгортання / Gradual Rollout
Поступове вмикання нових модулів з можливістю швидкого відкату.

Gradually enable new modules with quick rollback capability.

## Тестування / Testing

Запустити тести: / Run tests:

```bash
python -m pytest tests/core/orchestrator/test_interaction_sequencer.py -v
```

Запустити демо: / Run demo:

```bash
python examples/module_interaction_orchestrator_demo.py
```

## Продуктивність / Performance

- **Побудова послідовності**: O(V + E), де V — кількість модулів, E — кількість залежностей
- **Виконання**: O(V), лінійний час відносно кількості модулів
- **Пам'ять**: O(V + E) для зберігання графа залежностей

- **Sequence building**: O(V + E), where V is number of modules, E is number of dependencies
- **Execution**: O(V), linear time relative to module count
- **Memory**: O(V + E) to store dependency graph

## Обмеження / Limitations

1. **Циклічні залежності**: Не підтримуються, викликають ValueError
2. **Паралельне виконання**: Поточна реалізація виконує модулі послідовно
3. **Стан між запусками**: Не зберігається між різними викликами `execute()`

1. **Circular dependencies**: Not supported, raises ValueError
2. **Parallel execution**: Current implementation executes modules sequentially
3. **State between runs**: Not preserved between different `execute()` calls

## Майбутні покращення / Future Enhancements

1. Паралельне виконання модулів без залежностей / Parallel execution of independent modules
2. Асинхронна підтримка / Async support
3. Метрики продуктивності модулів / Module performance metrics
4. Візуалізація графа залежностей / Dependency graph visualization
5. Механізм відкату / Rollback mechanism

## Див. також / See Also

- [TradePulseOrchestrator](../application/system_orchestrator.py) — Головний оркестратор системи
- [ModeOrchestrator](../core/orchestrator/mode_orchestrator.py) — Керування режимами торгівлі
- [StrategyOrchestrator](../core/agent/orchestrator.py) — Координація паралельних стратегій
- [Conceptual Architecture](./architecture/CONCEPTUAL_ARCHITECTURE.md) — Архітектура системи
