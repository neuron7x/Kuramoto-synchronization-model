# ЄДИНИЙ РЕЄСТР ТЕХНІЧНОГО БОРГУ

_(English: Unified Technical Debt Registry)_

**Дата оновлення:** 2026-06-10 (звірка з кодом) · _попередня інвентаризація: 2025-12-19_  
**Джерела:** `reports/technical_debt_assessment.md`, `AUDIT_REPORT.md`, точкове сканування TODO/FIXME/XXX, огляд TLS артефактів у `configs/tls/dev/`.

## Методологія та телеметрія якості
- Проведено інвентаризацію існуючих аудитів (код, безпека, CI/CD) та фокусних модулів (індикатори, агенти, виконання, дані, бек-тести).
- TODO/FIXME/XXX маркери виявлені у файлових групах:
  - Документація: `docs/POSTMORTEM_TEMPLATE.md`, `docs/DEPENDENCY_MANAGEMENT.md`
  - Інструменти: `tools/docs/lint_docs.py`
  - Інфраструктура: Terraform модулі EKS
  - Тести: `tests/unit/tools/docs/test_lint_docs.py`, `tests/unit/data/adapters/test_polygon.py`
  - Потребують перенесення у баг-трекер і очищення шаблонів.
- Попередній тестовий прогін: `pytest tests/unit -m "not slow" -q --maxfail=1` **не виконався** (відсутній `pytest` у середовищі). Потрібно встановити залежності з `requirements-dev.lock` і повторити прогін (відкрита дія).
- Поточні контрольні пороги (див. `TESTING.md`): лінійне покриття ≥98% (цільове), CI виконує повну матрицю pytest + Playwright + security.

## Звірка з кодом — 2026-06-10

Попередній реєстр (2025-12-19) не мав колонки статусу й ніколи не позначав закриття,
тому стверджував неіснуючий стан (зокрема TD-001 як P0-CRITICAL «імпорт ламає пакет» —
насправді давно виправлено). Нижче — звірка кожного пункту з **поточним кодом на `main`**,
з доказами (файл:рядок / тест). Метод: 4-кластерний паралельний аудит + smoke-імпорт + прогін тестів.

**Підсумок:** 22 RESOLVED · 0 PARTIAL · 0 STILL-OPEN.
_Оновлення 2026-06-10 (друга ітерація): 5 PARTIAL закрито — додано закриваючі артефакти
(log-warn, constant-series guard+тест, cache-invariant тест, jitter+log тест, warn-path тест)._

