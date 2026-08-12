# DopamineController v2.3

Нейроінспірований TD(0) контур для апетитивної петлі з повною інтеграцією DDM, Go/Hold/No-Go керування та телеметрії.

## 1. Огляд архітектури

1. **TD(0) RPE** – `δ = r + γ · V' − V` із λ = 0 та насиченням `γ ∈ (0, 1]`.
2. **Phasic vs Tonic** – фазичний компонент `max(0, δ) · burst_factor`; тоніка – EMA апетитивного стану (`decay_rate`).
3. **Dopamine state** – сигмоїдальний перехід `σ(k · (tonic − θ))` з обмеженням логітів.
4. **Політика** – `modulate_action_value` масштабовує логіти, а `compute_temperature` задає температуру з урахуванням негативного RPE та DDM.
5. **Release gate** – дисперсія RPE (`rpe_ema_beta`) відкриває/закриває Go канал для safety.
6. **Meta-adapt** – Adam над базовою температурою (`temp_adapt_*`), керований `temp_adapt_target_var`.
7. **DDM coupling** – `ddm_thresholds(v, a, t0)` повертає масштаб температури та пороги Go/Hold/No-Go.
8. **ActionGate** – координує дофаміновий сигнал з серотоніновим HOLD та TACL-телеметрію.

## 2. Потік `step`

```text
estimate_appetitive_state → compute_rpe → update_value_estimate →
update_rpe_statistics → meta_adapt_temperature → update_release_gate →
compute_dopamine_signal → compute_temperature → (optional) ddm_thresholds →
policy modulation + gate synthesis → telemetry & extras
```

Метод `step(...) -> (rpe, temperature, policy_logits, extras)` повертає:

| Поле | Опис |
|------|------|
| `rpe` | TD(0) помилка з останнім застосованим `discount_gamma`. |
| `temperature` | Фінальна температура політики після DDM-скейлу. |
| `policy_logits` | Модульовані логіти політики (tuple). |
| `extras` | Діагностика: рівні DA, `rpe_variance`, release gate, пороги Go/Hold/No-Go, адаптивна база температури, `ddm_thresholds`. |

Ключові прапорці в `extras`:

- `release_gate_open`: `False` → ActionGate переходить у HOLD.
- `go`, `hold`, `no_go`: бульові рішення Go/Hold/No-Go.
- `adaptive_base_temperature`: нове значення після meta-adapt.
- `ddm_thresholds`: `DDMThresholds(temperature_scale, go_threshold, hold_threshold, no_go_threshold)`.

## 3. Приклад використання

```python
from geosync.core.neuro.dopamine import ActionGate, DopamineController

ctrl = DopamineController("config/dopamine.yaml")
app = ctrl.estimate_appetitive_state(r_proxy, novelty, momentum, value_gap)
rpe, temperature, policy_logits, extras = ctrl.step(
    reward=r,
    value=V,
    next_value=V_next,
    appetitive_state=app,
    policy_logits=raw_logits,
    ddm_params=(v_drift, boundary, non_decision),
)

thresholds = extras.get("ddm_thresholds")
gate = ActionGate(ctrl, serotonin_ctrl)
gate_eval = gate.evaluate(
    dopamine_signal=extras["dopamine_level"],
    thresholds=thresholds,
    release_gate_open=extras["release_gate_open"],
)
```

`extras` також містить `tonic_level`, `phasic_level`, `value_estimate`, `rpe_variance` та інші діагностичні величини для safety-логіки.

## 4. Конфігурація (`config/dopamine.yaml`)

