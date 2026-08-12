# Independent Models Split Plan

Цей документ формалізує розділення монорепозиторію на окремі моделі, які можуть
існувати, тестуватися та пакуватися незалежно одна від одної.

## Ціль

Виділити модулі з власним доменом, публічним API, локальними залежностями та
окремим `pyproject.toml`, щоб кожен з них можна було:

- інсталювати окремо;
- тестувати окремо;
- версіонувати окремо;
- переносити в окремий репозиторій без масової переробки коду.

## Незалежні моделі

| Модель | Каталог | Standalone package | Призначення |
| --- | --- | --- | --- |
| FPMA | `analytics/fpma/` | `geosync-fpma` | Фрактальна фазово-режимна модель для allocation/regime-aware portfolio logic. |
| Regime | `analytics/regime/` | `geosync-regime` | Багатовимірний аналіз режимів ринку, EWS і consensus routing. |
| Order Book | `markets/orderbook/` | `geosync-orderbook` | Симуляція LOB, інжест снапшотів/діфів і мікроструктурні події. |
| NaK Controller | `nak_controller/` | `geosync-nak` | Нейроенергетичний лімітер для risk/exposure/frequency control. |
| GeoSync Pro | `geosync_pro/` | `geosync-pro` | EMH-inspired state-space controller з EKF, MPC і CVaR gate. |

## Правила меж

### 1. FPMA
- Залежить лише від власного `src/` та числового стеку.
- Публічний standalone API експортується через `geosync_fpma`.
- Для відокремлення не потребує решти торгового контуру.

### 2. Regime
- Ядро (`src/core`) є самодостатнім.
- Consensus layer лишається опційним інтеграційним контуром.
- Standalone API експортується через `geosync_regime`.

### 3. Order Book
- Має повністю локальне ядро `src/core` та локальний ingest у `src/ingest`.
- Standalone API експортується через `geosync_orderbook`.
- Може служити окремим сервісом симуляції або тестовим harness для execution.

### 4. NaK Controller
- Уже мав локальний `pyproject.toml` і майже повну автономність.
- Залишається окремою моделлю контролю, яку можна підключати через hook.

### 5. GeoSync Pro
- Має завершений внутрішній цикл: модель → оцінювання → policy → risk → validate.
- Додано локальний `pyproject.toml` для повністю автономного пакування.

## Практичний workflow

### Локальна інсталяція окремої моделі

```bash
cd analytics/regime && python -m pip install -e .[test]
cd analytics/fpma && python -m pip install -e .[test]
cd markets/orderbook && python -m pip install -e .[test]
cd nak_controller && python -m pip install -e .
cd geosync_pro && python -m pip install -e .[test]
```

### Критерії “справді незалежної” моделі

Модель вважається відокремленою, якщо:

1. має власний `pyproject.toml`;
2. має власний README з public surface;
3. її публічний API не вимагає імпорту з кореня монорепозиторію;
4. її тести можна запускати з каталогу моделі;
5. перенесення в окремий git-репозиторій не вимагає переписувати доменне ядро.

## Що залишилось спільним

- загальна документація репозиторію;
- інтеграційні шари, які поєднують моделі між собою;
- монорепозиторний CI/CD;
- крос-модульні end-to-end сценарії.

## Наступний крок

Після цього розділення можна безболісно переходити до другого етапу:

1. винести кожну модель у власний репозиторій;
2. налаштувати окремий semantic versioning;
3. підключати моделі назад як залежності, а не як локальні каталоги.
