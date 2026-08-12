# Research Timeline

This timeline records the substrate-level results and architectural milestones
that the GeoSync codebase rests on. Numbers are stated as of the last commit
to this file (see `git log`); when in doubt, re-derive from the source of
truth shown in the **Source** column.

> Convention: `γ` denotes the metastable-computation scaling exponent
> hypothesized in this research line. See [`GLOSSARY.md`](./GLOSSARY.md).

## 2022

| Milestone | Source |
| --- | --- |
| Self-directed computational neuroscience study begins | — |
| First experiments with neural-dynamics simulation | — |

## 2023

| Milestone | Source |
| --- | --- |
| Mycelium-Fractal-Net (MFN) initial codebase | [`src/mycelium_fractal_net/`](../../src/mycelium_fractal_net/) |
| `γ ≈ 1.0` first observed in BN-Syn spiking-network simulations | external repo `BN-Syn` |
| GeoSync repository created — Kuramoto synchronization × market microstructure | this repo |
| Adversarial Orchestration methodology formalized | [`METHODOLOGY.md`](./METHODOLOGY.md) |

## 2024

| Milestone | Source |
| --- | --- |
| `γ ≈ 1.0` hypothesis: metastable computation invariant across substrates | external research notes |
| NFI architecture defined: ML-SDM, CA1-LAM, BN-Syn, MFN+ | external `NFI` repo |
| 6-substrate validation, mean γ = 0.994 ± 0.077 (zebrafish 0.967, Gray-Scott 1.000, Kuramoto 1.081, BN-Syn 0.959, NFI unified 0.8993, CNS-AI 1.059) | external substrate logs |
| NeoSynaptex monorepo created | external `NeoSynaptex` repo |
| GeoSync neuromodulation layer: serotonin ODE, dopamine TD, GABA gate, ECS Lyapunov | [`src/geosync/`](../../src/geosync/) |

## 2025

| Milestone | Source |
| --- | --- |
| NeoSynaptex: 232 tests, 13 scientific gaps closed, Protocol 7X | external `NeoSynaptex` repo |
| GeoSync: HPC Active Inference v4 | [`src/geosync/`](../../src/geosync/) |
| Physics Kernel formalized: AST-based validator + invariant registry | [`.claude/physics/`](../../.claude/physics/) |

## 2026-Q2

| Milestone | Source |
| --- | --- |
| Cryptobiosis module (tardigrade-inspired phase-transition survival) | [`.claude/physics/CRYPTOBIOSIS_THEORY.md`](../../.claude/physics/CRYPTOBIOSIS_THEORY.md) |
| Ontology of Gradient — invariant `INV-YV1` | [`.claude/physics/INVARIANTS.yaml`](../../.claude/physics/INVARIANTS.yaml) |
| GeoSync v0.1.0 public release candidate | repository tag |
| Physics Kernel: **60 invariants** across 16 categories (40 P0 / 17 P1 / 3 P2) | derived from [`.claude/physics/INVARIANTS.yaml`](../../.claude/physics/INVARIANTS.yaml) |
| Parallel `physics_contracts/` law catalog: **26 module-anchored laws** | [`physics_contracts/catalog.yaml`](../../physics_contracts/catalog.yaml) |
| pytest suite size on `main`: ≈8.8k test functions across 844 files | derive via `grep -rh "^def test_" tests/ \| wc -l` |

## How to update this file

1. State the milestone in one line.
2. Cite a source the reader can open today.
3. If the milestone is a numeric claim, name the script that re-derives it,
   not the value. Numbers drift; commands stay valid until the schema changes.
4. Any change to the substrate-validation block (2024) must be co-signed by a
   commit that also updates the underlying logs in the originating repo.
