# GABA Inhibition Gate — Physics Contract

> Ground truth for GABA position gate in GeoSync.
> Module: core/neuro/gaba_position_gate.py

## 1. The Model

GABAergic inhibition (Mink 1996): motor cortex output is tonically inhibited
by basal ganglia. Action requires active disinhibition. GeoSync maps this to:
high volatility → strong inhibition → reduced position.

### Gate function:

    inhibition = σ(k · (input - θ))

where:
- σ = sigmoid: 1/(1+e^{-x})
- input = composite volatility signal (VIX, realized vol, etc.)
- k = steepness (sensitivity)
- θ = threshold (center of sigmoid)

### Position modulation:

    effective_position = raw_position × (1 - inhibition)

When inhibition → 1: position → 0 (full inhibition)
When inhibition → 0: position unchanged (disinhibited)

## 2. Physics Invariants

### INV-GABA1: Gate output bounds
    inhibition ∈ [0, 1] for all inputs
    Type: UNIVERSAL
    Proof: sigmoid range is (0, 1), which is subset of [0, 1]
    Falsification: inhibition < 0 or inhibition > 1

### INV-GABA2: Monotonicity in volatility
    Higher volatility → higher or equal inhibition
    (sigmoid is monotonically increasing in its argument)
    Type: QUALITATIVE
    Falsification: vol₁ > vol₂ but inhibition(vol₁) < inhibition(vol₂)

### INV-GABA3: Position reduction
    effective_position ≤ raw_position (inhibition can only reduce, not amplify)
    Type: UNIVERSAL (assuming inhibition ≥ 0)
    Falsification: effective_position > raw_position

### INV-GABA4: Zero volatility limit
    When vol → 0: inhibition → σ(-k·θ) ≈ 0 for typical θ > 0
    (system should be mostly disinhibited in calm markets)
    Type: ASYMPTOTIC

### INV-GABA5: Extreme volatility limit
    When vol → ∞: inhibition → 1 (full inhibition)
    Type: ASYMPTOTIC

## 3. What Tests MUST Check

### P0 (blocks merge):
- inhibition ∈ [0, 1] for random inputs (property test)
- effective_position ≤ raw_position always
- Higher vol → higher inhibition (monotonicity)

### P1:
- Low vol → low inhibition (near zero)
- Extreme vol → inhibition near 1
- Steepness k affects transition sharpness

### Anti-patterns:
- Testing inhibition == exact_float (sigmoid is continuous, exact values
  depend on config params k, θ)
- Forgetting that sigmoid is never exactly 0 or 1 (only approaches)
