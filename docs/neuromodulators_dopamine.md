# DopamineController v2.2

Нейроінспірований контур, що моделює апетитивну дофамінову петлю під TD(0):

- TD(0) RPE з числовими клампами та стабілізацією.
- Phasic/Tonic динаміка з експоненційним згладжуванням і насиченням `σ(k·(tonic−θ))`.
- Нормована температура політики `T` (безрозмірна, шкала `[min_temperature, ∞)`), яка зростає при негативному RPE.
- Go/No-Go рішення в парі з **ActionGate** для пріоритезації серотонінового HOLD.
- Метапараметричні дріфти з охолодженням (`meta_cooldown_ticks`) та табличними правилами (`meta_adapt_rules`).
- DDM-адаптер `adapt_ddm_parameters` → перетворює `dopamine_level` у дрейф/межу.
- Повна валідація YAML-конфігу (`version`, діапазони, невідомі ключі → помилка).
- Телеметрія з префіксом `dopamine_*`, частотний ред’юсер `metric_interval`.

## Приклад використання

```python
from tradepulse.core.neuro.dopamine import (
    ActionGate,
    DopamineController,
    adapt_ddm_parameters,
)

da = DopamineController("config/dopamine.yaml")
rpe = da.compute_rpe(r, V, V_next)
da.update_value_estimate(rpe)
app = da.estimate_appetitive_state(r_proxy, novelty, momentum, value_gap)
DA = da.compute_dopamine_signal(app, rpe)
Q_mod = da.modulate_action_value(Q)
gate = ActionGate(da, serotonin_ctrl)
gate_eval = gate.evaluate(DA)
ddm = adapt_ddm_parameters(gate_eval.dopamine_level, base_drift, base_boundary)
da.update_metrics()
```

## Конфігурація

- `discount_gamma ∈ (0,1]`, `learning_rate_v ∈ (0,1]`.
- `baseline`, `delta_gain`, `invigoration_threshold`, `no_go_threshold ∈ [0,1]`.
- `temp_k > 0`, `min_temperature > 0`, `burst_factor ≥ 0`.
- `meta_adapt_rules` задають мультиплікативні коефіцієнти для станів `good|bad|neutral`.
- `metric_interval` визначає частоту логування (`1` → кожен крок).

## Meta-adapt

- `good`: drawdown ≥ `target_dd` **та** Sharpe ≥ `target_sharpe` → збільшуємо `learning_rate_v`, `delta_gain`, охолоджуємо `base_temperature`.
- `bad`: drawdown < `target_dd` **та** Sharpe < `target_sharpe` → зменшуємо `learning_rate_v`, `delta_gain`, підіймаємо `base_temperature`.
- Після не-нейтрального переходу спрацьовує охолодження (`meta_cooldown_ticks`).

## Тести

```bash
pytest tests/test_dopamine_controller.py \
       tests/test_dopamine_step_extension.py \
       tests/test_action_gate.py \
       tests/test_ddm_adapter.py
```