| TD | Пріор. | Статус | Доказ (звірено 2026-06-10) |
|----|--------|--------|----------------------------|
| TD-001 | P0 | ✅ RESOLVED | Усі символи існують (`multiscale_kuramoto.py:51,274,545`), експорт у `__init__.py:43-50`; `import core.indicators` OK; `tests/unit/test_indicators_kuramoto_multiscale.py` зелений |
| TD-002 | P1 | ✅ RESOLVED (2-га іт.) | Skip сигналізується структурно + `_logger.warning("multiscale_timeframes_skipped", …)`; тест `test_multiscale_skipped_timeframes_emit_warning_log` |
| TD-003 | P2 | ✅ RESOLVED (2-га іт.) | Явний guard на нульову дисперсію → fallback-вікно (не min_window); тест `test_wavelet_selector_constant_series_returns_stable_window` |
| TD-004 | P2 | ✅ RESOLVED | Історія накопичується (`retain_history` deque maxlen `temporal_ricci.py:363,395-397`); тест `test_temporal_ricci.py:72` |
| TD-005 | P3 | ✅ RESOLVED (2-га іт.) | Детермінований cache-invariant тест `test_edge_count_and_cache_avoid_rebuild` (O(1) edge count, edge-cache будується раз, інвалідується на topology change) |
| TD-006 | P1 | ✅ RESOLVED | `_w1_fallback` шанує ваги/позиції (`ricci.py:837,890-928`), той самий W1; `test_indicators_ricci.py` зелений |
| TD-007 | P3 | ✅ RESOLVED | `detector.py` без unused-import, пороги через `PhaseThresholds` dataclass; `test_phase.py:35` |
| TD-008 | P0 | ✅ RESOLVED | `simulate_performance` — детермінований walk-forward без RNG (`strategy.py:78-181`); `test_strategy_properties.py:87` |
| TD-009 | P1 | ✅ RESOLVED (2-га іт.) | Гістерезис+EMA+cooldown + `_logger.warning("agent_instability_triggered", …)` на переході; тести `test_subthreshold_jitter_does_not_flip_flop` + `test_instability_trigger_emits_log` |
| TD-010 | P2 | ✅ RESOLVED | mutation/repair → `validate_params()` clamp (`strategy.py:67,218-222,70-76`); тести `:58,179,224,231` |
| TD-011 | P2 | ✅ RESOLVED | `_evict()` на capacity (`memory.py:282-315`) + округлений NaN/Inf-стійкий ключ (`:82-93`); тест `test_strategy_memory.py:175` |
| TD-012 | P1 | ✅ RESOLVED | Валідація схеми + ValueError (`ingestion.py:115-127`), конфіг. поля, чисті імпорти; fuzz `test_ingestion_fuzz.py` |
| TD-013 | P2 | ✅ RESOLVED | `BinanceStreamHandle.start/close/__enter__/__exit__` (`ingestion.py:45-68`); тест lifecycle. _Прим.: auto-reconnect лишається поза скоупом graceful-shutdown_ |
| TD-014 | P1 | ✅ RESOLVED | `walk_forward` валідує довжину сигналів (`engine.py:511-512`), fee коректно (`:583-592`); `test_walk_forward_with_transaction_fees` |
| TD-015 | P0 | ✅ RESOLVED | Єдине джерело `calculate_position_size` (`position_sizer.py`), risk керує нотою; `test_calculate_position_size_matches_risk_aware` |
| TD-016 | P2 | ✅ RESOLVED (цей PR) | `execution/risk.py` → `execution/risk/core.py`. Heat **gross-by-design** (long+short додатні — fail-closed; нетинг **занизив би** ризик; формулювання реєстру «недооцінка» було перевернуте). Прибрано мертвий `side`/`direction` no-op під `abs()`; докстрінги виправлено. `test_portfolio_heat_sums_absolute_exposure` зелений |
| TD-017 | P2 | ✅ RESOLVED (2-га іт.) | `_maybe_warn_w1` RuntimeWarning покрито тестом `test_w1_fallback_emits_runtime_warning` (pytest.warns); `temporal_ricci.py` без важких deps за дизайном |
| TD-018 | P3 | ✅ RESOLVED | `ruff check core/phase/detector.py` → clean; unused-import немає |
| TD-019 | P0 | ✅ RESOLVED (цей PR) | Було 128/130 pinned; 2 mutable-теги в `calib-grid-witness-map.yml:26-27` пришпилено до канонічних SHA (`checkout df4cb1c…`, `setup-python a309ff8…`). repo-policy pin-guard тепер зелений на цьому файлі |
| TD-020 | P0 | ✅ RESOLVED | 0 приватних ключів: усі `configs/tls/dev/*.pem` = CERTIFICATE з `# REDACTED`; `.gitignore:42-44` блокує `*.key`; detect-secrets у `pr-gate.yml` |
| TD-021 | P0 | ✅ RESOLVED | Bandit MEDIUM=0: 2 `0.0.0.0` лише в docstring/help (`nlca_core.py:825`, `mlsdm/__main__.py:68`), реального bind немає; `bandit -ll` у CI |
| TD-022 | — | ✅ RESOLVED | 0 реальних code-debt TODO; решта — патерни сканерів/шаблони; lint-guard `tools/docs/lint_docs.py:165` блокує `TODO/FIXME/TBD` |
| TD-023-LOCK | P2 | ✅ ENFORCEMENT (цей PR) | **Process-level Fail-Closed block-factor** для TD-023: `scripts/ci/check_feature_debt_lock.py` + workflow `feature-debt-lock.yml`. BLOCK-закрито будь-який PR, що додає > 25 production-рядків у tracked-surface БЕЗ test-paydown для deficit-surfaces (`backtest/`, `analytics/`) і без аудит-trailer `Debt-Exempt: <reason>`. Чиста функція дифу (без coverage-прогону), 6 falsifiable-тестів. Стартує advisory; промоушн в **абсолютний блок** = додавання чека в branch-protection required-checks (admin-дія) після розгрібання in-flight backlog. Реалізує директиву: «жодних нових фіч, поки PR не паяє coverage-борг». |
| TD-023 | P2 | 🟡 TRACKED (partial paydown) | **Coverage Intelligence Gate (non-required) червоний: release-line coverage 85.03% < 90%** — standing-дефіцит, не регрес. Гейт сам рапортує: critical_surface (явний список) **задоволено** (next_tests.md §1 _none_); дірка — у 16 повністю-непокритих production-файлах + агрегатних таргетах (`execution` 87.74/95, `backtest` 68.55/98, `risk` 90.68/98, `core` 86.92/95, `ingestion` 89.60/95, `analytics` 75.99/90). **Цей PR** закриває 2/16 непокритих core-файлів до ~100%: `core/indicators/novelty.py` (KL/cosine, 10 falsifiable-тестів) + `core/metrics/fractal_dimension.py` (box-counting, 5 тестів). Решта 14 файлів + surface-гепи лишаються тут як свідомий, виміряний борг (потребує окремої scoped test-кампанії, не bug-fix). |