| Блок | Параметри | Призначення |
|------|-----------|-------------|
| TD / Value | `discount_gamma`, `learning_rate_v` | TD(0) оцінка вартості. |
| DA динаміка | `decay_rate`, `burst_factor`, `k`, `theta` | Формування фазичної та тонічної компонент. |
| Appetitive weights | `w_r`, `w_n`, `w_m`, `w_v`, `novelty_mode`, `c_absrpe` | Баланс сигналів нагороди/новизни/інерції. |
| Action modulation | `baseline`, `delta_gain` | Перетворення логітів політики. |
| Temperature | `base_temperature`, `min_temperature`, `temp_k`, `neg_rpe_temp_gain`, `max_temp_multiplier` | Управління explore/exploit. |
| Gating | `invigoration_threshold`, `no_go_threshold`, `hold_threshold` | Границі Go/Hold/No-Go. |
| Meta rules | `meta_adapt_rules`, `target_dd`, `target_sharpe`, `meta_cooldown_ticks`, `metric_interval` | Мультиплікативні дріфти конфігурації. |
| Variance adapt | `rpe_ema_beta`, `temp_adapt_*`, `rpe_var_release_threshold`, `rpe_var_release_hysteresis` | EMA/Adam-петля температури + release gate. |
| DDM | `ddm_temp_gain`, `ddm_threshold_gain`, `ddm_hold_gain`, `ddm_min_temperature_scale`, `ddm_max_temperature_scale`, `ddm_baseline_a`, `ddm_baseline_t0`, `ddm_eps` | Проєкція `(v, a, t0)` у пороги та масштаб. |

Конфігурація проходить сувору валідацію: наявність усіх ключів, діапазони (`temp_adapt_min_base ≤ temp_adapt_max_base`, `discount_gamma ∈ (0, 1]`, `ddm_eps > 0` тощо) та відсутність сторонніх полів.

## 5. DDM та ActionGate

- `ddm_thresholds` обчислює `temperature_scale` та пороги з урахуванням дрейфу (`v`), межі (`a`) і небажаної затримки (`t0`).
- Пороги Go/No-Go обрізаються до `[0, 1]`; при `go_threshold < no_go_threshold` – усереднюються для стабільності.
- `ActionGate` поєднує дофаміновий сигнал з порогами DDM та серотоніновим HOLD (`SerotoninLike.check_cooldown`).
- Температура на виході гейту додатково враховує `temperature_floor` серотоніну та DDM-скейл.

## 6. Meta-adapt та release gate

1. `_update_rpe_statistics` підтримує EMA середнього та середнього квадрата RPE.
2. `_meta_adapt_temperature` застосовує Adam до базової температури, обмежуючи її у `[temp_adapt_min_base, temp_adapt_max_base]`.
3. `_update_release_gate` закриває Go при `variance > rpe_var_release_threshold` з гістерезисом.
4. `extras['adaptive_base_temperature']` відслідковує нову базу, а `extras['release_gate_open']` → `ActionGate.hold`.

## 7. Телеметрія

- `tacl.dopa.rpe`, `tacl.dopa.temp`, `tacl.dopa.ddm.bound` – основні показники для TACL.
- `dopamine_release_gate`, `dopamine_temperature`, `dopamine_tonic_level`, `dopamine_phasic_level` – допоміжні метрики для внутрішніх дашбордів.
- Логер передається через конструктор або використовується типовий TACL адаптер.

## 8. Тестування та валідація

Юніт- та property-тести (див. `tests/core/neuro/dopamine/`):

- Перевірка знаку TD(0) RPE та стабільності температури.
- Валідація release gate та meta-adapt температури (EMA + Adam).
- Моніторинг `ActionGate` для Go/Hold/No-Go та DDM-скейлу.
- Перевірка `ddm_thresholds` і `adapt_ddm_parameters` на монотонність та обмеження.

Запуск локального пакету тестів:

```bash
pytest tests/core/neuro/dopamine/test_dopamine_controller.py \
       tests/core/neuro/dopamine/test_action_gate.py \
       tests/core/neuro/dopamine/test_ddm_adapter.py
```

## 9. Повна характеристика поведінки

### 9.1. Базові стани

