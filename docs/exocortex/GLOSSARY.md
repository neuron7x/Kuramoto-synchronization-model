# Glossary

Definitions of in-house terms used across [`CLAUDE.md`](../../CLAUDE.md), the
`.claude/physics/` documents, and this directory. Terms defined elsewhere in
mainstream literature (e.g. *Lyapunov exponent*, *Ricci curvature*) are
referenced rather than redefined here; see the cited sources.

## Notation

| Symbol | Meaning |
| --- | --- |
| `γ` (gamma) | Metastable-computation scaling exponent. Hypothesized to be ≈ 1 across substrates with critical neural-like dynamics. See [`RESEARCH_TIMELINE.md`](./RESEARCH_TIMELINE.md). |
| `R(t)` | Kuramoto order parameter at time *t*: `\| (1/N) Σ_j exp(i θ_j(t)) \|`. Bounded in `[0, 1]`. See [`.claude/physics/KURAMOTO_THEORY.md`](../../.claude/physics/KURAMOTO_THEORY.md). |
| `K_c` | Critical coupling for Kuramoto synchrony onset. `K_c = 2 / (π · g(0))` for unimodal `g`. |
| `INV-*` | Stable identifier for a physics invariant. Listed in [`INVARIANTS_INDEX.md`](./INVARIANTS_INDEX.md). |

## Acronyms

| Term | Expansion | Where it lives |
| --- | --- | --- |
| **TACL** | Tonic-Adaptive Coupling Layer — neuromodulator-gated coupling matrix used by the GeoSync neural controller | [`src/geosync/neural_controller/`](../../geosync/neural_controller/) |
| **MFN** | Mycelium-Fractal-Net — fractal-routing substrate inspired by hyphal-network growth | [`src/mycelium_fractal_net/`](../../src/mycelium_fractal_net/) |
| **BN-Syn** | Biophysical-Network Synthetic — spiking-network simulator (external repo); first place `γ ≈ 1` was observed | external |
| **NFI** | Neuro-Fractal-Inference platform composing ML-SDM, CA1-LAM, BN-Syn, MFN+ | external |
| **ML-SDM** | Multi-Layer Sparse Distributed Memory | external (NFI) |
| **CA1-LAM** | CA1-inspired Local Associative Memory | external (NFI) |
| **ECS** | Energy-Constraint System — Lyapunov-bounded controller used to keep strategies inside a free-energy budget | [`src/geosync/`](../../src/geosync/) |
| **OMS** | Order-Management System | [`src/geosync/`](../../src/geosync/), invariants under `oms.*` |

## Roles (see [`METHODOLOGY.md`](./METHODOLOGY.md))

| Role | Authority |
| --- | --- |
| **Creator** | Proposes a change. Cannot self-approve. |
| **Critic** | Challenges the change. May block on physics or architectural grounds. |
| **Auditor** | Confirms the gates passed. Signs CI status. |
| **Verifier** | Confirms reproducibility. Signs the release tag. |
| **Human** | Central decision node. Only signer of the merge commit. |

## Priority levels for invariants

| Priority | Meaning | CI behavior |
| --- | --- | --- |
| **P0** | Universal invariant. Violation = bug, not numerical artefact. | Block release. |
| **P1** | Asymptotic / regime-dependent invariant. Violation under documented conditions = bug. | Block release. |
| **P2** | Soft invariant. Violation = warning + tracked regression budget. | Report-only by default; can be promoted to P1. |
