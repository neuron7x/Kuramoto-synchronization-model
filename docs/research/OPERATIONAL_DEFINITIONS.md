<!-- Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab) -->
<!-- SPDX-License-Identifier: MIT -->

# Operational Definitions of the Physics & Neuroscience Vocabulary (RES-003)

GeoSync borrows heavily from physics and neuroscience — Kuramoto synchronization,
Ricci curvature, free energy, serotonin, dopamine, GABA. **A borrowed name is not a
mechanism.** This document, together with the machine-readable ontology
[`governance/operational_definitions.json`](../../governance/operational_definitions.json),
gives every active term an *operational definition* so a metaphor can never be
mistaken for a mechanism.

Project maturity is `RESEARCH_ALPHA` (see
[`governance/project_state.yaml`](../../governance/project_state.yaml)): instrumentation
and gates exist; live claims rest on synthetic or single-session evidence only. Nothing
here asserts market edge — the definitions describe the **mathematical objects and their
falsifiers**, not predictive power.

## What an operational definition must supply

For every **ACTIVE mechanism** term the ontology records six things:

1. **Mathematical object** — the exact quantity (e.g. the Kuramoto order parameter).
2. **Observable → math mapping** — how a measurable input becomes that quantity.
3. **Units / dimensions** — including "dimensionless" where that is the honest answer.
4. **Validity domain** — the regime where the object's laws hold.
5. **Alternative hypotheses** — the non-mechanism explanations that could produce the
   same reading (finite-size noise, estimator bias, embedding artifacts, ...).
6. **Falsifier** — an executable condition, tied to a registered `INV-*` invariant, that
   would refute the object.

A term with **no admissible observable → math mapping** is not allowed to sit as an
active mechanism. It is either **RETIRED** (a tombstone, preserved as negative evidence)
or explicitly labelled an **ANALOGUE** (an arithmetic proxy — a non-claim).

## Status vocabulary

| Status | Meaning | Is it a claim? |
| --- | --- | --- |
| `mechanism` | Rigorous mathematical object with an observable mapping and an executable falsifier, backed by P0/P1 invariants. | Yes |
| `analogue` | An engineering/arithmetic proxy that borrows a biological or physical name. The name is metaphorical; no biological or physical mechanism is asserted or measured (per `INV-HOM1`). | **No** |
| `retired` | A former framing that was a category error or was falsified. Preserved as a tombstone; never backs a live claim. | **No** |

## The terms

### Mechanisms (6)

These have rigorous mathematical objects, observable mappings, and falsifiers wired to
the invariant registry in [`CLAUDE.md`](../../CLAUDE.md).

| Term | Mathematical object | Key falsifier | Invariants |
| --- | --- | --- | --- |
| `synchronization` | Kuramoto order parameter `R = |mean(exp(i·θ))| ∈ [0,1]` | `R > 3/√N` after 1e4 steps at `K = 0.1·K_c`, `N>100` | INV-K1..K10, INV-OA1..3 |
| `curvature` | Ollivier–Ricci `κ = 1 − W₁/d`, `κ ≤ 1` | `κ > 1` on a connected graph; silent sign clip at the ROH boundary | INV-RC1..3, INV-KR4 |
| `energy` | Kuramoto potential `V = −(K·N/2)R²`; swing energy; free energy `F = U − T·S` | swing-energy secular growth; `F` increasing under active inference | INV-K7..K10, INV-FE1..2 |
| `entropy` | Entropy production `σ ≥ 0`; variational `S_q ≥ 0`; phase entropy | `σ < 0`; Jarzynski identity broken; phases fail Rayleigh uniformity | INV-TH1..2, INV-ST1..3 |
| `phase_transition` | `K_c = 2/(π·g(0))`; `R_∞ ∝ √(K−K_c)`; ROH boundary `Φ = K·λ_max(A_κ) − 2γ` | `sign(Φ)` fails to predict the `⟨R⟩` regime; hysteresis width `< 0` | INV-K2/K3, INV-KR1..2, INV-ES1..2 |
| `criticality` | `κ_critical = −ln(ΔH_max/ε)/(λ_local+δ)` (DFA Hurst); DRO `γ = 2H+1` | `|γ − (2H+1)| ≥ 1e-5`; a fragile node is not isolated | INV-AC1-rev, INV-DRO1..5 |

**Honest scope note on `criticality`.** The operational object is the DFA-derived
fragility/isolation gate and the fractional-Gaussian scaling identity `γ = 2H+1`. It does
**not** assert market self-organized criticality — that would be a separate, unmeasured
claim. The mechanism here is the gate, not a physical critical point in the market.

