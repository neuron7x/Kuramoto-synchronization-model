# RIEE Commercial Automation Matrix (2026-05-26)

## Executive axes
- **Ціна 💸**: `$4,900 / month` стартовий production-пакет RIEE Enterprise.
- **Терміновість 🔴**: `RED` — запуск guardrails блокує latent drift до інциденту.
- **Довіра ✅**: `VERIFIED` — claim hashes + drift checks + runtime panic/quarantine.
- **Пакет 📦**: `RIEE_ENTERPRISE` (CI guardians, runtime SDK, telemetry, quarantine).
- **Автоматизація ⚙️**: `92%` ключових перевірок автоматизовано через CI/pre-commit/runtime guards.
- **Продаж 📈**: `READY_FOR_PILOT` — готово до 1 production stream.
- **Дія 💬**: Запустити `fail_closed_guardians` та підключити перший контур даних.

## Machine artifact
Scorecard генерується скриптом:

```bash
python scripts/riee/package_scorecard.py
```

Output:
- `artifacts/riee_offering_scorecard.json`
