# TradePulse Architecture Map (Canonical Code Root)

## Canonical package
- **Root:** `src/tradepulse`
- **Import prefix:** `import tradepulse...`
- **Purpose:** Single source of truth for runtime, controllers, SDKs, and services.

## Legacy packages
- **`core/` (deprecated):** Thin shims that forward to `tradepulse.core.*`. Kept for backward compatibility only.
- **`tradepulse/` (repository root):** Shim that forwards to `src/tradepulse` to keep existing tooling working during transition.

## Subsystem map
- **Serotonin (TACL/5-HT):** `src/tradepulse/core/neuro/serotonin/` (legacy shim: `core/neuro/serotonin/`)
- **Thermo / TACL:** `runtime/` (API + controller), bridged through canonical runtime entrypoint
- **TACL Behavior Contracts:** `tacl/` (unchanged)
- **NAK controller:** `nak_controller/`
- **Neurotrade / Cortex:** `cortex_service/` and `tradepulse/neural_controller/` (shimmed via canonical root)
- **Risk/Execution:** `application/`, `execution/`, `runtime/`
- **Observability:** `observability/`
- **Experimental/Sandbox:** `sandbox/`, `examples/`

## Guidance
- New code MUST import from `tradepulse...`.
- Legacy imports under `core...` are deprecated and emit warnings; they resolve to the canonical modules where possible.
- See README for canonical run command and import examples.