**Залишковий код-борг:** один трекнутий пункт — TD-023 (coverage-дефіцит 85.03%<90%, non-required gate, partial paydown цим PR). Решта 22 пункти кодового реєстру закрито (TD-001…022).
П'ять колишніх PARTIAL (TD-002/003/005/009/017) закрито у другій ітерації додаванням
закриваючих артефактів (log-warn, constant-series guard+тест, cache-invariant тест,
jitter+log тест, warn-path тест). Поза цим реєстром лишаються нетехнічні readiness-гепи
(`governance/readiness_register.json`: RD-001 реальні дані, QA/GOV/OPS/EXT — процес-evidence),
які не закриваються кодом.

## Реєстр

- **TD-001 (code · Indicators)**  
  - Власник: Indicators  
  - Локація: `core/indicators/__init__.py`, `core/indicators/multiscale_kuramoto.py`  
  - Опис / Причина: Публічний API експортує `MultiScaleKuramotoFeature`, `TimeFrame`, `WaveletWindowSelector`, яких модуль не надає; імпорт ламає весь пакет.  
  - Вплив / Ризик / Критичність: Блокування multi-scale індикаторів; API недоступний; 🔴 Critical  
  - Пріоритет: P0  
  - Рекомендоване виправлення: Додати відсутні класи/функції або прибрати експорти; покрити smoke-тестом імпорту.  
  - Критерій «закрито»: Імпорт працює, pytest multi-scale проходить  
  - Доказ: `reports/technical_debt_assessment.md:L3-L8`

- **TD-002 (code · Indicators)**  
  - Власник: Indicators  
  - Локація: `core/indicators/multiscale_kuramoto.py`  
  - Опис / Причина: `analyze` тихо відкидає таймфрейми < window+5, повертає нулі без сигналізації.  
  - Вплив / Ризик / Критичність: Непрозорі рішення; ризик хибних сигналів; 🟠 High  
  - Пріоритет: P1  
  - Рекомендоване виправлення: Явно логувати/повертати метадані про відкинуті вікна; додати тест на фільтрацію.  
  - Критерій «закрито»: Тести фіксують відкинуті масштаби, лог містить попередження  
  - Доказ: `reports/technical_debt_assessment.md:L6-L9`

- **TD-003 (code · Indicators)**  
  - Власник: Indicators  
  - Локація: `core/indicators/multiscale_kuramoto.py`  
  - Опис / Причина: Автокореляційний селектор не захищає від константних рядів, повертає мінімальне вікно.  
  - Вплив / Ризик / Критичність: Підсилення шуму на неліківідах; нестабільні сигнали; 🟡 Medium  
  - Пріоритет: P2  
  - Рекомендоване виправлення: Додати перевірку дисперсії/порог; fallback до нульового сигналу.  
  - Критерій «закрито»: Тест на константний ряд проходить, сигнал не шумовий  
  - Доказ: `reports/technical_debt_assessment.md:L8-L10`

