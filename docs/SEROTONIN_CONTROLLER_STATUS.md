# Serotonin Controller Status

**Date**: 2025-11-10  
**Status**: Active research component (sandbox-first)  
**Controller Version**: not declared in code (document-only label)

---

## Overview

The serotonin controller provides a neuromodulator-inspired gating mechanism for strategy and risk heuristics. It is intended for research and simulation workflows; live trading usage should remain in sandboxes or paper-trading environments.

---

## Implemented mechanisms (code paths)

- `core/neuro/serotonin/serotonin_controller.py` — state machine and modulation logic
- `core/neuro/serotonin/profiler/behavioral_profiler.py` — profiling utilities
- `core/neuro/serotonin/profiler/cli.py` — CLI entrypoint for profiling
- `core/neuro/tests/test_serotonin_controller.py` — internal tests covering core behaviors
- `examples/serotonin_validation_demo.py` — scenario walkthrough for manual review

---

## Engineering abstraction disclaimer

- The controller is a simplified control abstraction inspired by neuromodulator terminology; it does **not** model biological serotonin.
- Default parameters are tuned for demonstrations and may require reconfiguration for different strategies or data characteristics.
- Trading hooks are provided for stress-testing; they are not positioned as a production-grade risk engine.

---

## Known limitations

- Optional dependencies (e.g., PyTorch) may be required for certain pathways and are not bundled by default.
- Performance and stability are sensitive to configuration; thresholds are illustrative and not externally audited.
- Integration with live trading paths is not continuously exercised; keep deployments behind feature flags and manual review.

---

## Testing and validation notes

- Internal tests exist in `core/neuro/tests/test_serotonin_controller.py`; pass counts depend on environment and optional dependencies.
- The validation demo (`examples/serotonin_validation_demo.py`) offers scenarios for manual inspection rather than formal certification.
