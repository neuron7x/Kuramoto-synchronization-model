# DopamineController v2.3

Нейроінспірований TD(0) контур зі стабільною дофаміновою петлею та Go/Hold/No-Go керуванням:

- **TD(0) RPE**: `δ = r + γ·V' − V` (λ=0) із перевіркою діапазону `γ`.
- **Phasic/Tonic**: фазичний сплеск `max(0, δ)·burst_factor` і тоніка як EMA апетитивного стану.
- **Step API**: `step(...) -> (rpe, temperature, policy_logits, extras)` виконує повний цикл (TD, DA, температура, release gate, DDM).
- **DDM адаптація**: `ddm_thresholds(v, a, t0)` повертає масштаб температури й пороги Go/Hold/No-Go для дій та `ActionGate`.
- **Meta-adapt температури**: Adam над дисперсією RPE (`rpe_ema_beta`, `temp_adapt_*`) + variance release gate.
- **ActionGate**: коригує температуру, синхронізує HOLD із серотоніном, блокує виконання при перевищенні дисперсії.
- **Телеметрія TACL**: `tacl.dopa.rpe`, `tacl.dopa.temp`, `tacl.dopa.ddm.bound` + `dopamine_release_gate` для dashboards.
- **Повна YAML-валідація**: усі сталі конфігурації (`config/dopamine.yaml`) перевіряються при старті.

## Приклад використання

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

`extras` також містить `tonic_level`, `phasic_level`, `adaptive_base_temperature`, `rpe_variance` та прапорець `release_gate_open` для побудови safety-логіки.

## Конфігурація (config/dopamine.yaml)

| Блок | Поля | Опис |
|------|------|------|
| TD / Value | `discount_gamma`, `learning_rate_v` | TD(0) оновлення цінності. |
| DA динаміка | `decay_rate`, `burst_factor`, `k`, `theta` | Фазичний і тонічний рівні. |
| Температура | `base_temperature`, `min_temperature`, `temp_k`, `neg_rpe_temp_gain`, `max_temp_multiplier` | Експлорація/експлуатація. |
| Гейти | `invigoration_threshold`, `no_go_threshold`, `hold_threshold` | Go/Hold/No-Go пороги. |
| Meta rules | `meta_adapt_rules`, `target_dd`, `target_sharpe`, `meta_cooldown_ticks` | Повільні мультиплікативні дріфти. |
| Variance adapt | `rpe_ema_beta`, `temp_adapt_*`, `rpe_var_release_*` | EMA + Adam оновлення температури. |
| DDM | `ddm_*` | Перетворення `(v, a, t0)` у `temperature_scale` і пороги. |

Конфігурація проходить сувору перевірку (наявність ключів, межі, `temp_adapt_min_base ≤ temp_adapt_max_base`, додатність `ddm_eps` тощо). Будь-які невідомі ключі викликають `ValueError`.

## Release gate & TACL

- `rpe_variance` оцінюється через EMA (`rpe_ema_beta`). При перевищенні `rpe_var_release_threshold` Go/Hold переводиться у HOLD (`release_gate_open = False`).
- Метрики TACL: `tacl.dopa.rpe`, `tacl.dopa.temp`, `tacl.dopa.ddm.bound`, `dopamine_release_gate`.
- Використовуйте `extras["release_gate_open"]` для інтеграції із зовнішніми safety-гейтами.

## Тести

```bash
pytest tests/core/neuro/dopamine/test_dopamine_controller.py \
       tests/core/neuro/dopamine/test_action_gate.py \
       tests/core/neuro/dopamine/test_ddm_adapter.py
```