- **TD-004 (code · Indicators)**  
  - Власник: Indicators  
  - Локація: `core/indicators/temporal_ricci.py`  
  - Опис / Причина: Кожен виклик очищує історію, метрики стабільності не накопичуються.  
  - Вплив / Ризик / Критичність: Неможливо оцінити динаміку; втрата історії; 🟡 Medium  
  - Пріоритет: P2  
  - Рекомендоване виправлення: Зберігати стан або приймати історію ззовні; додати тест на накопичення.  
  - Критерій «закрито»: Метрики зберігають попередні вікна, тест підтверджує  
  - Доказ: `reports/technical_debt_assessment.md:L10-L11`

- **TD-005 (code/perf · Indicators)**  
  - Власник: Indicators  
  - Локація: `core/indicators/temporal_ricci.py`  
  - Опис / Причина: Графові утиліти квадратичні, без кешування/векторизації.  
  - Вплив / Ризик / Критичність: Повільні обчислення; ризик перевищення бюджетів; 🟡 Medium  
  - Пріоритет: P3  
  - Рекомендоване виправлення: Векторизувати або кешувати shortest paths; додати бенчмарк.  
  - Критерій «закрито»: Бенчмарк показує покращення / бюджет не перевищено  
  - Доказ: `reports/technical_debt_assessment.md:L11-L12`

- **TD-006 (code · Indicators)**  
  - Власник: Indicators  
  - Локація: `core/indicators/ricci.py`  
  - Опис / Причина: Fallback ігнорує ваги/дистанції, значно спотворює кривину.  
  - Вплив / Ризик / Критичність: Невірні метрики; модельні помилки; 🟠 High  
  - Пріоритет: P1  
  - Рекомендоване виправлення: Додати вагові розрахунки або жорстко вимагати залежності; логувати деградацію.  
  - Критерій «закрито»: Тести демонструють однакові знаки кривини з основним шляхом  
  - Доказ: `reports/technical_debt_assessment.md:L12-L13`

- **TD-007 (code · Signals)**  
  - Власник: Signals  
  - Локація: `core/phase/detector.py`  
  - Опис / Причина: Жорстко зашиті пороги, імпорти невикористаних індикаторів (мертвий код).  
  - Вплив / Ризик / Критичність: Неточні фазові прапори; хибні спрацьовування; 🟢 Low  
  - Пріоритет: P3  
  - Рекомендоване виправлення: Прибрати мертвий код, параметризувати пороги, покрити тестами.  
  - Критерій «закрито»: Phase detector покритий тестами, немає невикористаних імпортів  
  - Доказ: `reports/technical_debt_assessment.md:L13-L14`

- **TD-008 (code/tests · Agents)**  
  - Власник: Agents  
  - Локація: `core/agent/strategy.py`  
  - Опис / Причина: `simulate_performance` повертає випадкові оцінки замість бектесту.  
  - Вплив / Ризик / Критичність: Непридатні оптимізації; нерепродуктивність; 🟠 High  
  - Пріоритет: P0  
  - Рекомендоване виправлення: Замінити на детермінований бектест або виділити заглушку в dev-режим.  
  - Критерій «закрито»: Тест підтверджує детермінований вихід для фіксованих даних  
  - Доказ: `reports/technical_debt_assessment.md:L15-L17`

- **TD-009 (code · Agents)**  
  - Власник: Agents  
  - Локація: `core/agent/strategy.py`  
  - Опис / Причина: Пороги без гістерезису/логування => фліп між станами.  
  - Вплив / Ризик / Критичність: Дрижання стратегій; втрата капіталу; 🟡 Medium  
  - Пріоритет: P1  
  - Рекомендоване виправлення: Додати гістерезис, логування переходів; тест на стабільність.  
  - Критерій «закрито»: Тест показує сталі рішення при малих джитерах  
  - Доказ: `reports/technical_debt_assessment.md:L16-L18`