### Analogues (3) — arithmetic proxies, **not** biology

The neuromodulator vocabulary is an **engineering analogue**. Per `INV-HOM1`, the
`E`/`I`/`serotonin` quantities are *arithmetic proxies* and the invariant is explicitly a
**NON-CLAIM**. The invariants attached to these terms are real — they govern the
*arithmetic* (boundedness, Lyapunov descent, saturation, veto) — but the biological
**names are metaphors**. No neurotransmitter, receptor, channel, or pathway is modeled or
measured.

| Term | Arithmetic object | What it actually is | Invariants |
| --- | --- | --- | --- |
| `serotonin` | `s = σ(k·(tonic−θ))·sensitivity ∈ [0,1]`, Lyapunov `V(s)` non-increasing | a bounded sigmoid risk-tempering controller | INV-5HT1..7, INV-HOM1 |
| `dopamine` | TD error `δ = r + γ·V′ − V` (`∂δ/∂r = 1`); tanh adapter `|δ| ≤ 1` | a textbook TD(0) reward-surprise update | INV-DA1..8 |
| `gaba` | inhibition gate `g ∈ [0,1]`, `effective = raw·(1−inhibition)` | a volatility-scaled down-weighting clamp | INV-GABA1..5, INV-HOM1 |

**Why analogue and not mechanism?** Each is fully reproduced by a plain, name-free
control primitive (a bounded sigmoid, a TD update, a saturating clamp). The biological
label carries no additional explanatory content and no biological quantity is measured, so
labelling it a *mechanism* would overclaim. The gate below fails closed if any of these is
relabelled `mechanism`.

### Retired (1) — tombstone

| Term | Why retired | Replaced by |
| --- | --- | --- |
| `heisenberg_uncertainty` | Category error: asserted `Δx·Δp ≥ ℏ/2` on price and `diff(price)`, which are jointly observable (not conjugate), with a fabricated `ℏ/2`. No admissible observable mapping; unfalsifiable as stated. | Gabor time-frequency limit `Δt·Δf ≥ 1/(4π)` (`INV-GABOR1`, `core/physics/uncertainty.py`) |

The retired framing is preserved as negative evidence — it must never reappear as a live
mechanism. The correct, operationally-defined object is the exact Fourier bound `1/(4π)`,
which needs no Planck constant.

## The claim gate

[`scripts/ci/check_terminology.py`](../../scripts/ci/check_terminology.py) enforces the
ontology, fail-closed:

```bash
# 1. Validate the ontology: schema + semantic rules.
python scripts/ci/check_terminology.py --validate

# 2. Claim gate: a doc/PR asserts it uses a term as a mechanism.
python scripts/ci/check_terminology.py --assert synchronization --as mechanism   # PASS (rc 0)
python scripts/ci/check_terminology.py --assert serotonin      --as mechanism   # FLAGGED (rc 1)
python scripts/ci/check_terminology.py --assert quantum_alpha  --as mechanism   # FLAGGED (rc 1)
```

The gate goes **RED** when:

- an active `mechanism` term is missing its `math_object`, `observable_mapping`,
  `falsifier`, or `alternatives`;
- a metaphor-only term (a neuromodulator, or a retired framing) is labelled `mechanism`;
- a term declares an unknown `status`;
- a claim asserts a term as a `mechanism` that the ontology defines as `analogue`,
  `retired`, or does not define at all (a term used as mechanism **without** an operational
  definition).

Exit codes: `0` clean, `1` a contradiction was found, `2` the ontology/schema could not be
read (hard fail-closed).

## Closure

`tests/ci/test_terminology.py` proves both polarities: the committed ontology validates
(POSITIVE), and each corruption — a mechanism missing a falsifier, a mechanism with no
observable mapping, an unknown status, a metaphor relabelled as mechanism — drives the gate
RED (NEGATIVE).

## Sources of truth

- [`CLAUDE.md`](../../CLAUDE.md) — the invariant registry (the mathematical definitions).
- [`FORBIDDEN_CLAIMS.md`](../../FORBIDDEN_CLAIMS.md) — the status/claim-word firewall.
- [`governance/project_state.yaml`](../../governance/project_state.yaml) — the project
  maturity state (`RESEARCH_ALPHA`) and evidence-class vocabulary.
- [`PRODUCT_CATEGORY.md`](../../PRODUCT_CATEGORY.md) — verification-first research platform,
  not a live-trading or alpha product.
