# Summary
Production-grade апдейт `MisanthropicAgent` + термодинамічний місток:
- Детермінований seed/device pipeline, gradient clipping та AdamW для стабільності.
- CVaR-Lagrangian + PER перераховані з IS-вагами, ensemble-UQ, telemetry hook.
- TACL feedback: `ThermoController.broadcast_agent_feedback()` + runtime agent registry.
- EnbPI coverage каркас, rolling KS OOD, ризик-гейти → адаптивний position sizing.

# How to
```python
from runtime.misanthropic_agent import MisanthropicAgent
from runtime.thermo_controller import ThermoController

agent = MisanthropicAgent()
controller = ThermoController(graph)
hook = controller.bind_agent("misanthropic", agent)

agent.train(env, episodes=100)
action, size = agent.step(lob_data, price)
```

# Notes

* `hook(metrics)` публікується агентом автоматично; TACL коригує λ та capital.
* Registry: `core.agent.global_agent_registry().resolve("misanthropic")` → фабрика.
* EnbPI лишається каркасом — під’єднай власний TS-предиктор.
