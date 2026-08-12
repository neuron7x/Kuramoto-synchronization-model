# 7 фундаментальних задач для доведення PR до інтеграційної якості

Цей список фіксує наступний інженерний рівень для `BBB–NVU Cognitive Noise Gate 2026`: від repo-seed артефакту до продуктового, технологічного, інформатичного, практичного, системного, операційного та інтегрально готового до інтеграції компонента.

## 1. Контрактний контур даних і версій

**Проблема:** поточні схеми задають базовий формат, але інтеграційний споживач потребує незмінний контракт для версій, сумісності, міграцій і відмов.

**Зробити:**

- Зафіксувати machine-readable контракт `InferenceInput`, `Observation`, `InferenceRun`, `RiskState`, `ControlAction` і `ProvenanceRecord` як версіоновані API-об'єкти.
- Додати `schema_version`, `contract_version`, `rules_version`, `engine_version` і політику backward/forward compatibility.
- Заборонити неявні поля: `additionalProperties=false` має залишатися інваріантом для production path.
- Додати набір негативних контрактних прикладів: неправильні типи, зайві поля, пропущені provenance/time поля, несумісна версія.

**Критерій готовності:** будь-який несумісний payload переходить у керований `BLACK_INVALID` або відхиляється schema gate до inference, без Python exception у production wrapper.

## 2. Детермінований runtime API замість demo CLI

**Проблема:** CLI-рушій корисний для seed, але інтеграції потрібен стабільний runtime API з чіткими межами побічних ефектів.

**Зробити:**

- Виділити бібліотечний API `DeterministicInferenceEngine.evaluate_run(...)` як основний entrypoint.
- Розділити pure inference, validation gate, provenance builder, CLI adapter і файл-системний I/O.
- Додати структуровані помилки/відмови як дані, а не як runtime exceptions.
- Додати стабільний JSON output profile для batch, service і CI modes.

**Критерій готовності:** однаковий input/rules/engine дає однаковий `run_hash`; CLI, тест і майбутній сервісний wrapper використовують той самий core engine без дублювання логіки.

## 3. Executable invariants + dynamic traceability як merge gate

**Проблема:** інваріанти і матриця трасування мають бути не документацією після факту, а автоматично перевірюваним merge gate.

**Зробити:**

- Зробити `invariants.yaml` компільованим у pytest-перевірки або перевіряти його hash/test bindings у CI.
- Вимагати `@requirement("Rxxx")` для кожного тесту, який закриває safety/traceability claim.
- Генерувати `docs/generated_traceability_matrix.csv` у CI і падати, якщо committed artifact застарів.
- Додати coverage по вимогах: кожен `Rxxx` має мінімум один позитивний, один негативний і один boundary/adversarial тест.

**Критерій готовності:** PR не може пройти, якщо змінено inference/rules/schema без оновленої трасованої вимоги, тесту і generated matrix.

## 4. Калібрований adversarial/property/mutation test harness

**Проблема:** поточний adversarial sandbox є корисним стартом, але інтеграційна якість вимагає вимірювану стійкість до мутацій і шуму.

**Зробити:**

- Винести campaign profiles: `smoke`, `ci`, `nightly`, `release` з різною кількістю і типами мутацій.
- Додати property-based тестування для повного простору finite/out-of-range/NaN/Inf/missing/conflicting input.
- Додати mutation testing для threshold/rule regressions: `>=`/`>`, `risk`/`warning`, `lower_is_worse`, action mapping.
- Зберігати кожен знайдений bypass у `tests/adversarial_golden_vectors.json` з reason, expected state і regression ID.

**Критерій готовності:** release profile має 0 bypass, 100% fail-closed для corrupted math, і визначений mutation kill-score threshold до merge.

## 5. Операційний observability/audit контур

**Проблема:** provenance в output є, але операційна інтеграція потребує структурованих audit events, метрик і incident hooks.

**Зробити:**

- Додати JSONL audit log profile з UTC timestamp, `run_hash`, `input_hash`, `rules_hash`, `engine_hash`, state, confidence, degradations, action IDs.
- Додати counters/metrics: invalid rate, degradation rate, human-review rate, confidence distribution, state distribution, schema rejection rate.
- Додати replay command: відтворити inference з saved input/rules/engine hash і перевірити hash stability.
- Описати incident workflow для `RED_CRITICAL`, `BLACK_INVALID`, source conflict і rule mismatch.

**Критерій готовності:** кожний run відтворюваний з audit bundle; деградація видима як контрольний сигнал у метриках, а не лише у JSON output.

## 6. Governance, privacy, security і integration boundary

**Проблема:** artifact явно не є медичним пристроєм, але інтеграційний контур має довести, що не створює прихованих clinical/security/privacy claims.

**Зробити:**

- Зафіксувати allowed/restricted modes у machine-readable policy file.
- Додати privacy boundary: pseudonymous `subject_id`, retention, consent, provenance separation, no direct PII.
- Додати security boundary: no hidden network calls, no dynamic rule download, pinned rules, deterministic offline inference.
- Додати human-review queue contract для `ORANGE_RISK`, `RED_CRITICAL`, `BLACK_INVALID` без autonomous clinical execution.

**Критерій готовності:** інтегратор може підключити компонент без прямого PII, без мережевих side effects і без ризику автономної клінічної дії.

## 7. Packaging, CI/CD і release readiness

**Проблема:** repo-seed має файли і тести, але інтеграція потребує відтворювану збірку, мінімальний dependency surface і release gates.

**Зробити:**

- Додати package metadata або чіткий local module entrypoint для імпорту без path hacks.
- Додати CI job matrix: schema validation, unit tests, invariant tests, adversarial smoke, traceability generation, JSON/YAML lint, py_compile.
- Додати release checklist: changelog, contract delta, migration note, rollback path, frozen vectors rerun, artifact hash manifest.
- Додати integration example для batch invocation і library invocation.

**Критерій готовності:** clean checkout може виконати documented CI commands і отримати той самий результат без ручної підготовки середовища, окрім задокументованих dependencies.

## Пріоритет виконання

1. Контрактний контур даних і версій.
2. Детермінований runtime API.
3. Executable invariants + dynamic traceability.
4. Калібрований adversarial/property/mutation harness.
5. Observability/audit контур.
6. Governance/privacy/security boundary.
7. Packaging/CI/CD/release readiness.

Цей порядок навмисний: спочатку стабілізується контракт, потім engine boundary, потім доказовість, потім стійкість, потім операційна видимість, потім governance, і лише після цього — release packaging.
