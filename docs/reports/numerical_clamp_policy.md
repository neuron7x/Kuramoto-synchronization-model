<!--
Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
SPDX-License-Identifier: MIT
-->
# Numerical Clamp Policy Report (P0-5)

Deterministic audit of silent numerical clamps in the scoped physics tree,
produced by `tools/physics/check_silent_clamps.py`. Policy:
[`docs/physics/numerical_policy.md`](../physics/numerical_policy.md). Registry:
[`tools/physics/clamp_registry.yaml`](../../tools/physics/clamp_registry.yaml).

## Scope

- `core/kuramoto`
- `core/physics`
- `core/indicators`
- `core/config/kuramoto_ricci.py`

## Result

- Clamp sites detected: **172**
- Distinct `path:line` keys registered: **169**
- Unregistered violations: **0**
- Stale registrations: **0**
- Clamp classes: **8**
- Physics source files touched by a clamp: **47**

## Clamp sites by class

| clamp class | sites |
| --- | ---: |
| `abs_sign_loss` | 10 |
| `cap_minimum` | 3 |
| `epsilon_add` | 15 |
| `floor_builtin` | 23 |
| `floor_maximum` | 34 |
| `nan_repair` | 18 |
| `saturate_clip` | 55 |
| `symmetrise` | 14 |

## Verification

```
python tools/physics/check_silent_clamps.py        # -> RESULT: PASS, exit 0
pytest -q tests/tools/test_numerical_policy.py
```

