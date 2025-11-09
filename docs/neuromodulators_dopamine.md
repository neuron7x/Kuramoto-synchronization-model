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
from tradepulse.core.neuro.dopamine import ActionGate, DopamineController

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

## Release gate & TACL

- `rpe_variance` оцінюється через EMA (`rpe_ema_beta`). При перевищенні `rpe_var_release_threshold` Go/Hold переводиться у HOLD (`release_gate_open = False`).
- Метрики TACL: `tacl.dopa.rpe`, `tacl.dopa.temp`, `tacl.dopa.ddm.bound`, `dopamine_release_gate`.
- Використовуйте `extras["release_gate_open"]` для інтеграції із зовнішніми safety-гейтми.
