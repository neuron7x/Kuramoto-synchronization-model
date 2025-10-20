# Інтеграційний тест: replayable live-sim — інструкція

Мета:
- Прогнати backtest → зберегти сигнали → прогнати live-runner з FakeExchangeAdapter → перевірити коректність PnL/позицій/ризик‑гейтів.

Як запускати:
1. Запустити:
   pytest tests/integration/test_e2e_replay_live_sim.py -m integration -q
2. Логи тесту міститимуть backtest report, live runner report і порівняльні метрики (див. ``tmp_path`` артефакти при DEBUG_E2E=1).
3. Якщо потрібен детальніший дебаг — встановити ENV ``DEBUG_E2E=1``.
