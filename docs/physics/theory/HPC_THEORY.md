# HPC Theory Boundary

## Scope

This contract covers numerical reproducibility, finite-output guarantees, and state-envelope integrity for GeoSync HPC components.

## Model

A deterministic numerical kernel must produce identical output for identical inputs on fixed hardware. Finite admissible inputs must not produce NaN or infinity unless the contract explicitly defines that failure mode.

## Invariants

- INV-HPC1: seeded kernels are reproducible bit-for-bit on fixed hardware.
- INV-HPC2: finite inputs inside the documented range produce finite outputs.
- INV-HPC3: fixed-point ledger conservation holds inside the integer envelope.
- INV-HPC4: runtime-state envelopes reject tampering and schema drift.
- INV-HPC5: session lifecycle is a total finite-state machine over its declared state/action surface.

## Witness rules

Tests must pin seeds, dtypes, payloads, schema versions, and numerical tolerances. Cross-ISA tolerances must be declared separately from same-hardware reproducibility.

## Boundary

These invariants prove local deterministic contracts, not cluster-scale performance, GPU portability, or economic correctness. Performance and market claims require separate benchmark and audit artifacts.
