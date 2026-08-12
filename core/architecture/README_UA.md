# Архітектурні Принципи Системи GeoSync

## Огляд

Цей модуль визначає сім ключових архітектурних принципів, які керують проектуванням та реалізацією торгової системи GeoSync. Кожен принцип забезпечує важливі властивості системи та має конкретну реалізацію.

## Сім Архітектурних Принципів

### 1. Нейроорієнтована (Neuro-oriented)

**Опис:** Використання нейронаукових обчислювальних моделей для прийняття рішень та навчання.

**Ключові компоненти:**
- **Дофамінова система** - TD-learning для підкріплювального навчання
- **Серотонінова система** - Управління ризиками та стресом
- **Базальні ганглії** - Вибір дій через Go/No-Go шляхи
- **GABA/NA-ACh** - Інгібіція імпульсів та контроль уваги

**Приклад використання:**
```python
from core.architecture import NeuroOrientedPrinciple

principle = NeuroOrientedPrinciple()
context = {
    "neuromodulators": ["dopamine", "serotonin", "gaba", "na_ach"],
    "components": ["basal_ganglia_selector", "dopamine_learning_loop"],
    "learning_loop": {"algorithm": "TD(0)"}
}
violations = principle.validate(context)
```

---

### 2. Модульна (Modular)

**Опис:** Незалежні, слабко пов'язані компоненти з чіткими інтерфейсами.

**Характеристики:**
- Максимальний показник зв'язності (coupling): 0.3
- Мінімальний показник згуртованості (cohesion): 0.7
- Заборона циклічних залежностей

**Переваги:**
- Горизонтальне масштабування
- Незалежне розгортання
- Ізольоване тестування

---

### 3. Рольова (Role-based)

**Опис:** Чітке розділення відповідальностей та контроль доступу на основі ролей.

**Ролі компонентів:**
| Роль | Опис | Дозволи |
|------|------|---------|
| SENSOR | Збір даних | read_market_data, emit_events |
| PROCESSOR | Обробка сигналів | process_signals, emit_events |
| ACTUATOR | Виконання дій | execute_orders, emit_events |
| COORDINATOR | Координація | orchestrate, read_all, configure |
| MONITOR | Моніторинг | read_all, emit_alerts |
| GUARDIAN | Безпека | veto_actions, halt_system |

---

### 4. Інтегративна (Integrative)

**Опис:** Безшовна інтеграція компонентів та уніфіковані потоки даних.

**Контракти інтеграції:**
```python
from core.architecture import IntegrationContract

contract = IntegrationContract(
    source="data_ingestion",
    target="feature_extraction",
    data_schema="ohlcv_v1",
    protocol="stream",
    version="1.0.0"
)
```

**Обов'язкові інтеграції:**
- data_ingestion → feature_extraction
- feature_extraction → risk_assessment
- risk_assessment → action_selector
- action_selector → execution
- execution → monitoring

---

### 5. Відтворювана (Reproducible)

**Опис:** Детерміністична поведінка та повний аудит стану системи.

**Механізми:**
- **Знімки стану (StateSnapshot)** - Збереження повного стану системи
- **Зерна випадковості** - Контрольована стохастичність
- **Версіонування конфігурації** - Відстеження змін
- **Контрольні суми** - Верифікація цілісності

**Приклад:**
```python
from core.architecture import ReproduciblePrinciple

principle = ReproduciblePrinciple()
snapshot = principle.create_snapshot(
    component_states={"strategy": {"position": 0}},
    random_seeds={"rng": 42},
    configuration={"risk_limit": 0.02}
)
print(f"Checksum: {snapshot.checksum}")
```

---

### 6. Контрольована (Controllable)

**Опис:** Повний операційний контроль та можливість втручання.

**Механізми контролю:**
- **Kill Switch** - Аварійна зупинка системи
- **Circuit Breakers** - Автоматичне переривання при аномаліях
- **Рівні схвалення** - Ієрархічний контроль дій

**Рівні дозволів:**
| Рівень | Дії |
|--------|-----|
| 0 | Спостереження |
| 1 | Конфігурація |
| 2 | Перевизначення |
| 3 | Зупинка системи |

---

### 7. Автономна (Autonomous)

**Опис:** Саморегулювання та адаптивна поведінка системи.

**Рівні автономії:**
| Рівень | Назва | Опис |
|--------|-------|------|
| 0 | MANUAL | Повністю ручне управління |
| 1 | ASSISTED | Рекомендації без автоматичного виконання |
| 2 | SUPERVISED | Автоматичне виконання з людським наглядом |
| 3 | AUTONOMOUS | Повна автономія для рутинних операцій |

**Можливості:**
- Автоматичне відновлення після збоїв
- Адаптація до ринкових умов
- Самоналаштування параметрів

---

## Використання SystemArchitecture

```python
from core.architecture import SystemArchitecture, get_system_architecture

# Отримати синглтон архітектури
arch = get_system_architecture()

# Валідація всіх принципів
context = {
    "neuromodulators": ["dopamine", "serotonin", "gaba", "na_ach"],
    "components": ["basal_ganglia_selector"],
    "coupling_score": 0.2,
    "kill_switch_available": True,
    # ... інші параметри
}
violations = arch.validate_all(context)

# Вивести порушення
for principle_name, principle_violations in violations.items():
    for v in principle_violations:
        print(f"[{v.severity}] {principle_name}: {v.description}")

# Отримати підсумок
summary = arch.get_summary()
print(arch.to_json())
```

## Інтеграція з TACL

Архітектурні принципи інтегруються з Thermodynamic Autonomic Control Layer (TACL):

- **Контрольована** принцип забезпечує дотримання монотонного спадання вільної енергії
- **Автономна** принцип визначає рівні автоматичного втручання
- **Відтворювана** принцип гарантує аудит всіх змін топології

## Структура Файлів

```
core/architecture/
├── __init__.py              # Експорт публічного API
├── system_principles.py     # Реалізація принципів
└── README_UA.md             # Ця документація
```

## Зв'язок з Іншими Компонентами

```
┌─────────────────────────────────────────────────────────────┐
│                  SYSTEM ARCHITECTURE                         │
│    (Neuro | Modular | Role | Integrative | Reproducible     │
│           | Controllable | Autonomous)                       │
└─────────────────────────────────────────────────────────────┘
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│    TACL       │    │  Neuro        │    │   Runtime     │
│ (Free Energy) │    │ Orchestrator  │    │  Controller   │
└───────────────┘    └───────────────┘    └───────────────┘
```

## Ліцензія

MIT License
