# NaK Neuro-Energetic Controller v2.1

Енергетичний гомеостаз поверх стратегій («нейронів») з нелінійним PI-контуром, 
нейромодуляцією (DA/NA/5-HT/ACh), глобальними режимами (GREEN/AMBER/RED) та 
жорсткими інваріантами безпеки.

## Нове у v2.1
- Нелінійний PI (tanh) з anti-windup і режимним розширенням EI-зони.
- NA-scaled волатильність; DA-boost енергії; енергетичний борг/регенерація; шум.
- Hysteresis на відновлення, rate-limit ризику, `reset()` для детермінізму.
- Повний набір тестів + CLI + CI-конвеєр.

## Інваріанти
- `E ∈ [0, E_max]`, `EI ∈ [0, 1]`, `L ∈ [L_min, L_max]`.
- `I ∈ [−I_max, I_max]`, `risk ∈ [r_min, r_max]` + rate-limit.
- Режим RED ⇒ `risk_mult = 0` або `is_suspended = True`.
- Unsuspend лише при `EI ≥ EI_crit + EI_hysteresis`.

## Швидкий старт
```bash
python -m nak_controller.cli.run_validate --config nak_controller/conf/nak.yaml --steps 1600 --seeds 8
pytest -q nak_controller/tests
```

## Інтеграція
```python
from nak_controller.integration.hook import NaKHook

nak = NaKHook("nak_controller/conf/nak.yaml")
limits = nak.compute_limits("alpha_1", local_dict, global_dict, 0.002, 1.0, 2000)
```

## Мапінг до TACL
`risk_per_trade_factor → temperature`, `health/EI → coupling`, `is_suspended → hot-swap off`.
