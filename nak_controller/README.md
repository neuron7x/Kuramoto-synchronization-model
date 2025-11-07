# NaK Neuro‑Energetic Controller v2.1

Енергетичний гомеостаз поверх стратегій (як "нейронів") з PI‑контролем, нейромодуляторами (DA/NA/5‑HT/ACh), глобальними режимами (GREEN/AMBER/RED) та інваріантами безпеки.

## Що нового у v2.1
- Нелінійний PI (`tanh`) + anti‑windup, розширення діапазону EI за режимом.
- NA‑scaled волатильність у навантаженні та енергії.
- DA‑boost енергії для позитивного неочікуваного reward.
- Енергетичний борг і регенерація, шумова ін’єкція, гістерезис відновлення.
- Rate‑limit на зміну ризику, частотний менеджмент, повні тести/CI.

## Інваріанти
- `E ∈ [0, E_max]`, `EI ∈ [0,1]`, `L ∈ [L_min, L_max]`.
- `I ∈ [−I_max, I_max]` (anti‑windup).
- `risk_per_trade_factor ∈ [r_min, r_max]` і **rate‑limit** на крок.
- `mode=RED ⇒ risk_mult=0` або `suspend=True`.
- Unsuspend тільки при `EI ≥ EI_crit + EI_hysteresis`.

## Швидкий старт
```bash
python -m nak_controller.cli.run_validate --config nak_controller/conf/nak.yaml --steps 1600 --seeds 8
pytest -q nak_controller/tests/test_nak.py
```

## Інтеграція в TradePulse

```python
from nak_controller.integration.hook import NaKHook
nak = NaKHook("nak_controller/conf/nak.yaml")
limits = nak.compute_limits(
    strategy_id="alpha_1",
    local_obs=local_dict,    # trades, pnl, local_vol, local_dd, ...
    global_obs=global_dict,  # global_vol, portfolio_dd, exposure, unexpected_reward
    risk_per_trade_base=0.002,
    max_position_base=1.0,
    cooldown_ms_base=2000,
)
```

## Мапінг до TACL

* `risk_per_trade_factor → temperature`
* `health/EI → coupling` / throttle
* `is_suspended → hot‑swap off`

## Телеметрія (простий приклад)

На інтеграційному рівні логуй `{"EI", "E", "L", "risk_factor", "mode"}` до CSV/Prometheus.
