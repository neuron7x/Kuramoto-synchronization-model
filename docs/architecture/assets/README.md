---
owner: docs@tradepulse
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# Архітектурні діаграми / Architecture Diagrams

Цей каталог містить вихідні файли Mermaid (`.mmd`) та згенеровані SVG діаграми для візуалізації архітектури TradePulse.

This directory contains Mermaid source files (`.mmd`) and generated SVG diagrams for TradePulse architecture visualization.

## Концептуальні діаграми / Conceptual Diagrams

### 1. Концептуальна карта системи / System Conceptual Map
- **Файл / File**: `conceptual_map.mmd` → `conceptual_map.svg`
- **Опис / Description**: Високорівнева візуалізація всіх концептуальних елементів системи та їхніх взаємозв'язків
- **Тип / Type**: Flowchart (graph TB)
- **Розділи / Sections**:
  - 🌐 Зовнішні джерела (External Sources)
  - 📥 Шар інтеграції (Integration Layer)
  - 🧠 Ядро обробки (Processing Core)
    - 📊 Індикатори (Indicators)
    - 🎯 Стратегії (Strategies)
    - 🧬 Нейромодуляція (Neuromodulation)
    - ⚡ TACL
  - 💼 Виконання (Execution)
  - 📡 Спостереження (Observability)
  - 👤 Інтерфейси (Interfaces)

### 2. Нейромодуляційна система / Neuromodulation System
- **Файл / File**: `neuromodulation_system.mmd` → `neuromodulation_system.svg`
- **Опис / Description**: Детальна візуалізація нейромодуляційних контрольних механізмів
- **Тип / Type**: Flowchart (graph TB)
- **Компоненти / Components**:
  - 💊 Дофамінова підсистема (Dopamine Subsystem)
  - 🎯 Серотонінова підсистема (Serotonin Subsystem)
  - 🛑 GABA підсистема (GABA Subsystem)
  - ⚙️ Інтеграційний центр (Integration Center)
  - 📊 Входи (Inputs): P&L, Market conditions, Performance, Trade frequency
  - 🎯 Виходи (Outputs): Position size, Risk tolerance, Entry threshold, Exit speed

### 3. Термодинамічний контроль TACL / TACL System
- **Файл / File**: `tacl_system.mmd` → `tacl_system.svg`
- **Опис / Description**: Візуалізація термодинамічного автономного контрольного шару
- **Тип / Type**: Flowchart (graph TB)
- **Компоненти / Components**:
  - 📊 Збір метрик (Metrics Collection)
  - 🧮 Обчислення енергії: F = U - T·S (Energy Calculation)
  - 🎚️ Валідація порогів (Threshold Validation)
  - 🚨 Управління кризами (Crisis Management)
  - ⚙️ Дії контролю (Control Actions)
- **Метрики / Metrics**: Latency P95/P99, CPU, Memory, Queue depth, Coherency drift, Packet loss

### 4. Життєвий цикл торгівельного сигналу / Signal Lifecycle
- **Файл / File**: `signal_lifecycle.mmd` → `signal_lifecycle.svg`
- **Опис / Description**: Послідовна діаграма повного циклу від генерації сигналу до виконання
- **Тип / Type**: Sequence diagram
- **Учасники / Participants**:
  - Ринок (Market)
  - Інжестор (Ingestion)
  - Feature Store
  - Індикатори (Indicators)
  - Нейромодулятори (Neuromodulators)
  - Стратегія (Strategy)
  - TACL
  - Риск-менеджер (Risk Manager)
  - Execution Gateway
  - Брокер (Broker)
  - Телеметрія (Telemetry)

### 5. Взаємозв'язки модулів / Module Relationships
- **Файл / File**: `module_relationships.mmd` → `module_relationships.svg`
- **Опис / Description**: Детальна візуалізація залежностей між шарами системи
- **Тип / Type**: Flowchart (graph LR)
- **Шари / Layers**:
  - Шар даних (Data Layer)
  - Аналітичний шар (Analytics Layer)
  - Шар рішень (Decision Layer)
  - Шар виконання (Execution Layer)
  - Контрольний шар (Control Layer)
  - Шар спостереження (Observability Layer)

## Існуючі діаграми / Existing Diagrams

### System Overview
- **Файл / File**: `system_overview.mmd` → `system_overview.svg`
- **Опис / Description**: Контекстна діаграма системи TradePulse (2025 ревізія)

