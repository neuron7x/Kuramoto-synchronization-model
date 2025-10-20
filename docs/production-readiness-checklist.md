# Production Readiness: E2E replayable live-sim checklist

Цей документ описує, що повинен покривати e2e тест, щоб підвищити readiness.

Core checks:
- [ ] Deterministic backtest with fixed seed produces stable signals.
- [ ] Signals can be exported and replayed without mutation.
- [ ] Live runner accepts pluggable exchange adapter (production adapter і fake one).
- [ ] FakeExchange supports latency, jitter, failures, disconnects.
- [ ] Risk controls (max position, max drawdown, circuit breaker) перевіряються під навантаженням і при помилках.
- [ ] Тест виконується в CI; провал тесту блокує merge.
- [ ] Логи та artifact'и (backtest report, live report, signals JSON) прикріпляються до CI run для дебагу.
- [ ] Тест має timeout і не флейкить у >1% прогонів.
- [ ] Документація "how to run locally" та "explain failure modes" присутня.
