# NaK Neuro-Energetic Controller

NaK is a neuro-inspired limit controller designed for multi-strategy trading
systems. It fuses local trading telemetry with global risk indicators to
produce dynamic risk, position and frequency limits. The implementation ships
with:

- Deterministic energy/load dynamics suitable for offline validation.
- Dopamine / noradrenaline inspired neuromodulator hooks for adaptive behaviour.
- Synthetic validation utilities and CLI wrappers for continuous verification.

## Quick start

```bash
python -m pip install -e .
python -m nak_controller.cli.run_validate --config nak_controller/conf/nak.yaml --steps 200 --seeds 2
```

## Layout

- `core/` – state machines, configuration and energetic models.
- `control/` – PI control loop and neuromodulator adjustments.
- `runtime/` – orchestration logic combining observations and limits.
- `integration/` – `NaKHook` adapter for TradePulse integration points.
- `validate/` – simulation environment and validation harness.
- `cli/` – runnable entry points for validation and sweeps.
- `tests/` – unit coverage for deterministic behaviour and CLI guarantees.

## Testing

Run the dedicated test suite via:

```bash
pytest nak_controller/tests
```

The validation CLI emits deterministic JSON summaries to ease automation and
reporting.