| Режим | Умови | Ознаки | Дії контролера |
|-------|-------|--------|----------------|
| **Тонічна стабільність** | `|δ| < tonic_band`, низька дисперсія RPE | `tonic_level` ≈ базовому, `release_gate_open = True` | Температура → `base_temperature`, Go активний, DDM масштабує мінімально. |
| **Фазична активація** | `δ > burst_threshold` | Високий `phasic_level`, `temperature` зростає в межах `max_temp_multiplier` | Гейт пропускає Go, `ddm_thresholds.temperature_scale` підсилює експлорацію. |
| **Інгібіція / No-Go** | `δ < 0` та `release_gate_open = False` чи `go_threshold` < `no_go_threshold` | Зростає `no_go` прапорець, `temperature` → `min_temperature` | ActionGate примушує HOLD/No-Go до відновлення варіації. |

### 9.2. Динаміка TD(0) RPE

1. `compute_rpe` оцінює `δ` у межах `[-rpe_clip, rpe_clip]` для запобігання вибухам.
2. Експоненційне згладжування (`rpe_ema_beta`) відстежує середнє та дисперсію, які керують release gate.
3. Позитивні `δ` підсилюють фазичну компоненту (`burst_factor`), негативні — знижують температуру через `neg_rpe_temp_gain`.
4. Стійке відхилення `δ` запускає `meta_adapt_rules` (Sharpe/DD) для корекції `base_temperature`.

### 9.3. Інтеграція з DDM та Go/No-Go

- Drift-diffusion параметри `(v, a, t0)` конвертуються у `DDMThresholds`, що модулюють як температуру, так і граничні значення Go/Hold/No-Go.
- Якщо `v` зменшується, `temperature_scale` → `ddm_min_temperature_scale`, що знижує активність Go.
- `ActionGate.evaluate` поєднує `release_gate_open`, `ddm_thresholds` і серотоніновий HOLD, забезпечуючи каскад: `Go → Hold → No-Go`.
- При конфліктах (`go_threshold < hold_threshold`) спрацьовує нормалізація й усереднення для стабільного рішення.

### 9.4. Крайові сценарії та захисти

- **Variance spike**: якщо `rpe_variance` перевищує `rpe_var_release_threshold`, Go блокується до спадання нижче гістерезису.
- **Cold-start**: при відсутності історії EMA ініціалізується `temp_adapt_init_var`, температура залишається біля бази до накопичення статистики.
- **DDM saturation**: `ddm_threshold_gain` обмежений `ddm_max_temperature_scale`; при насиченні температура обрізається до `max_temp_multiplier * base_temperature`.
- **Telemetry fail-safe**: відсутність телеметрії → використання стандартного логера та дублювання ключових метрик у `extras` для дебагу.

### 9.5. Метрики спостереження

- `dopamine_rpe_mean`, `dopamine_rpe_var` – контроль стабільності TD(0) оновлень.
- `dopamine_temperature`, `adaptive_base_temperature` – динаміка explore/exploit.
- `dopamine_gate_state` (Go/Hold/No-Go) – частоти переходів та латентність відновлення після блокувань.
- `ddm_temperature_scale`, `ddm_go_threshold` – синхронізація з поведінкою DDM.
- `safety.release_gate_closures` – кількість спрацювань захисту за інтервал.

Регулярний аналіз цих метрик дозволяє профілювати поведінку петлі, виявляти деградації (запізнення реакції, надмірне блокування Go) та адаптувати `meta_adapt_rules` без ризику для торговельних політик.

## Release gate & TACL

- `rpe_variance` оцінюється через EMA (`rpe_ema_beta`). При перевищенні `rpe_var_release_threshold` Go/Hold переводиться у HOLD (`release_gate_open = False`).
- Метрики TACL: `tacl.dopa.rpe`, `tacl.dopa.temp`, `tacl.dopa.ddm.bound`, `dopamine_release_gate`.
- Використовуйте `extras["release_gate_open"]` для інтеграції із зовнішніми safety-гейтми.
