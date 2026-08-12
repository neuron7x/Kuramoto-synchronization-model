# Cryptobiosis Theory — Phase-Transition Survival

## Biological basis

Tardigrades survive lethal conditions (vacuum, radiation, -272°C, 150°C)
not by resisting them but by **exiting the space where the threat applies**:
vitrifying into a tun state where metabolism drops to zero.

Key properties:
- **O(1) transition**: vitrification is a phase transition, not a gradual process
- **Zero metabolism in dormant state**: not "reduced" — zero
- **Snapshot recovery**: the tun contains all information needed to resume
- **Staged rehydration**: recovery is cautious, multi-phase, abortable
- **Hysteresis**: exit threshold < entry threshold (prevents oscillation)

## GeoSync implementation

State machine: ACTIVE → VITRIFYING → DORMANT → REHYDRATING → ACTIVE

Combined neuromodulator distress T ∈ [0, 1]:
    T = 1 - GVS_score (where GVS = Gradient Vital Signs)

When T ≥ entry_threshold (default 0.85):
- System vitrifies in ONE tick (O(1))
- Position multiplier drops to EXACTLY 0.0
- Snapshot is captured for recovery

When T < exit_threshold (default 0.60):
- Rehydration begins (staged ramp-up)
- If T ≥ entry during rehydration → abort back to DORMANT

## Why this matters for trading

Traditional risk management: "reduce position by X% when vol > Y."
This RESISTS the threat — still in the space, still losing money slower.

Cryptobiosis: "exit ALL positions when gradient collapses."
This EXITS the space — zero exposure, zero P&L, wait for recovery.

The key insight: the cost of being in DORMANT during a false alarm
(missed opportunity) is bounded and recoverable. The cost of being
ACTIVE during a true crisis (unbounded loss) is not.

DORMANT multiplier = 0.0 EXACTLY is a SAFETY INVARIANT (INV-CB1).
Not 0.001. Not "close to zero." Zero. Because a discharged gradient
computing its own disappearance is worse than zero.

## Connection to Gradient Ontology (CLAUDE.md Section 0)

Layer 3 of the maintenance hierarchy: Gradient Preserved.
When Layers 0-2 fail (gradient gone, Lyapunov diverging, GABA saturated),
Layer 3 fires: exit the space entirely.

## Invariants

| ID | Statement | Priority |
|----|-----------|----------|
| INV-CB1 | DORMANT ⟹ multiplier == 0.0 EXACTLY | P0 |
| INV-CB2 | Vitrification O(1) — one tick | P0 |
| INV-CB3 | Snapshot non-None in DORMANT | P1 |
| INV-CB4 | Rehydration stages non-decreasing | P0 |
| INV-CB5 | Entry > individual module thresholds | P1 |
| INV-CB6 | T ∈ [0, 1] | P0 |
| INV-CB7 | exit < entry (hysteresis) | P0 |
| INV-CB8 | T ≥ entry during rehydration → DORMANT | P0 |
