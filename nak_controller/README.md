# NaK Neuro‑Energetic Controller v2.0

Біоінспірований контролер енергетичного гомеостазу для мультистратегічних
систем трейдингу. Нелінійний PI з `tanh`, нейромодулятори (DA/NA/5‑HT/ACh),
глобальні режими (GREEN/AMBER/RED), rate-limit на зміну ризику та сувора
перевірка інваріантів.

## Швидкий старт

```bash
python -m nak_controller.cli.run_validate --config nak_controller/conf/nak.yaml --steps 1600 --seeds 8
pytest -q nak_controller/tests/test_nak.py
mypy nak_controller
```

## Інтеграція з TradePulse

```python
from nak_controller.integration.hook import NaKHook

hook = NaKHook("nak_controller/conf/nak.yaml", seed=2024)

def apply_limits(signal, local_obs, global_obs):
    limits = hook.compute_limits(
        strategy_id=signal.strategy_id,
        local_obs=local_obs,
        global_obs=global_obs,
        risk_per_trade_base=signal.risk_per_trade,
        max_position_base=signal.max_position,
        cooldown_ms_base=signal.cooldown_ms,
    )
    signal.risk_per_trade = signal.risk_per_trade * limits.risk_per_trade_factor
    signal.max_position = signal.max_position * limits.max_position_factor
    signal.cooldown_ms = limits.cooldown_ms
    signal.suspended = limits.is_suspended
    return limits
```

## Метрики та одиниці

| Метрика                  | Одиниці                  | Діапазон | Примітка |
|--------------------------|--------------------------|----------|----------|
| `trades`                 | нормалізовані (0-1)      | [0, 1]   | частота угод на кроці |
| `pnl`                    | частка equity            | [-1, 1]  | масштабується `pnl_scale` |
| `local_vol`              | нормалізована волатильність | [0, 1] | після NA-скейлу |
| `local_dd`               | локальний drawdown       | [0, 1]   | оновлюється симуляцією |
| `tech_errors`, `latency`, `slippage` | нормалізовані | [0, 1] | показники якості виконання |
| `EI`                     | безрозмірний             | [0, 1]   | індекс енергії |
| `risk_per_trade_factor`  | множник ризику           | [r_min, r_max] | rate-limit 0.20 |
| `cooldown_ms`            | мс                       | ≥ ⌊base/f_max⌋ | anti-thrashing |

## Параметри конфігурації

| Параметр        | Значення | Опис |
|-----------------|----------|------|
| `L_min/L_max`   | 0.0 / 1.0 | межі навантаження |
| `E_max`         | 1.0      | максимальна енергія |
| `EI_low/high`   | 0.35 / 0.65 | робочий діапазон |
| `EI_crit`       | 0.15     | поріг suspend |
| `EI_hysteresis` | 0.05     | запас для unsuspend |
| `r_min/r_max`   | 0.2 / 1.8 | обмеження ризику |
| `f_min/f_max`   | 0.25 / 1.50 | межі частоти |
| `delta_r_limit` | 0.20     | rate-limit на крок |
| `band_expand`   | 1.0 / 1.25 / 1.5 | розширення діапазону EI для GREEN/AMBER/RED |
| `risk_mult`     | 1.0 / 0.65 / 0.0 | множники ризику |
| `activity_mult` | 1.2 / 0.9 / 0.6 | множники активності |

## Безпекові інваріанти

- `E`, `L`, `EI` жорстко обмежені конфігом; debt-менеджмент не допускає від’ємної енергії.
- `risk_per_trade_factor == max_position_factor` та завжди в `[r_min, r_max]`.
- Режим RED гарантує `is_suspended` **або** `risk_mult=0` (контролюється assert).
- `cooldown_ms ≥ floor(base/f_max)` запобігає перегріву.
- `NaKController.reset()` скидає стани та RNG для повторюваних тестів.

## Телеметрія

Логування у форматі JSONLines з ключами `EI`, `E`, `L`, `mode`, `dopamine`,
`noradrenaline`, `serotonin`, `acetylcholine`, `risk_factor`, `cooldown_ms`.

```json
{"strategy": "alpha_1", "EI": 0.52, "E": 0.63, "L": 0.41, "mode": "GREEN", "risk_factor": 0.98}
```

## Відомі trade-offs

- Нижчі множники в RED різко обнуляють ризик, що зменшує дохідність під час
  коротких просідань, але гарантує дотримання інваріантів.
- Шум у `update_load` зменшує застої, але потребує фіксованого seed для
  відтворюваності.
- Додаткова перевірка конфіга через Pydantic збільшує час старту (~3‑4 мс),
  але відсікає некоректні налаштування на ранньому етапі.

## Документація API

- `NaKHook.compute_limits` повертає `NaKStepOutput` з усіма лімітами і
  діагностикою. Для сумісності з попереднім API використовуйте
  `compute_limits_dict()`.
- `nak_controller.cli.run_validate` та `nak_controller.cli.run_cv` доступні як
  консольні скрипти `nak-validate` та `nak-cv`.