- **TD-010 (code · Agents)**  
  - Власник: Agents  
  - Локація: `core/agent/strategy.py`  
  - Опис / Причина: Мутації/ремонт нулять великі/NaN параметри без обмежень.  
  - Вплив / Ризик / Критичність: Руйнування гіперпараметрів; хибна адаптація; 🟡 Medium  
  - Пріоритет: P2  
  - Рекомендоване виправлення: Ввести валідатори та межі, логи відсікання; тести на збереження валідних параметрів.  
  - Критерій «закрито»: Тести підтверджують збереження коректних значень  
  - Доказ: `reports/technical_debt_assessment.md:L17-L19`

- **TD-011 (code/data · Agents)**  
  - Власник: Agents  
  - Локація: `core/agent/memory.py`  
  - Опис / Причина: Сховище стратегії без виселення, ключ як кортеж float.  
  - Вплив / Ризик / Критичність: Витік пам’яті; крихкі пошуки; 🟡 Medium  
  - Пріоритет: P2  
  - Рекомендоване виправлення: Додати TTL/розмірні ліміти, нормалізувати ключі; тест на евікцію.  
  - Критерій «закрито»: Евікція працює у тесті, ключі стабільні  
  - Доказ: `reports/technical_debt_assessment.md:L19-L20`

- **TD-012 (code/data · Data)**  
  - Власник: Data  
  - Локація: `core/data/ingestion.py`  
  - Опис / Причина: CSV інжестор без валідації, припускає `ts/price`, має зайві імпорти.  
  - Вплив / Ризик / Критичність: Падіння при кривих даних; дані недостовірні; 🟠 High  
  - Пріоритет: P1  
  - Рекомендоване виправлення: Додати валідацію схем, обробку помилок, прибрати мертві імпорти; тести на невалідні рядки.  
  - Критерій «закрито»: Тести валідації проходять, імпорти чисті  
  - Доказ: `reports/technical_debt_assessment.md:L21-L23`

- **TD-013 (code/infra · Data)**  
  - Власник: Data  
  - Локація: `core/data/ingestion.py`  
  - Опис / Причина: WebSocket Binance повертається без керування життєвим циклом/реконекту.  
  - Вплив / Ризик / Критичність: Витік потоків; втрати даних; 🟡 Medium  
  - Пріоритет: P2  
  - Рекомендоване виправлення: Додати менеджер контексту/реконект, тест на graceful shutdown.  
  - Критерій «закрито»: Тест закриває клієнт без висяків  
  - Доказ: `reports/technical_debt_assessment.md:L22-L23`

- **TD-014 (code/backtest · Backtest)**  
  - Власник: Backtest  
  - Локація: `backtest/engine.py`  
  - Опис / Причина: `walk_forward` не звіряє довжину сигналів, неправильно застосовує fee.  
  - Вплив / Ризик / Критичність: Хибна метрика PnL; фінансовий ризик; 🟠 High  
  - Пріоритет: P1  
  - Рекомендоване виправлення: Валідувати довжину, коректно рахувати fee за нотою; додати тести.  
  - Критерій «закрито»: Тести перевіряють довжину та fee-розрахунок  
  - Доказ: `reports/technical_debt_assessment.md:L23-L25`

- **TD-015 (code/execution · Execution)**  
  - Власник: Execution  
  - Локація: `execution/order.py`  
  - Опис / Причина: Конфліктні формули позиціонування, risk параметр ігнорується.  
  - Вплив / Ризик / Критичність: Неправильний розмір позиції; фінансовий ризик; 🔴 Critical  
  - Пріоритет: P0  
  - Рекомендоване виправлення: Узгодити формулу, додати валідацію risk; покрити юніт-тестом.  
  - Критерій «закрито»: Тест підтверджує узгоджену формулу та risk вплив  
  - Доказ: `reports/technical_debt_assessment.md:L25-L27`

- **TD-016 (code/risk · Execution)**  
  - Власник: Execution  
  - Локація: `execution/risk.py`  
  - Опис / Причина: Heat сумує абсолютну ноту без напрямку/валюти.  
  - Вплив / Ризик / Критичність: Перекошені ризик-метрики; недооцінка ризику; 🟡 Medium  
  - Пріоритет: P2  
  - Рекомендоване виправлення: Врахувати side/FX/ваги; тести на long/short портфелі.  
  - Критерій «закрито»: Тест показує коректний heat для long/short  
  - Доказ: `reports/technical_debt_assessment.md:L27-L29`

