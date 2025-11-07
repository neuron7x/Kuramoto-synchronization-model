# Summary
Production-grade оновлення `MisanthropicAgent`:
- Lagrangian **CVaR** у QR-DQN update (м'яке обмеження хвоста).
- **PER** (proportional) + IS-ваги; пріоритезація за |TD|.
- **EnbPI coverage каркас**: online residuals + тригер адаптації.
- **OOD** (rolling **KS**) → size-gating/HOLD.
- **Context slot** (мінімальний провайдер autocorr).

# How to
```python
from runtime.misanthropic_agent import MisanthropicAgent
agent = MisanthropicAgent()
agent.train(env, episodes=100)
a, size = agent.step(lob_data, price)
```

# Notes

* EnbPI тут — каркас; заміни джерело residuals на твій TS-предиктор.
* Ансамблі тренуються в `repose()` на батчі (bootstrapped).
* A/B: hard-CVaR gate (runtime) vs Lagrangian-CVaR (training).