### Service Interactions
- **Файл / File**: `service_interactions.mmd` → `service_interactions.svg`
- **Опис / Description**: Послідовність взаємодій між сервісами

### Data Flow
- **Файл / File**: `data_flow.mmd` → `data_flow.svg`
- **Опис / Description**: Потік даних від вхідних джерел до виконання

### Feature Store Internals
- **Файл / File**: `feature_store_internals.mmd` → `feature_store_internals.svg`
- **Опис / Description**: Внутрішня архітектура Feature Store

## Генерація SVG / SVG Generation

Для генерації SVG файлів з Mermaid джерел використовуйте:

To generate SVG files from Mermaid sources, use:

```bash
# З кореня проєкту / From project root
./scripts/generate_conceptual_diagrams.sh
```

Цей скрипт використовує `@mermaid-js/mermaid-cli` для конвертації `.mmd` файлів у `.svg`.

This script uses `@mermaid-js/mermaid-cli` to convert `.mmd` files to `.svg`.

### Вимоги / Requirements
- Node.js >= 18
- npm або npx
- @mermaid-js/mermaid-cli (встановлюється автоматично / installed automatically)

### Конфігурація / Configuration
- `puppeteer-config.json` - налаштування для Puppeteer при рендерингу

## Перегляд діаграм / Viewing Diagrams

### В GitHub
GitHub автоматично рендерить Mermaid діаграми в Markdown файлах.

GitHub automatically renders Mermaid diagrams in Markdown files.

### Локально / Locally

**Опція 1: VS Code**
- Встановіть розширення "Markdown Preview Mermaid Support"
- Відкрийте `.md` або `.mmd` файл
- Використайте preview (Ctrl+Shift+V)

**Опція 2: Онлайн редактори**
- [Mermaid Live Editor](https://mermaid.live/)
- Копіюйте вміст `.mmd` файлу в редактор

**Опція 3: MkDocs**
- Запустіть локальний сервер документації:
  ```bash
  mkdocs serve
  ```
- Відкрийте http://localhost:8000

## Стиль та конвенції / Style and Conventions

### Кольорова схема / Color Scheme
- 🔵 Синій (`#e1f5ff`, `#e3f2fd`): Індикатори та аналітичний шар
- 🟡 Жовтий (`#fff4e1`, `#fff3e0`): Нейромодуляція та стратегії
- 🔴 Червоний (`#ffe1e1`, `#ffebee`): TACL та контроль
- 🟢 Зелений (`#4caf50`, `#81c784`): Успішні операції
- 🔴 Червоний (`#f44336`, `#e57373`): Критичні стани

### Типи стрілок / Arrow Types
- `-->` : Прямий потік даних (direct data flow)
- `-.->` : Контрольний сигнал (control signal)
- `==>` : Потовщена лінія для основних шляхів (thick line for main paths)
- `..>` : Асинхронний зв'язок (async connection)

### Іконки / Icons
Використовуються емоджі для швидкої ідентифікації типів компонентів:
- 🌐 Зовнішні системи
- 📥 Вхідні потоки
- 🧠 Обробка
- 💼 Виконання
- 📡 Моніторинг
- 👤 Користувацькі інтерфейси

## Оновлення діаграм / Updating Diagrams

1. Відредагуйте відповідний `.mmd` файл
2. Запустіть скрипт генерації для оновлення SVG
3. Закомітьте обидва файли (`.mmd` та `.svg`)
4. Оновіть посилання в документації, якщо потрібно

Steps:
1. Edit the corresponding `.mmd` file
2. Run generation script to update SVG
3. Commit both files (`.mmd` and `.svg`)
4. Update documentation references if needed

## Пов'язані документи / Related Documents

- [Концептуальна архітектура (UA)](../../CONCEPTUAL_ARCHITECTURE_UA.md)
- [Системний огляд](../system_overview.md)
- [Основна архітектура](../../ARCHITECTURE.md)
- [TACL документація](../../TACL.md)

## Контакти / Contacts

Для питань щодо архітектурних діаграм звертайтесь до Architecture Review Board.

For questions about architectural diagrams, contact the Architecture Review Board.

---

**Версія / Version**: 1.0.0  
**Дата оновлення / Last Updated**: 2025-11-17  
**Автори / Authors**: TradePulse Architecture Team
