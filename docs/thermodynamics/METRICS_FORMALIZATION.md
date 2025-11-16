# Thermodynamics Metrics Formalization

## Overview

This document formalizes the mathematical foundations and computational procedures for the Thermodynamic Autonomic Control Layer (TACL) metrics system in TradePulse.

## Helmholtz Free Energy

The core metric in TACL is the Helmholtz free energy **F**, defined as:

```
F = U - T·S
```

Where:
- **F**: Free energy (dimensionless, target: F ≤ 1.35)
- **U**: Internal energy (system inefficiency penalties)
- **T**: Control temperature (fixed at 0.60 for TradePulse)
- **S**: Stability (entropy proportional to available headroom)

### Physical Interpretation

- **Low F**: System operates efficiently with ample headroom
- **High F**: System approaches instability, requires intervention
- **ΔF/Δt < 0**: Energy descent (desired, system improving)
- **ΔF/Δt > 0**: Energy ascent (warning, may trigger circuit breaker)

## Internal Energy (U)

Internal energy represents the aggregate penalty from system inefficiencies.

## References

- Friston, K. (2010). The free-energy principle: a unified brain theory?
- Helmholtz, H. (1882). Die Thermodynamik chemischer Vorgänge
- TradePulse TACL specification: `docs/TACL.md`
- Energy validator implementation: `runtime/energy_validator.py`
- Controller implementation: `runtime/thermo_controller.py`
