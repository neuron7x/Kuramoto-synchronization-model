# Production Readiness: E2E replayable live-sim checklist

Цей документ описує, що повинен покривати e2e тест, щоб підвищити readiness.

Core checks:
- [ ] Deterministic backtest with fixed seed produces stable signals.
- [ ] Signals can be exported and replayed without mutation.
- [ ] Live runner accepts pluggable exchange adapter (production adapter і fake one).
- [ ] FakeExchange supports latency, jitter, failures, disconnects.
- [ ] Risk controls (max position, max drawdown, circuit breaker) перевіряються під навантаженням і при помилках.
- [ ] Тест виконується в CI; провал тесту блокує merge.
- [ ] Логи та artifact'и (backtest report, live report, signals JSON) прикріпляються до CI run для дебагу.
- [ ] Тест має timeout і не флейкить у >1% прогонів.
- [ ] Документація "how to run locally" та "explain failure modes" присутня.

## Reproducibility Checklist

- [ ] Для кожного модельного артефакту зафіксовано `data_version` (або hash) і `code_version`.
- [ ] Training data snapshot/version збережений у registry та доступний для відтворення.
- [ ] Git SHA/релізний тег тренувального коду закріплений у run metadata.
- [ ] Всі випадкові seed-и та nondeterministic налаштування описані в run notes.
- [ ] Dependency lockfile (requirements.lock/poetry.lock) оновлено і прикріплено до run.
- [ ] Контрольні артефакти (feature manifests, checksums) збережені разом із моделлю.

## Операційні артефакти

- [ ] Runbook-и для продакшену оновлені та зібрані в `docs/operational_handbook.md`, включно з новими сценаріями у [`docs/OPERATIONS.md`](OPERATIONS.md).
- [ ] Incident playbooks (`docs/incident_playbooks.md`, `docs/runbook_data_incident.md`) переглянуті, дати ревізій зафіксовані в квитку.
- [ ] SLA-пакет узгоджений: `docs/sla_alert_playbooks.md` містить актуальні пороги для Market Data, Feature Store та Reconciliation.
- [ ] PagerDuty/діджестер контакти підтверджені; відповідальні особи перелічені у зміні.

## Інтеграції з реальними потоками даних

- [ ] Підтверджено схеми інтеграції: мермейд-діаграма [`docs/architecture/assets/data_flow.mmd`](architecture/assets/data_flow.mmd) або оновлений експортив з [`docs/architecture/system_overview.md`](architecture/system_overview.md) додані до релізного пакету.
- [ ] Є звіт про проходження rehearsal для подвійних venue (`docs/OPERATIONS.md#scenario-dual-venue-market-data-degradation`).
- [ ] Зафіксовані результати синхронізації feature store та reconciliation (`reports/live/<date>/recon.json`, `sla_incidents.md`).
- [ ] Вказано контрольні CLI-команди для live перевірки потоків (metrics, ingestion, replay) в runbook-ах.

## Інцидентні процедури та перевірки

- [ ] Є заповнений шаблон постмортему для останнього drill (`reports/live/<date>/postmortem.md`).
- [ ] Валідація комунікаційної матриці: канали `#inc-trading`, `#risk-ops`, external status page.
- [ ] Тригериться симульований алерт на `TradePulseVenueDivergence` та задокументовано виконання плейбука.
- [ ] Результати failover rehearsal прикріплені (`reports/live/<date>/recon.json`, Grafana скріншоти).
