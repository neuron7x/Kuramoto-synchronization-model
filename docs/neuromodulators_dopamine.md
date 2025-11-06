# DopamineController

Біологічно натхнений контур для адаптивної політики:
- TD(0) RPE
- Фазичний (phasic) та тонічний (tonic) рівні
- Логістична нормалізація DA
- Модуляція дії та температури (explore/exploit)
- Go / No-Go евристики
- Meta-adapt за Sharpe / Drawdown
- Опціональна новизна через |RPE|

## Використання

```python
from tradepulse.core.neuro.dopamine import DopamineController

da = DopamineController("config/dopamine.yaml")
rpe = da.compute_rpe(r, V, V_next)
da.update_value_estimate(rpe)
app = da.estimate_appetitive_state(r_proxy, novelty, momentum, value_gap)
DA = da.compute_dopamine_signal(app, rpe)
Q_mod = da.modulate_action_value(Q)
T = da.compute_temperature()
go = da.check_invigoration()
no_go = da.check_suppress()
da.update_metrics()
```

## Meta-adapt

Підвищує `learning_rate_v` і `delta_gain`, знижує `base_temperature` при одночасно добрих Sharpe & Drawdown, і навпаки при поганих.

## Тести

Запуск:
```bash
pytest -k dopamine_controller
```
