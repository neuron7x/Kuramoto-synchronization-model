# Концептуальна архітектура TradePulse

## Огляд

Цей документ візуалізує концептуальні елементи системи TradePulse та їхні взаємозв'язки. Документація розроблена для розуміння архітектури на високому рівні абстракції.

## Зміст

- [Концептуальна карта системи](#концептуальна-карта-системи)
- [Основні концептуальні елементи](#основні-концептуальні-елементи)
- [Взаємозв'язки модулів](#взаємозвязки-модулів)
- [Потоки даних та сигналів](#потоки-даних-та-сигналів)
- [Нейромодуляційний контроль](#нейромодуляційний-контроль)
- [Термодинамічний контроль (TACL)](#термодинамічний-контроль-tacl)
- [Життєвий цикл торгівельного сигналу](#життєвий-цикл-торгівельного-сигналу)

---

## Концептуальна карта системи

Ця діаграма показує високорівневу концептуальну архітектуру TradePulse з усіма ключовими елементами:

```mermaid
graph TB
    subgraph "🌐 Зовнішні джерела"
        MD[Ринкові дані]
        AD[Альтернативні дані]
        NF[Новини та настрої]
        BE[Брокерські події]
    end

    subgraph "📥 Шар інтеграції"
        ING[Інжестор даних]
        VAL[Валідація якості]
        BUS[Шина подій]
    end

    subgraph "🧠 Ядро обробки"
        subgraph "📊 Індикатори"
            KURA[Kuramoto<br/>Синхронізація]
            RICCI[Ricci Flow<br/>Кривизна]
            ENTR[Ентропійні<br/>міри]
            TECH[Технічні<br/>індикатори]
        end

        subgraph "🎯 Стратегії"
            FETE[FETE DSL<br/>Стратегії]
            BACKT[Бектестинг]
            OPT[Оптимізація]
        end

        subgraph "🧬 Нейромодуляція"
            DOP[Дофамін<br/>Винагорода]
            SER[Серотонін<br/>Ризик]
            GABA[GABA<br/>Гальмування]
        end

        subgraph "⚡ TACL"
            THERMO[Термодинамічна<br/>валідація]
            ENERGY[Енергетичний<br/>бюджет]
            CRISIS[Управління<br/>кризами]
        end
    end

    subgraph "💼 Виконання"
        RISK[Перевірка<br/>ризиків]
        EXEC[Шлюз<br/>виконання]
        BROKER[Адаптери<br/>брокерів]
    end

    subgraph "📡 Спостереження"
        TELEM[Телеметрія]
        ALERT[Алерти]
        AUDIT[Аудит]
    end

    subgraph "👤 Інтерфейси"
        UI[Веб UI]
        CLI[CLI]
        API[API]
    end

    MD --> ING
    AD --> ING
    NF --> ING
    BE --> ING

    ING --> VAL
    VAL --> BUS

    BUS --> KURA
    BUS --> RICCI
    BUS --> ENTR
    BUS --> TECH

    KURA --> FETE
    RICCI --> FETE
    ENTR --> FETE
    TECH --> FETE

    FETE --> BACKT
    FETE --> OPT

    DOP -.регулює.-> FETE
    SER -.регулює.-> RISK
    GABA -.регулює.-> EXEC

    THERMO -.контролює.-> FETE
    ENERGY -.моніторить.-> EXEC
    CRISIS -.керує.-> RISK

    OPT --> RISK
    BACKT --> RISK
    RISK --> EXEC
    EXEC --> BROKER

    BROKER --> BE

    TELEM -.збирає з.-> ING
    TELEM -.збирає з.-> FETE
    TELEM -.збирає з.-> EXEC
    ALERT -.реагує на.-> TELEM
    AUDIT -.відстежує.-> EXEC

    UI --> API
    CLI --> API
    API --> FETE
    API --> RISK
    API --> TELEM

    style KURA fill:#e1f5ff
    style RICCI fill:#e1f5ff
    style ENTR fill:#e1f5ff
    style TECH fill:#e1f5ff
    style DOP fill:#fff4e1
    style SER fill:#fff4e1
    style GABA fill:#fff4e1
    style THERMO fill:#ffe1e1
    style ENERGY fill:#ffe1e1
    style CRISIS fill:#ffe1e1
```

---

## Основні концептуальні елементи

### 1. Аналітичне ядро

Компоненти, відповідальні за аналіз ринкових даних та генерацію торгівельних сигналів:

```mermaid
mindmap
  root((Аналітичне<br/>ядро))
    Індикатори
      Геометричні
        Kuramoto осцилятори
        Ricci Flow кривизна
        Мультимасштабний аналіз
      Статистичні
        Ентропійні міри
        Hurst експонента
        Фрактальна GCL
      Традиційні
        RSI, MACD, Bollinger
        Volume Profile
        Pivot Points
    Feature Engineering
      Ієрархічні ознаки
      Нормалізація
      Pipeline обробки
      Кешування
    Стратегії
      FETE DSL
        Декларативний опис
        Композиція сигналів
        Керування ризиками
      Оптимізатор
        Генетичні алгоритми
        Optuna framework
        Параметричний пошук
      Бектестер
        Подієва симуляція
        Комісії та slippage
        Метрики продуктивності
```

### 2. Система керування

Контрольні механізми для забезпечення стабільності та безпеки:

```mermaid
mindmap
  root((Система<br/>керування))
    Нейромодуляція
      Дофамінова система
        Реакція на винагороду
        Мотиваційні сигнали
        Навчання з підкріпленням
      Серотонінова система
        Регуляція ризику
        Адаптація до умов
        Контроль настрою
      GABA система
        Гальмування сигналів
        Запобігання перетрейдингу
        Стабілізація
    TACL
      Термодинаміка
        Вільна енергія Гельмгольца
        Внутрішня енергія U
        Ентропія стабільності S
      Валідація
        Метрики латентності
        Використання CPU/RAM
        Глибина черг
      Управління кризами
        Виявлення аномалій
        Автоматичні відкати
        Відновлення стабільності
    Моніторинг
      Телеметрія
        OpenTelemetry
        Prometheus metrics
        Distributed tracing
      Алертинг
        Розумні правила
        Ескалаційні політики
        Інтеграція з runbook
      Аудит
        Trail всіх операцій
        Governance compliance
        Lineage tracking
```

### 3. Інфраструктура даних

```mermaid
mindmap
  root((Інфраструктура<br/>даних))
    Джерела
      Ринкові дані
        CCXT exchanges
        WebSocket feeds
        REST API polling
      Альтернативні
        Новинні ленти
        Соціальні сигнали
        On-chain метрики
    Зберігання
      Hot path
        Redis cluster
        In-memory buffers
        Sub-50ms latency
      Операційне
        PostgreSQL 16
        Temporal tables
        PITR backup
      Аналітичне
        Iceberg lakehouse
        S3-compatible
        Parquet columnar
    Feature Store
      Online serving
        Redis backing
        Low-latency reads
        Point-in-time correctness
      Offline training
        Parquet datasets
        Historical features
        Experiment reproducibility
      Catalog
        Feast registry
        Schema versioning
        Lineage metadata
```

---

## Взаємозв'язки модулів

Ця діаграма демонструє детальні взаємозв'язки між основними модулями системи:

```mermaid
graph LR
    subgraph "Шар даних"
        DS[Data Sources]
        DQ[Data Quality]
        FS[Feature Store]
    end

    subgraph "Аналітичний шар"
        IND[Indicators Layer]
        FEAT[Feature Engineering]
        SIG[Signal Generation]
    end

    subgraph "Шар рішень"
        STRAT[Strategy Engine]
        RISK[Risk Management]
        PORT[Portfolio Manager]
    end

    subgraph "Шар виконання"
        EXEC[Execution Engine]
        OMS[Order Management]
        ADAPT[Broker Adapters]
    end

    subgraph "Контрольний шар"
        NEURO[Neuromodulators]
        TACL[TACL Controller]
        GOV[Governance]
    end

    subgraph "Шар спостереження"
        TELEM[Telemetry]
        LOG[Logging]
        TRACE[Tracing]
    end

    DS -->|raw data| DQ
    DQ -->|validated| FS
    FS -->|features| IND
    IND -->|indicators| FEAT
    FEAT -->|engineered| SIG
    SIG -->|signals| STRAT

    STRAT -->|orders intent| RISK
    RISK -->|approved| PORT
    PORT -->|allocations| EXEC
    EXEC -->|orders| OMS
    OMS -->|routes| ADAPT

    NEURO -.modulates.-> STRAT
    NEURO -.modulates.-> RISK
    NEURO -.modulates.-> EXEC

    TACL -.validates.-> STRAT
    TACL -.validates.-> EXEC
    TACL -.controls.-> RISK

    GOV -.audits.-> RISK
    GOV -.audits.-> EXEC
    GOV -.policies.-> STRAT

    TELEM -.observes.-> IND
    TELEM -.observes.-> STRAT
    TELEM -.observes.-> EXEC

    LOG -.captures.-> DS
    LOG -.captures.-> RISK
    LOG -.captures.-> OMS

    TRACE -.tracks.-> SIG
    TRACE -.tracks.-> EXEC
    TRACE -.tracks.-> ADAPT

    ADAPT -->|fills| OMS
    OMS -->|confirmations| EXEC
    EXEC -->|P&L| PORT
    PORT -->|feedback| STRAT
    STRAT -->|learning| FEAT

    style DS fill:#e3f2fd
    style FS fill:#e3f2fd
    style STRAT fill:#fff3e0
    style EXEC fill:#f3e5f5
    style NEURO fill:#ffebee
    style TACL fill:#ffebee
```

---

## Потоки даних та сигналів

Детальний життєвий цикл даних від отримання до виконання:

```mermaid
flowchart TB
    START([Початок: Ринкова подія])
    
    subgraph "Фаза 1: Прийом"
        RECV[Отримання сирих даних]
        NORM[Нормалізація формату]
        VALID[Валідація схеми]
        STAMP[Часові мітки]
    end

    subgraph "Фаза 2: Збагачення"
        FEAT_EXT[Витяг базових ознак]
        CALC_IND[Розрахунок індикаторів]
        HIER_FEAT[Ієрархічні ознаки]
        CACHE[Кешування]
    end

    subgraph "Фаза 3: Генерація сигналів"
        KURA_SIG[Kuramoto сигнал]
        RICCI_SIG[Ricci сигнал]
        ENTR_SIG[Ентропійний сигнал]
        COMPOSITE[Композитний сигнал]
    end

    subgraph "Фаза 4: Нейромодуляція"
        DOP_MOD[Дофамінова модуляція]
        SER_MOD[Серотонінова модуляція]
        GABA_MOD[GABA модуляція]
        ADJUST[Адаптація параметрів]
    end

    subgraph "Фаза 5: Стратегічні рішення"
        EVAL_STRAT[Оцінка стратегії]
        SIZE_POS[Розрахунок розміру]
        RISK_CHECK[Перевірка ризиків]
        ORDER_GEN[Генерація ордера]
    end

    subgraph "Фаза 6: Термодинамічний контроль"
        THERMO_VAL[Валідація енергії]
        CRISIS_CHECK{Криза?}
        CIRCUIT{Автомат<br/>захисту}
        PROCEED[Дозволити виконання]
        BLOCK[Заблокувати]
    end

    subgraph "Фаза 7: Виконання"
        PRE_TRADE[Передторгові перевірки]
        ROUTE[Маршрутизація]
        SUBMIT[Подання до брокера]
        CONFIRM[Підтвердження]
    end

    subgraph "Фаза 8: Зворотний зв'язок"
        RECORD[Запис результатів]
        UPDATE_PNL[Оновлення P&L]
        LEARN[Навчання моделі]
        TELEM_LOG[Телеметрія]
    end

    START --> RECV
    RECV --> NORM
    NORM --> VALID
    VALID --> STAMP

    STAMP --> FEAT_EXT
    FEAT_EXT --> CALC_IND
    CALC_IND --> HIER_FEAT
    HIER_FEAT --> CACHE

    CACHE --> KURA_SIG
    CACHE --> RICCI_SIG
    CACHE --> ENTR_SIG
    KURA_SIG --> COMPOSITE
    RICCI_SIG --> COMPOSITE
    ENTR_SIG --> COMPOSITE

    COMPOSITE --> DOP_MOD
    COMPOSITE --> SER_MOD
    COMPOSITE --> GABA_MOD
    DOP_MOD --> ADJUST
    SER_MOD --> ADJUST
    GABA_MOD --> ADJUST

    ADJUST --> EVAL_STRAT
    EVAL_STRAT --> SIZE_POS
    SIZE_POS --> RISK_CHECK
    RISK_CHECK --> ORDER_GEN

    ORDER_GEN --> THERMO_VAL
    THERMO_VAL --> CRISIS_CHECK
    CRISIS_CHECK -->|Так| BLOCK
    CRISIS_CHECK -->|Ні| CIRCUIT
    CIRCUIT -->|OK| PROCEED
    CIRCUIT -->|Порушення| BLOCK
    BLOCK --> TELEM_LOG

    PROCEED --> PRE_TRADE
    PRE_TRADE --> ROUTE
    ROUTE --> SUBMIT
    SUBMIT --> CONFIRM

    CONFIRM --> RECORD
    RECORD --> UPDATE_PNL
    UPDATE_PNL --> LEARN
    LEARN --> TELEM_LOG

    TELEM_LOG --> END([Кінець циклу])

    style RECV fill:#bbdefb
    style CALC_IND fill:#c5e1a5
    style COMPOSITE fill:#fff9c4
    style ADJUST fill:#ffccbc
    style ORDER_GEN fill:#f8bbd0
    style THERMO_VAL fill:#ffcdd2
    style BLOCK fill:#ef9a9a
    style PROCEED fill:#a5d6a7
    style CONFIRM fill:#ce93d8
    style LEARN fill:#90caf9
```

---

## Нейромодуляційний контроль

Детальна візуалізація нейромодуляційної системи:

```mermaid
graph TB
    subgraph "🧠 Нейромодуляційна система"
        subgraph "💊 Дофамінова підсистема"
            DOP_REWARD[Сигнал винагороди]
            DOP_PREDICT[Прогноз винагороди]
            DOP_ERROR[Помилка прогнозу δ]
            DOP_LEARNING[Навчальний сигнал]
            
            DOP_REWARD --> DOP_ERROR
            DOP_PREDICT --> DOP_ERROR
            DOP_ERROR --> DOP_LEARNING
        end

        subgraph "🎯 Серотонінова підсистема"
            SER_STATE[Оцінка стану]
            SER_RISK[Рівень ризику]
            SER_MOOD[Настрій системи]
            SER_ADAPT[Адаптація стратегії]
            
            SER_STATE --> SER_RISK
            SER_RISK --> SER_MOOD
            SER_MOOD --> SER_ADAPT
        end

        subgraph "🛑 GABA підсистема"
            GABA_MONITOR[Моніторинг активності]
            GABA_THRESH[Поріг гальмування]
            GABA_INHIB[Гальмівний сигнал]
            GABA_COOL[Період охолодження]
            
            GABA_MONITOR --> GABA_THRESH
            GABA_THRESH --> GABA_INHIB
            GABA_INHIB --> GABA_COOL
        end

        subgraph "⚙️ Інтеграційний центр"
            INTEGRATE[Інтеграція сигналів]
            WEIGHTS[Вагові коефіцієнти]
            FINAL_MOD[Фінальна модуляція]
        end
    end

    subgraph "📊 Входи"
        PNL[P&L історія]
        MARKET[Ринкові умови]
        PERF[Метрики продуктивності]
        TRADES[Частота торгів]
    end

    subgraph "🎯 Виходи"
        POS_SIZE[Розмір позиції ↑↓]
        RISK_TOL[Толерантність ризику ↑↓]
        ENTRY_THRESH[Поріг входу ↑↓]
        EXIT_SPEED[Швидкість виходу ↑↓]
    end

    PNL --> DOP_REWARD
    MARKET --> SER_STATE
    PERF --> DOP_PREDICT
    TRADES --> GABA_MONITOR

    DOP_LEARNING --> INTEGRATE
    SER_ADAPT --> INTEGRATE
    GABA_INHIB --> INTEGRATE

    INTEGRATE --> WEIGHTS
    WEIGHTS --> FINAL_MOD

    FINAL_MOD --> POS_SIZE
    FINAL_MOD --> RISK_TOL
    FINAL_MOD --> ENTRY_THRESH
    FINAL_MOD --> EXIT_SPEED

    style DOP_LEARNING fill:#81c784
    style SER_ADAPT fill:#64b5f6
    style GABA_INHIB fill:#e57373
    style FINAL_MOD fill:#ffd54f
```

---

## Термодинамічний контроль (TACL)

Візуалізація термодинамічного шару автономного контролю:

```mermaid
graph TB
    subgraph "⚡ TACL - Thermodynamic Autonomic Control Layer"
        subgraph "📊 Збір метрик"
            LAT_P95[Латентність P95]
            LAT_P99[Латентність P99]
            CPU[Використання CPU]
            MEM[Використання пам'яті]
            QUEUE[Глибина черги]
            COHERENCY[Дрейф когерентності]
            PACKET[Втрата пакетів]
        end

        subgraph "🧮 Обчислення енергії"
            INTERNAL[Внутрішня енергія U]
            ENTROPY[Ентропія стабільності S]
            TEMP[Температура контролю T]
            FREE_ENERGY[Вільна енергія Гельмгольца<br/>F = U - T·S]
        end

        subgraph "🎚️ Валідація порогів"
            THRESHOLD{F ≤ 1.35?}
            MARGIN[Запас безпеки 12%]
            TREND[Аналіз тренду]
        end

        subgraph "🚨 Управління кризами"
            DETECT[Виявлення кризи]
            CLASSIFY[Класифікація типу]
            PROTOCOL[Вибір протоколу]
            RECOVER[Виконання відновлення]
        end

        subgraph "⚙️ Дії контролю"
            PROCEED[✅ Дозволити операцію]
            THROTTLE[⚠️ Обмежити навантаження]
            ROLLBACK[🔄 Автоматичний відкат]
            ALERT[📢 Ескалація алерту]
        end
    end

    LAT_P95 --> INTERNAL
    LAT_P99 --> INTERNAL
    CPU --> INTERNAL
    MEM --> INTERNAL
    QUEUE --> INTERNAL
    COHERENCY --> INTERNAL
    PACKET --> INTERNAL

    LAT_P95 --> ENTROPY
    LAT_P99 --> ENTROPY
    CPU --> ENTROPY
    MEM --> ENTROPY
    QUEUE --> ENTROPY
    COHERENCY --> ENTROPY
    PACKET --> ENTROPY

    INTERNAL --> FREE_ENERGY
    ENTROPY --> FREE_ENERGY
    TEMP --> FREE_ENERGY

    FREE_ENERGY --> THRESHOLD
    MARGIN --> THRESHOLD
    FREE_ENERGY --> TREND

    THRESHOLD -->|Так| PROCEED
    THRESHOLD -->|Ні| DETECT
    TREND -->|Погіршення| DETECT

    DETECT --> CLASSIFY
    CLASSIFY --> PROTOCOL
    PROTOCOL --> RECOVER

    RECOVER --> THROTTLE
    RECOVER --> ROLLBACK
    RECOVER --> ALERT

    THROTTLE -.зворотний зв'язок.-> LAT_P95
    ROLLBACK -.зворотний зв'язок.-> CPU

    style FREE_ENERGY fill:#ffeb3b
    style THRESHOLD fill:#ff9800
    style PROCEED fill:#4caf50
    style DETECT fill:#f44336
    style ROLLBACK fill:#e91e63
    style RECOVER fill:#9c27b0

    subgraph "📈 Формули"
        FORMULA1["U = Σ(wᵢ × penaltyᵢ)<br/>penalty = max(0, (metric - threshold) / threshold)"]
        FORMULA2["S = Σ(headroomᵢ)<br/>headroom = max(0, (threshold - metric) / threshold)"]
        FORMULA3["F = U - T×S<br/>T = 0.60 (константа)"]
    end

    INTERNAL -.використовує.-> FORMULA1
    ENTROPY -.використовує.-> FORMULA2
    FREE_ENERGY -.використовує.-> FORMULA3
```

### Таблиця метрик TACL

| Метрика | Опис | Поріг | Вага |
|---------|------|-------|------|
| `latency_p95` | 95-й перцентиль латентності (мс) | 85.0 | 1.6 |
| `latency_p99` | 99-й перцентиль латентності (мс) | 120.0 | 1.9 |
| `coherency_drift` | Дрейф спільного стану | 0.08 | 1.2 |
| `cpu_burn` | Коефіцієнт використання CPU | 0.75 | 0.9 |
| `mem_cost` | Footprint пам'яті (GiB) | 6.5 | 0.8 |
| `queue_depth` | Довжина черги | 32.0 | 0.7 |
| `packet_loss` | Коефіцієнт втрати пакетів | 0.005 | 1.4 |

---

## Життєвий цикл торгівельного сигналу

Послідовна діаграма повного циклу від генерації сигналу до виконання:

```mermaid
sequenceDiagram
    autonumber
    participant M as Ринок
    participant I as Інжестор
    participant F as Feature Store
    participant Ind as Індикатори
    participant N as Нейромодулятори
    participant S as Стратегія
    participant T as TACL
    participant R as Риск-менеджер
    participant E as Execution Gateway
    participant B as Брокер
    participant Tel as Телеметрія

    M->>I: Нові ринкові дані
    I->>I: Валідація та нормалізація
    I->>F: Зберегти сирі дані
    F->>Ind: Запит на розрахунок
    
    par Паралельний розрахунок індикаторів
        Ind->>Ind: Kuramoto синхронізація
        Ind->>Ind: Ricci кривизна
        Ind->>Ind: Ентропійні міри
    end
    
    Ind->>F: Зберегти індикатори
    F->>S: Надати feature vector
    
    S->>N: Запит модуляційних параметрів
    N->>N: Дофамін: оцінка винагороди
    N->>N: Серотонін: оцінка ризику
    N->>N: GABA: перевірка гальмування
    N-->>S: Модульовані параметри
    
    S->>S: Генерація торгівельного сигналу
    S->>T: Запит на термодинамічну валідацію
    
    T->>T: Розрахунок F = U - T·S
    alt F ≤ 1.35 (безпечно)
        T-->>S: ✅ Валідація пройдена
        S->>R: Подати намір ордера
        
        R->>R: Передторгові перевірки
        R->>R: Перевірка лімітів позиції
        R->>R: Валідація розміру
        
        alt Ризики в межах норми
            R-->>E: ✅ Дозволити виконання
            E->>B: Маршрутизувати ордер
            B-->>E: Підтвердження виконання
            E-->>S: Статус: FILLED
            S->>F: Оновити P&L та метрики
            F->>N: Зворотний зв'язок для навчання
        else Порушення ризик-лімітів
            R-->>S: ❌ Ордер відхилено
            S->>Tel: Логувати відхилення
        end
    else F > 1.35 (небезпечно)
        T-->>S: ❌ Енергія перевищена
        T->>T: Ініціювати протокол кризи
        T->>Tel: Критичний алерт
        S->>Tel: Логувати блокування
    end
    
    Tel->>Tel: Агрегувати метрики
    Tel->>N: Оновити нейромодуляційні моделі
    Tel->>T: Оновити енергетичні базові лінії

    Note over M,Tel: Цикл повторюється для кожної ринкової події
```

---

## Додаткові ресурси

### Пов'язана документація

- [Основна архітектурна схема](ARCHITECTURE.md)
- [Системний огляд](architecture/system_overview.md)
- [Документація TACL](TACL.md)
- [Керівництво з нейромодуляторів](docs/neuromodulators/)
- [Специфікація індикаторів](core/indicators/README.md)
- [DSL стратегій FETE](core/strategies/README.md)

### Діаграми та активи

Усі діаграми Mermaid можна знайти в:
- `docs/architecture/assets/` - архітектурні діаграми
- `docs/security/assets/` - діаграми безпеки

### Інструменти візуалізації

Для рендерингу діаграм використовуються:
- MkDocs з плагіном `mermaid2`
- GitHub автоматично рендерить Mermaid в Markdown
- Puppeteer для експорту в SVG (див. `docs/architecture/assets/puppeteer-config.json`)

---

## Версіонування

- **Версія документа**: 1.0.0
- **Дата створення**: 2025-11-17
- **Автор**: TradePulse Architecture Team
- **Статус**: Затверджено

## Журнал змін

| Дата | Версія | Опис |
|------|--------|------|
| 2025-11-17 | 1.0.0 | Початкова версія концептуальної архітектури |