- **TD-017 (code/ops · Indicators)**  
  - Власник: Indicators  
  - Локація: `core/indicators/ricci.py`, `core/indicators/temporal_ricci.py`  
  - Опис / Причина: Fallback без логів/попереджень при відсутності важких залежностей.  
  - Вплив / Ризик / Критичність: Тихе падіння якості; невидимі деградації; 🟡 Medium  
  - Пріоритет: P2  
  - Рекомендоване виправлення: Логувати деградацію, вимагати залежність або QA fallback; тест на повідомлення.  
  - Критерій «закрито»: Лог попереджає, тест перевіряє  
  - Доказ: `reports/technical_debt_assessment.md:L29-L31`

- **TD-018 (code/quality · Platform)**  
  - Власник: Platform  
  - Локація: `core/phase/detector.py` та ін.  
  - Опис / Причина: Залишкові імпорти/unused deps вказують на прогалини лінтингу.  
  - Вплив / Ризик / Критичність: Підвищений борг; шум у коді; 🟢 Low  
  - Пріоритет: P3  
  - Рекомендоване виправлення: Увімкнути/посилити лінт у цих шляхах, прибрати залишки.  
  - Критерій «закрито»: Лінт чистий, імпорти оптимізовані  
  - Доказ: `reports/technical_debt_assessment.md:L31-L33`

- **TD-019 (ci/security · DevEx/Security)**  
  - Власник: DevEx/Security  
  - Локація: `.github/workflows/*`  
  - Опис / Причина: 386 GitHub Actions (за даними `./AUDIT_REPORT.md`) не зафіксовані на SHA, використовують mutable теги.  
  - Вплив / Ризик / Критичність: Supply-chain ризик; компрометація CI; 🔴 Critical  
  - Пріоритет: P0  
  - Рекомендоване виправлення: Пришпилити всі дії на commit SHA, автоматизувати lint перевірку.  
  - Критерій «закрито»: CI проходить з pinned actions; workflow guard успішний  
  - Доказ: `./AUDIT_REPORT.md:L164-L193`

- **TD-020 (security/infra · Security)**  
  - Власник: Security  
  - Локація: `configs/tls/dev/*.pem`  
  - Опис / Причина: 4 dev TLS приватні ключі відстежуються у git.  
  - Вплив / Ризик / Критичність: Потенційний витік dev середовища; 🟠 High  
  - Пріоритет: P0  
  - Рекомендоване виправлення: Видалити ключі, замінити макетами, відкликати сертифікати; додати секрет-скани.  
  - Критерій «закрито»: Ключі видалені, нові видані, скан чистий  
  - Доказ: `./AUDIT_REPORT.md:L212-L233`

- **TD-021 (security/code · Security/Platform)**  
  - Власник: Security/Platform  
  - Локація: `audit/artifacts/bandit.json` (кодові шляхи)  
  - Опис / Причина: 5 Bandit MEDIUM (B104 bind all interfaces) та низькі B110/B101.  
  - Вплив / Ризик / Критичність: Підвищена поверхня атаки; config risk; 🟠 High  
  - Пріоритет: P1  
  - Рекомендоване виправлення: Усунути B104 (bind), додати логування для try/except, переглянути asserts; перезапустити Bandit.  
  - Критерій «закрито»: Bandit clean (MEDIUM=0); звіт оновлений  
  - Доказ: `./AUDIT_REPORT.md:L244-L252`

- **TD-022 (docs/process · Platform)**  
  - Власник: Platform  
  - Локація: `docs/POSTMORTEM_TEMPLATE.md`, `docs/DEPENDENCY_MANAGEMENT.md`, Terraform EKS модулі  
  - Опис / Причина: TODO/FIXME/XXX не пронумеровані у трекері.  
  - Вплив / Ризик / Критичність: Непрозорість боргу; ризик забути; 🟢 Low  
  - Пріоритет: P3  
  - Рекомендоване виправлення: Перенести TODO у задачі, видалити маркери з шаблонів/Infra.  
  - Критерій «закрито»: TODO відсутні або замінені посиланнями на задачі  
  - Доказ: TODO/TBD місця виявлені ріпгрепом
